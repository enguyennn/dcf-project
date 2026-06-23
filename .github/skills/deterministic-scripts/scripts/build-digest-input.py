#!/usr/bin/env python3
"""Build digest-input.json from raw Conductor upstream outputs.

Takes a JSON file with raw upstream agent outputs (as dumped by Jinja2 templates)
and produces the exact digest-input.json schema that compose-digest.py expects.

This eliminates LLM judgment from JSON construction — all mapping, classification,
and verdict computation is deterministic.

Usage:
    python build-digest-input.py upstream.json --output-file digest-input.json
    python build-digest-input.py upstream.json --merge existing-digest-input.json --output-file merged.json

Input schema (upstream.json):
{
  "pr_url": "https://...",
  "pr_title": "...",
  "platform": "ado|github",
  "code_review_findings": { "tier": "1", "important": [...], "suggestions": [...] },
  "code_fix": { "fixes_applied": 1, "fix_commits": ["sha1"] },
  "risk_level": "medium",
  "risk_signals": [...],
  "watch_and_fix": { "build_status": "passed", "fixes_pushed": 0, "fix_summaries": [], "elapsed_minutes": 23 },
  "address_feedback": { "status": "no_feedback" }
  // OR: { "iteration": 1, "comments_addressed": 3, "fix_commits": ["sha"], "all_addressed": true }
  // status: "no_feedback" = phase ran but no reviewer comments existed
  // omit address_feedback entirely = phase hasn't run yet (shows ⏳ Pending)
}

Output: digest-input.json matching compose-digest.py schema
"""

import argparse
import json
import re
import subprocess
import sys

from encoding_utils import clean_html, load_json_robust, sanitize_llm_json
from phase_contracts import coerce_phase_types, read_phase_output
from phase_models import PHASE_MODELS, to_list as ensure_list
from phase_output_validation import validate_upstream_data

IMPORTANT_KEYS = ("important", "Important")
ACTIONABLE_KEYS = ("critical", "Critical", *IMPORTANT_KEYS, "high", "High")
SUGGESTION_KEYS = ("suggestions", "Suggestion", "suggestion", "Medium", "medium", "Low", "low")
SEVERITY_KEYS = (*ACTIONABLE_KEYS, *SUGGESTION_KEYS)
SEVERITY_LABEL_MAP = {"high": "Important", "medium": "Suggestion", "low": "Suggestion"}
STATUS_ICONS = {"complete": "✅", "warning": "⚠️", "failed": "🔴", "pending": "⏳", "suggestion": "💡"}
RESOLUTION_STATUS = {
    "fixed": "✅ Fixed",
    "bydesign": "✅ By Design",
    "by_design": "✅ By Design",
    "wontfix": "✅ Won't Fix",
    "wont_fix": "✅ Won't Fix",
    "deferred": "⏭️ Deferred",
}

def _phase_output(data: dict, phase_id: str) -> dict:
    """Read a phase output with backward-compatible fallback."""
    phase_data = read_phase_output(data, phase_id)
    return dict(phase_data) if isinstance(phase_data, dict) else {}

def _coerce_model(model_cls, phase_id: str, phase_data: dict):
    try:
        return model_cls.from_raw(phase_data)
    except (ValueError, TypeError):
        try:
            return model_cls.from_raw(coerce_phase_types(phase_id, phase_data))
        except (ValueError, TypeError):
            return model_cls()

def _phase_model(data: dict, phase_id: str):
    """Read a phase output and coerce it into its typed model."""
    model_cls = PHASE_MODELS.get(phase_id)
    if not model_cls:
        return _phase_output(data, phase_id)
    phase_data = _phase_output(data, phase_id)
    model = _coerce_model(model_cls, phase_id, phase_data)
    phase_data.update(model.to_dict())
    return model

def _nested_phase_output(data: dict, phase_id: str, nested_key: str) -> dict:
    """Merge nested compatibility blobs with canonical phase output.

    Applies typed model coercion (if available) then falls back to
    coerce_phase_types to guarantee downstream consumers always see
    correct types regardless of what LLM/Conductor wrote.
    """
    merged = {}
    nested_state = data.get(nested_key)
    if isinstance(nested_state, dict):
        merged.update(nested_state)

    phase_data = _phase_output(data, phase_id)
    nested_phase = phase_data.get(nested_key)
    if isinstance(nested_phase, dict):
        merged.update(nested_phase)

    for key, value in phase_data.items():
        if key != nested_key and value is not None:
            merged[key] = value

    # Typed model coercion (preferred) with fallback to dict-based coercion.
    # Merge coerced fields back so unknown keys survive.
    model_cls = PHASE_MODELS.get(phase_id)
    if model_cls:
        try:
            coerced = model_cls.from_raw(merged).to_dict()
            merged.update(coerced)
            return merged
        except (ValueError, TypeError):
            pass
    return coerce_phase_types(phase_id, merged)

def _nested_phase_model(data: dict, phase_id: str, nested_key: str):
    """Read a nested compatibility blob and coerce it into its typed model."""
    model_cls = PHASE_MODELS.get(phase_id)
    if not model_cls:
        return _nested_phase_output(data, phase_id, nested_key)
    return _coerce_model(model_cls, phase_id, _nested_phase_output(data, phase_id, nested_key))

def _hydrate_phase_contract_fields(data: dict) -> dict:
    """Expose contract-backed phase fields in the working copy."""
    for phase_id, keys in {
        "2": ("pr_url", "pr_title", "work_items_linked"),
        "4": ("digest_comment_url", "digest_comment_id"),
        "4b": (
            "walkthrough_posted",
            "pr_classification",
            "skip_reason",
            "diagram_count",
            "concepts_explained",
        ),
    }.items():
        phase_model = _phase_model(data, phase_id)
        for key in keys:
            value = getattr(phase_model, key, None)
            if value is not None:
                data[key] = value
    return data

def _clean_thread_payload(value):
    """Normalize HTML-heavy thread payload fields into plain text."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in {"body", "finding_summary", "content"} and isinstance(item, str):
                max_length = 150 if key == "finding_summary" else None
                cleaned[key] = clean_html(item, max_length=max_length)
            else:
                cleaned[key] = _clean_thread_payload(item)
        return cleaned
    if isinstance(value, list):
        return [_clean_thread_payload(item) for item in value]
    return value

def _warn_unparseable_code_review_findings(phase_1c) -> None:
    """Emit the legacy parse warning when Phase 1c received bad findings JSON."""
    if getattr(phase_1c, "_code_review_findings_parse_failed", False):
        print(
            f"WARNING: code_review_findings is unparseable (type={getattr(phase_1c, '_code_review_findings_raw_type', 'unknown')}, len={getattr(phase_1c, '_code_review_findings_raw_len', 0)})",
            file=sys.stderr,
        )

def _parse_code_review_findings(raw, *, warn: bool = False) -> dict:
    """Compatibility shim: Phase 1c parsing now happens inside the typed model."""
    phase_1c = raw if hasattr(raw, "code_review_findings") else PHASE_MODELS["1c"].from_raw({"code_review_findings": raw})
    if warn:
        _warn_unparseable_code_review_findings(phase_1c)
    return phase_1c.code_review_findings

def normalize_upstream(data: dict) -> dict:
    """Restructure flat state-file keys into the nested schema expected by
    ``build_digest_input()``.

    Handles two common mismatches:
    1. Flat keys (``fixes_pushed``, ``fix_summaries``, …) at top level instead
       of nested under ``watch_and_fix`` / ``code_fix``.
    2. List fields stored as Python repr strings (e.g. ``"['sha1']"``).

    When the state file contains ``_phases`` (namespaced per-phase output),
    uses phase-specific data to avoid cross-phase key collisions (e.g.,
    Phase 3 ``fix_commits`` overwriting Phase 1d ``fix_commits``).
    """
    _hydrate_phase_contract_fields(data)
    phase_1d = _nested_phase_model(data, "1d", "code_fix")
    phase_3 = _nested_phase_model(data, "3", "watch_and_fix")

    phase3_present = bool(getattr(phase_3, "_provided_fields", set()))
    phases_blob = data.get("_phases")
    if isinstance(phases_blob, dict) and "3" not in phases_blob:
        phase_3 = PHASE_MODELS["3"].from_raw({})
        phase3_present = False

    completed = data.get("_completed_phases", [])
    phase3_ran = "3" in completed if completed else phase3_present

    if "watch_and_fix" not in data and phase3_ran:
        data["watch_and_fix"] = {"build_status": phase_3.build_status or "unknown", "fixes_pushed": phase_3.fixes_pushed, "fix_summaries": phase_3.fix_summaries, "fix_commits": phase_3.fix_commits, "elapsed_minutes": phase_3.elapsed_minutes}

    if not phase3_ran and isinstance(data.get("watch_and_fix"), dict):
        waf = data["watch_and_fix"]
        if not waf.get("fix_summaries") and not waf.get("fix_commits"):
            data["watch_and_fix"] = {
                "build_status": "skipped",
                "fixes_pushed": 0,
                "fix_summaries": [],
                "fix_commits": [],
                "elapsed_minutes": 0,
            }

    phase1d_present = bool(getattr(phase_1d, "_provided_fields", set()))
    if "code_fix" not in data and phase1d_present:
        data["code_fix"] = {"fixes_applied": phase_1d.fixes_applied, "fix_commits": phase_1d.fix_commits, "findings_remaining": phase_1d.findings_remaining}

    if isinstance(data.get("watch_and_fix"), dict):
        waf = data["watch_and_fix"]
        waf_model = PHASE_MODELS["3"].from_raw(waf)
        waf.update(waf_model.to_dict())

    if isinstance(data.get("code_fix"), dict):
        cf = data["code_fix"]
        cf_model = PHASE_MODELS["1d"].from_raw(cf)
        cf.update(cf_model.to_dict())

    return data

def extract_file_and_line(file_str: str) -> tuple[str, int | None]:
    """Extract clean file path and line number from code review file strings.

    Handles formats like:
    - "Frontend/src/.../StringUtils.ts (line 87)"
    - "Frontend/src/.../StringUtils.ts (lines 41-51)"
    - "path.cs (~lines 731-777)"
    - "File.ts (line 87) + OtherFile.ts (lines 10, 20)"
    """
    # Extract first file path (before any parenthetical)
    file_match = re.match(r"([^\(]+?)(?:\s*\(|$)", file_str)
    file_path = file_match.group(1).strip() if file_match else file_str.strip()

    # Extract first line number
    line_match = re.search(r"line[s]?\s+~?(\d+)", file_str)
    line_num = int(line_match.group(1)) if line_match else None

    return file_path, line_num

def map_findings(phase_1c, code_fix, pr_url: str, *, repo_root: str | None = None) -> list[dict]:
    """Map code_review findings to prevalidate table rows."""
    findings = []
    fix_commits = resolve_short_shas(code_fix.fix_commits if code_fix else [], None, repo_root=repo_root)
    code_review = phase_1c.code_review_findings

    raw_findings = []

    search_dicts = [code_review]
    nested_findings = code_review.get("findings")
    if isinstance(nested_findings, dict):
        search_dicts.append(nested_findings)

    for search_dict in search_dicts:
        for severity_key in SEVERITY_KEYS:
            for item in search_dict.get(severity_key, []):
                finding = dict(item)
                base = severity_key.rstrip("s").lower()
                finding["_severity"] = SEVERITY_LABEL_MAP.get(base, base.capitalize())
                raw_findings.append(finding)
        if raw_findings:
            break

    flat_findings = code_review.get("findings", [])
    if not raw_findings and isinstance(flat_findings, list):
        for item in flat_findings:
            finding = dict(item)
            finding["_severity"] = finding.get("severity", "Suggestion")
            raw_findings.append(finding)

    review_engine = determine_found_by(phase_1c)

    mechanical_idx = 0
    for i, finding in enumerate(raw_findings, 1):
        classification = finding.get("classification", "")
        category = finding.get("category", "")
        is_mechanical = finding.get("mechanical") is True or classification == "mechanical" or category == "mechanical"
        severity = finding.get("_severity", "Suggestion")

        if is_mechanical and fix_commits:
            commit_sha = fix_commits[mechanical_idx] if mechanical_idx < len(fix_commits) else fix_commits[-1]
            mechanical_idx += 1
            status = "✅ Fixed"
            fixed_by = "Auto-fix"
        elif severity.lower() in ("critical", "important"):
            status = "⚠️ Needs judgment"
            fixed_by = ""
            commit_sha = ""
        else:
            status = "💡 Suggestion"
            fixed_by = ""
            commit_sha = ""

        file_path, _line_num = extract_file_and_line(finding.get("file", ""))
        raw_file = finding.get("file", file_path)
        commit_url = build_commit_url(pr_url, commit_sha) if commit_sha else ""
        file_url = build_file_url(pr_url, raw_file)

        findings.append({
            "num": i,
            "file": raw_file,
            "file_url": file_url,
            "finding": finding.get("description", finding.get("finding", "")),
            "found_by": f"Code Review ({review_engine})",
            "fixed_by": fixed_by,
            "commit_sha": commit_sha,
            "commit_url": commit_url,
            "status": status,
        })

    return findings

def determine_found_by(phase_1c) -> str:
    """Determine review engine label from phase output."""
    engine = phase_1c.code_review_findings.get("review_engine", "")
    if engine and engine.lower() == "unavailable":
        return "Unavailable"
    tier = str(phase_1c.tier or phase_1c.code_review_findings.get("tier", ""))
    if re.match(r"^(1|Tier\s*1)", tier, re.IGNORECASE):
        return "Gatekeeper"
    # No engine and no tier means no review ran
    if not engine and not tier:
        return "Unavailable"
    return "Gatekeeper"

def build_thread_url(pr_url: str, thread_id: str, platform: str = "") -> str:
    """Build a URL to a specific discussion thread within the PR."""
    if not thread_id or not pr_url:
        return ""
    # Auto-detect platform from URL if not provided
    if not platform:
        if "github.com" in pr_url:
            platform = "github"
        else:
            platform = "ado"
    if platform == "ado":
        ado_match = re.search(r"(https?://.+/pullrequest/\d+)", pr_url)
        if ado_match:
            return f"{ado_match.group(1)}?discussionId={thread_id}"
    elif platform == "github":
        gh_match = re.search(r"(https?://github\.com/[^/]+/[^/]+/pull/\d+)", pr_url)
        if gh_match:
            return f"{gh_match.group(1)}#discussion_r{thread_id}"
    return ""

def build_file_url(pr_url: str, file_path: str) -> str:
    """Build a URL to the file's diff view within the PR."""
    if not file_path or not pr_url:
        return ""
    # Strip line references and extra files for clean path
    clean = re.sub(r"\s*\(lines?\s+[^)]+\)", "", file_path)
    clean = re.sub(r"\s*\+\s+\S+.*", "", clean).strip()
    # ADO PR: append ?_a=files&path=/filepath
    ado_match = re.search(r"(https?://.+/pullrequest/\d+)", pr_url)
    if ado_match:
        encoded = clean.lstrip("/").replace(" ", "%20")
        return f"{ado_match.group(1)}?_a=files&path=/{encoded}"
    # GitHub PR: append /files and use anchor
    gh_match = re.search(r"(https?://github\.com/[^/]+/[^/]+/pull/\d+)", pr_url)
    if gh_match:
        return f"{gh_match.group(1)}/files"
    return ""

def _git_rev_parse(short_sha: str, repo_root: str | None) -> str | None:
    """Resolve a short SHA to full 40-char SHA via ``git rev-parse``.

    Returns the full SHA or None if resolution fails (missing repo, ambiguous
    SHA, not a valid object, etc.).  Errors are silently swallowed — callers
    fall back to scrape data or passthrough.
    """
    if not repo_root:
        return None
    try:
        r = subprocess.run(
            ["git", "rev-parse", short_sha],
            capture_output=True, text=True, timeout=5,
            cwd=repo_root,
        )
        if r.returncode == 0:
            full = r.stdout.strip()
            if len(full) == 40:
                return full
    except Exception:
        pass
    return None


def resolve_short_shas(
    short_shas: list[str],
    scrape_data: dict | None,
    *,
    repo_root: str | None = None,
) -> list[str]:
    """Resolve short SHAs to full 40-char SHAs.

    Resolution order for each short SHA (< 40 chars):
      1. ``git rev-parse`` against *repo_root* (most reliable — works for any commit)
      2. Prefix-match against *scrape_data["commits"]* (fallback when repo unavailable)
      3. Pass through as-is (compose-digest renders plain text)

    Full 40-char SHAs always pass through unchanged.
    """
    full_shas_from_scrape = (
        [c.get("sha", "") for c in scrape_data.get("commits", []) if c.get("sha")]
        if scrape_data and scrape_data.get("commits")
        else []
    )

    resolved: list[str] = []
    for sha in short_shas:
        sha = str(sha).strip()
        if len(sha) >= 40:
            resolved.append(sha)
            continue
        # Layer 1: git rev-parse (authoritative)
        full = _git_rev_parse(sha, repo_root)
        if full:
            resolved.append(full)
            continue
        # Layer 2: scrape data prefix match
        match = next((f for f in full_shas_from_scrape if f.startswith(sha)), None)
        if match:
            resolved.append(match)
            continue
        # Layer 3: passthrough (build_commit_url will reject as safety net)
        resolved.append(sha)
    return resolved


def build_commit_url(pr_url: str, sha: str) -> str:
    """Build a commit URL from the PR URL and full SHA.

    Returns "" if *sha* is shorter than 40 characters — ADO commit detail
    pages fail with short SHAs (return "unexpected error").  Callers should
    use ``resolve_short_shas()`` first to upgrade short SHAs when scrape
    data is available; compose-digest renders plain ``abc1234`` text as
    graceful fallback when the URL is empty.
    """
    if not sha or not pr_url:
        return ""

    sha = str(sha).strip()
    if not sha or len(sha) < 40:
        return ""

    # ADO: https://dev.azure.com/org/project/_git/Repo/pullrequest/123
    #   or: https://msazure.visualstudio.com/One/_git/Repo/pullrequest/123
    #   → .../commit/{sha}
    ado_match = re.search(r"(https?://.+/_git/[^/]+)/pullrequest/\d+", pr_url)
    if ado_match:
        return f"{ado_match.group(1)}/commit/{sha}"

    # GitHub: https://github.com/owner/repo/pull/123
    #   → https://github.com/owner/repo/commit/{sha}
    gh_match = re.search(r"(https?://github\.com/[^/]+/[^/]+)/pull/\d+", pr_url)
    if gh_match:
        return f"{gh_match.group(1)}/commit/{sha}"

    return ""

def compute_verdict(phase_1c, code_fix=None) -> str:
    """Compute verdict from code review findings using deterministic priority rules.

    Gate statuses (lint/build/test/security) are no longer available since phase 1efg
    was removed. Verdict is now derived from code review findings only.
    """
    fix_commits = code_fix.fix_commits if code_fix else []
    code_review = phase_1c.code_review_findings
    has_unresolved_important = False
    for key in IMPORTANT_KEYS:
        for item in code_review.get(key, []):
            classification = item.get("classification", "")
            is_mechanical = item.get("mechanical") is True or classification == "mechanical"
            if not (is_mechanical and fix_commits):
                has_unresolved_important = True
                break
        if has_unresolved_important:
            break

    if has_unresolved_important:
        return "warnings"

    return "ready"

def format_advisory(advisory_data: dict | list | str | None) -> dict:
    """Format a single advisory check result."""
    if advisory_data is None:
        return {"check": "", "findings": "✅ No issues"}

    if isinstance(advisory_data, str):
        if "no issues" in advisory_data.lower() or "pass" in advisory_data.lower():
            return {"findings": "✅ No issues"}
        return {"findings": f"⚠️ {advisory_data}"}

    if isinstance(advisory_data, dict):
        verdict = advisory_data.get("verdict", "PASS")
        count = advisory_data.get("findings_count", 0)
        details = advisory_data.get("details", "")

        if verdict == "PASS" or count == 0:
            return {"findings": "✅ No issues"}

        # Extract a summary from details
        if isinstance(details, list):
            # Escape pipe chars to avoid breaking markdown table cells
            pipe = "|"
            escaped_pipe = r"\|"
            summaries = [d.get("description", d.get("finding", d.get("assessment", d.get("suggestion", "")))).replace(pipe, escaped_pipe)[:80] for d in details[:3]]
            return {"findings": f"⚠️ {count} finding(s): " + "; ".join(s for s in summaries if s)}
        elif isinstance(details, str):
            safe_details = details.replace("|", r"\|")[:120]
            return {"findings": f"⚠️ {safe_details}"}
        return {"findings": f"⚠️ {count} finding(s)"}

    return {"findings": "✅ No issues"}

def build_gates_list(data: dict, review_engine: str, mapped_findings: list[dict] | None = None) -> list[dict]:
    """Build the gate list from upstream data.

    Phase 1efg (deterministic gates) has been removed. Lint, build, test, and
    security gate statuses are no longer available from a dedicated phase.
    The code review gate is derived from phase 1c; CI build from phase 3.
    """
    phase_1c = _phase_model(data, "1c")
    completed = data.get("_completed_phases", [])
    phase3_ran = any(p == "3" or p.startswith("3") for p in completed)

    def gate_status(val, ci_gate: bool = False):
        s = str(val).lower()
        if "pass" in s:
            return "✅ Passed"
        if "fail" in s:
            return "❌ Failed"
        if "warn" in s:
            return "⚠️ Warning"
        if "skip" in s:
            return "⏭️ Skipped"
        if ci_gate and not phase3_ran:
            return "⏭️ Skipped"
        return "⏳ Pending"

    if (review_engine or "").strip().lower() == "unavailable":
        cr_status = "⚠️ Warning"
        cr_details = "No review engine available"
    elif mapped_findings is not None:
        fixed_count = sum(1 for f in mapped_findings if "Fixed" in f.get("status", ""))
        judgment_count = sum(1 for f in mapped_findings if "Needs judgment" in f.get("status", ""))
        suggestion_count = sum(1 for f in mapped_findings if "Suggestion" in f.get("status", ""))
        total_actionable = fixed_count + judgment_count

        if judgment_count > 0:
            cr_status = "⚠️ Warning"
            parts = []
            if fixed_count:
                parts.append(f"{fixed_count} fixed")
            if judgment_count:
                parts.append(f"{judgment_count} needs judgment")
            if suggestion_count:
                parts.append(f"{suggestion_count} suggestions")
            cr_details = ", ".join(parts)
        elif total_actionable > 0:
            cr_status = "✅ Passed"
            cr_details = f"{fixed_count} fixed, {suggestion_count} suggestions" if suggestion_count else f"{fixed_count} fixed"
        elif suggestion_count > 0:
            cr_status = "✅ Passed"
            cr_details = f"{suggestion_count} suggestions"
        else:
            cr_status = "✅ Passed"
            cr_details = "No issues"
    else:
        code_review = phase_1c.code_review_findings
        important_count = 0
        suggestion_count = 0
        search_dicts = [code_review]
        nested = code_review.get("findings")
        if isinstance(nested, dict):
            search_dicts.append(nested)
        for search_dict in search_dicts:
            for key in ACTIONABLE_KEYS:
                important_count += len(search_dict.get(key, []))
            for key in SUGGESTION_KEYS:
                suggestion_count += len(search_dict.get(key, []))
            if important_count or suggestion_count:
                break

        cr_status = "⚠️ Warning" if important_count > 0 else "✅ Passed"
        cr_details = f"{important_count} important, {suggestion_count} suggestions" if important_count > 0 else "No issues"

    def gate_details(val, passed_text: str, ci_gate: bool = False) -> str:
        s = str(val).lower()
        if "pass" in s:
            return passed_text
        if ci_gate and not phase3_ran and not val:
            return "CI build skipped"
        return str(val) if val else "—"

    # Phase 3 (CI) build status — use if available
    phase_3_data = _phase_output(data, "3")
    ci_build_status = phase_3_data.get("build_status", "")

    return [
        {"check": f"🔍 Code Review ({review_engine})", "status": cr_status, "details": cr_details},
        {"check": "🔨 Build (CI)", "status": gate_status(ci_build_status, ci_gate=True), "details": gate_details(ci_build_status, "Build succeeded", ci_gate=True)},
    ]

def build_advisory_list(data: dict) -> list[dict]:
    """Build the advisory section from upstream data.

    Advisory checks have been removed — returns empty list.
    Advisory agent no longer runs; kept for digest schema compatibility.
    """
    return []

def _summarize_signals(signals: list) -> str:
    """Summarize risk signals by grouping duplicate categories.

    Instead of listing every file, group signals like
    "API controller change" (×13), "Service layer change" (×11), ...
    and cap at MAX_SIGNAL_GROUPS to keep the digest compact.
    """
    import re

    MAX_SIGNAL_GROUPS = 5

    # Each signal looks like "🟡 path/to/File.cs: description"
    # Extract the description part (after the colon) for grouping
    categories: dict[str, int] = {}
    test_count = 0
    for s in signals:
        s_str = str(s)
        # Handle the "✅ N test file(s) included" line separately
        if "test file" in s_str.lower():
            m = re.search(r"(\d+)\s+test file", s_str)
            test_count = int(m.group(1)) if m else 1
            continue
        # Extract category after the colon
        parts = s_str.split(":", 1)
        if len(parts) == 2:
            cat = parts[1].strip()
        else:
            cat = s_str.strip()
        # Strip leading emoji
        cat = re.sub(r"^[🟡🔴🟢⚪✅⚠️\s]+", "", cat).strip()
        if cat:
            categories[cat] = categories.get(cat, 0) + 1

    # Sort by count descending
    sorted_cats = sorted(categories.items(), key=lambda x: -x[1])

    parts = []
    for cat, count in sorted_cats[:MAX_SIGNAL_GROUPS]:
        if count > 1:
            parts.append(f"🟡 {cat} (×{count})")
        else:
            parts.append(f"🟡 {cat}")

    remaining = len(sorted_cats) - MAX_SIGNAL_GROUPS
    if remaining > 0:
        parts.append(f"+{remaining} more categories")

    if test_count > 0:
        parts.append(f"✅ {test_count} test file(s) included")

    return ", ".join(parts) if parts else "No signals provided"

def build_risk(data: dict) -> dict:
    """Build risk section from upstream data."""
    level = str(data.get("risk_level", "unknown")).lower()
    signals = data.get("risk_signals", [])
    if isinstance(signals, str):
        try:
            signals = json.loads(signals)
        except (json.JSONDecodeError, ValueError):
            signals = [signals] if signals else []
    if not isinstance(signals, list):
        signals = [str(signals)] if signals else []
    if len(signals) > 5:
        signals_str = _summarize_signals(signals)
    else:
        signals_str = ", ".join(str(s) for s in signals)

    req_map = {
        "low": "AI review sufficient — human review optional",
        "medium": "Standard human review recommended",
        "high": "SME review required",
    }

    if level not in req_map:
        signals_str = signals_str or "Not assessed"

    return {
        "level": level,
        "signals": signals_str,
        "review_requirement": req_map.get(level, "Not assessed — no risk classification available"),
    }

def _field(data, key: str, default=None):
    """Read a field from either a dict or a typed phase model."""
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)

def _watch_fix_result(phase_3) -> str:
    """Map watch_and_fix build_status to timeline result string."""
    status = str(_field(phase_3, "build_status", "")).lower()
    if not status:
        return "⏳ Pending"
    if status in ("skipped", "unknown"):
        return "⏭️ Skipped"
    fixes = _field(phase_3, "fixes_pushed", 0)
    if status == "passed":
        return f"✅ Passed ({fixes} fix)" if fixes else "✅ Passed"
    if status == "failed":
        return f"🔴 Failed ({fixes} fix attempted)" if fixes else "🔴 Failed"
    if status in ("infra_failure", "infra"):
        return "🔴 Infra failure (not code-related)"
    if status == "limit_reached":
        return f"⚠️ Fix limit reached ({fixes} fixes)"
    if status in ("running", "in_progress"):
        return "🔄 Running"
    return f"⚠️ {status}"

def _af_duration(phase_5) -> str:
    """Map address_feedback to timeline duration string."""
    status = str(_field(phase_5, "status", "")).lower()
    if status == "no_feedback":
        return "< 1 min"
    iteration = _field(phase_5, "iteration", 0)
    if iteration:
        return f"{iteration} iteration(s)"
    address_feedback = _field(phase_5, "address_feedback", {}) or {}
    final_verdict = _field(phase_5, "final_verdict")
    digest_updated = _field(phase_5, "digest_updated")
    if isinstance(address_feedback, dict) and (address_feedback.get("final_verdict") or address_feedback.get("digest_updated")):
        return "< 1 min"
    if final_verdict or digest_updated:
        return "< 1 min"
    if isinstance(phase_5, dict):
        return "⏳ Pending" if not phase_5 else "< 1 min"
    if not getattr(phase_5, "_provided_fields", set()):
        return "⏳ Pending"
    return "< 1 min"

def _af_result(phase_5, completed_phases: list[str] | None = None) -> str:
    """Map address_feedback to timeline result string."""
    completed_phases = [str(p) for p in (completed_phases or [])]
    phase5_completed = any(p == "5" or p.startswith("5") for p in completed_phases)
    if isinstance(phase_5, dict):
        if not phase_5:
            return "✅ Complete (no feedback)" if phase5_completed else "⏳ Pending"
    elif not getattr(phase_5, "_provided_fields", set()):
        return "✅ Complete (no feedback)" if phase5_completed else "⏳ Pending"
    status = str(_field(phase_5, "status", "")).lower()
    if status == "no_feedback":
        return "✅ No feedback to address"
    if _field(phase_5, "all_addressed", False):
        return f"✅ {_field(phase_5, 'comments_addressed', 0)} addressed"
    comments_addressed = _field(phase_5, "comments_addressed", 0)
    if comments_addressed:
        return f"⚠️ {comments_addressed} addressed (some remain)"
    address_feedback = _field(phase_5, "address_feedback", {}) or {}
    final_verdict = _field(phase_5, "final_verdict")
    if not final_verdict and isinstance(address_feedback, dict):
        final_verdict = address_feedback.get("final_verdict")
    if final_verdict:
        verdict = str(final_verdict).lower()
        if verdict in ("completed", "no_feedback", "done"):
            return "✅ No feedback to address"
        return f"✅ {verdict.replace('_', ' ').title()}"
    if _field(phase_5, "digest_updated") or (isinstance(address_feedback, dict) and address_feedback.get("digest_updated")):
        return "✅ Complete"
    if phase5_completed:
        return "✅ Complete (no feedback)"
    return "⏳ Pending"

def build_timeline(data: dict) -> list[dict]:
    """Build the 5-phase timeline."""
    phase_3 = _nested_phase_model(data, "3", "watch_and_fix")
    phase_5 = _nested_phase_model(data, "5", "address_feedback")
    completed_phases = [str(p) for p in data.get("_completed_phases", [])]
    waf_skipped = str(phase_3.build_status).lower() in ("skipped", "unknown", "")

    return [
        {"phase": "Pre-Validate", "duration": "~8 min", "result": "✅ Complete"},
        {"phase": "Create PR", "duration": "~1 min", "result": "✅ Created"},
        {
            "phase": "Watch & Fix CI",
            "duration": "⏭️ Skipped" if waf_skipped else (f"~{phase_3.elapsed_minutes} min" if phase_3.elapsed_minutes else "⏳ Pending"),
            "result": "⏭️ Skipped" if waf_skipped else _watch_fix_result(phase_3),
        },
        {"phase": "Review Digest", "duration": "~2 min", "result": "✅ Posted"},
        {
            "phase": "Address Feedback",
            "duration": _af_duration(phase_5),
            "result": _af_result(phase_5, completed_phases),
        },
    ]

def build_digest_input(data: dict, *, scrape_waf: dict | None = None, repo_root: str | None = None) -> dict:
    """Build the complete digest-input.json from upstream data."""
    normalize_upstream(data)
    phase_1c = _phase_model(data, "1c")
    phase_1d = _nested_phase_model(data, "1d", "code_fix")
    phase_3 = _nested_phase_model(data, "3", "watch_and_fix")
    phase_5 = _nested_phase_model(data, "5", "address_feedback")
    phase_2 = _phase_model(data, "2")

    _parse_code_review_findings(getattr(phase_1c, "_code_review_findings_raw", phase_1c.code_review_findings), warn=True)
    pr_url = phase_2.pr_url or data.get("pr_url", "")

    review_engine = determine_found_by(phase_1c)
    prevalidate = map_findings(phase_1c, phase_1d, pr_url, repo_root=repo_root)

    human_findings = phase_1c.human_judgment_findings
    if human_findings:
        existing_descriptions = {f.get("finding", "") for f in prevalidate}
        start_num = len(prevalidate) + 1
        added = 0
        for hf in human_findings:
            file_path = hf.get("file", "Unknown")
            description = hf.get("description", hf.get("finding", ""))
            if len(description) > 150:
                description = description[:147] + "..."
            if description in existing_descriptions:
                continue
            file_url = build_file_url(pr_url, file_path)
            prevalidate.append({
                "num": start_num + added,
                "file": file_path,
                "file_url": file_url,
                "finding": description,
                "found_by": f"Code Review ({review_engine})",
                "fixed_by": "",
                "commit_sha": "",
                "commit_url": "",
                "status": "⚠️ Needs judgment",
                "view_url": file_url,
            })
            added += 1

    watch_fix = []
    waf_fix_summaries = phase_3.fix_summaries
    if scrape_waf and scrape_waf.get("commits"):
        scraped = scrape_waf["commits"]
        waf_commits = [c["sha"] for c in scraped]
        if not waf_fix_summaries and scraped:
            waf_fix_summaries = [c["message"] for c in scraped]
        fixes_pushed = len(scraped)
    else:
        waf_commits = phase_3.fix_commits
        fixes_pushed = phase_3.fixes_pushed
    if fixes_pushed > 0:
        for i, summary in enumerate(waf_fix_summaries, 1):
            sha = waf_commits[i - 1] if i - 1 < len(waf_commits) else ""
            watch_fix.append({
                "num": i,
                "file": "CI Build",
                "finding": summary,
                "found_by": "CI Build",
                "fixed_by": "Watch & Fix",
                "commit_sha": sha,
                "commit_url": build_commit_url(pr_url, sha),
                "status": "✅ Fixed",
            })

    feedback = []
    verdict = compute_verdict(phase_1c, phase_1d)
    risk = build_risk(data)

    return {
        "pr_url": pr_url,
        "risk": risk,
        "risk_level": risk["level"],
        "risk_level_displayed": risk["level"],
        "judgment_items": "",
        "findings": {
            "prevalidate": prevalidate,
            "watch_fix": watch_fix,
            "feedback": feedback,
        },
        "timeline": build_timeline(data),
        "gates": build_gates_list(data, review_engine, mapped_findings=prevalidate),
        "verdict": verdict,
        "advisory": build_advisory_list(data),
        "review_engine": review_engine,
        "total_duration": f"~{phase_3.elapsed_minutes + 15} min" if getattr(phase_3, "_provided_fields", set()) else "~45 min",
        "footer_variant": "Phase 4 Review Digest",
    }

def merge_phase5(existing: dict, data: dict, *, scrape_feedback: dict | None = None, thread_state: dict | None = None, triage_output: dict | None = None, repo_root: str | None = None) -> dict:
    """Merge Phase 5 (address_feedback) data into existing digest-input."""
    normalize_upstream(data)
    phase_5 = _nested_phase_model(data, "5", "address_feedback")

    completed = data.get("_completed_phases", existing.get("_completed_phases", []))
    if completed and "3" not in completed:
        findings = existing.get("findings", {})
        if findings.get("watch_fix"):
            findings["watch_fix"] = []

    existing_risk_level = existing.get("risk", {}).get("level") or build_risk(data).get("level", "unknown")
    existing.setdefault("risk_level", existing_risk_level)
    existing.setdefault("risk_level_displayed", existing_risk_level)

    if triage_output:
        summary = triage_output.get("summary", {})
        skipped_list = triage_output.get("skipped", [])
        skip_reasons: dict[str, int] = {}
        for s in skipped_list:
            reason = s.get("reason", "unknown")
            base_reason = reason.split(" (")[0] if " (" in reason else reason
            skip_reasons[base_reason] = skip_reasons.get(base_reason, 0) + 1
        existing["triage_summary"] = {
            "total": summary.get("total", len(triage_output.get("actionable", [])) + len(skipped_list)),
            "actionable": summary.get("actionable", len(triage_output.get("actionable", []))),
            "skipped": summary.get("skipped", len(skipped_list)),
            "skip_reasons": skip_reasons,
        }

    if not getattr(phase_5, "_provided_fields", set()):
        return existing

    phase_2 = _phase_model(data, "2")
    pr_url = phase_2.pr_url or data.get("pr_url", existing.get("pr_url", ""))

    # Re-resolve any short SHAs in Phase 1 prevalidate findings (belt-and-suspenders:
    # Phase 4 should have resolved them, but if it didn't we fix them here)
    if repo_root:
        for finding in existing.get("findings", {}).get("prevalidate", []):
            sha = finding.get("commit_sha", "")
            if sha and len(sha) < 40:
                full = _git_rev_parse(sha, repo_root)
                if full:
                    finding["commit_sha"] = full
                    finding["commit_url"] = build_commit_url(pr_url, full)

    feedback_findings = []
    if scrape_feedback and scrape_feedback.get("commits"):
        fix_commits = [c["sha"] for c in scrape_feedback["commits"]]
    else:
        # Agent-reported SHAs may be short — try to resolve against scrape data
        fix_commits = resolve_short_shas(phase_5.fix_commits, scrape_feedback, repo_root=repo_root)
    comments_addressed = phase_5.comments_addressed
    if thread_state and thread_state.get("addressed_details"):
        addressed_details = thread_state["addressed_details"]
    else:
        addressed_details = phase_5.addressed_details

    if addressed_details:
        # Per-comment rows from structured detail (preferred)
        seen_threads = set()
        for i, detail in enumerate(addressed_details, 1):
            tid = detail.get("thread_id", "")
            if tid and tid in seen_threads:
                continue  # dedupe by thread_id across cumulative iterations
            if tid:
                seen_threads.add(tid)
            sha = detail.get("commit_sha", "")
            resolution = detail.get("resolution", "fixed").lower().replace("-", "").replace(" ", "")
            status = RESOLUTION_STATUS.get(resolution, "✅ Fixed")
            feedback_findings.append({
                "num": i,
                "file": detail.get("file", "Unknown"),
                "finding": detail.get("finding_summary", "Review comment addressed"),
                "found_by": "Code Review",
                "fixed_by": "PROrchestrator (feedback)",
                "commit_sha": sha,
                "commit_url": build_commit_url(pr_url, sha),
                "status": status,
            })
    elif fix_commits and comments_addressed > 0 and triage_output and triage_output.get("actionable"):
        # Build per-thread rows from triage data when Phase 5 didn't report per-thread details
        sha = fix_commits[0] if fix_commits else ""
        commit_url = build_commit_url(pr_url, sha)
        for i, item in enumerate(triage_output["actionable"], 1):
            body = clean_html(item.get("body", "Review comment addressed"), max_length=150)
            feedback_findings.append({
                "num": i,
                "file": item.get("file", "Unknown"),
                "finding": body,
                "found_by": "Code Review",
                "fixed_by": "PROrchestrator (feedback)",
                "commit_sha": sha,
                "commit_url": commit_url,
                "status": "✅ Fixed",
            })
    elif fix_commits and comments_addressed > 0:
        # Last-resort fallback: collapsed single row when no triage data available
        sha = fix_commits[0] if fix_commits else ""
        commit_url = build_commit_url(pr_url, sha)
        feedback_findings.append({
            "num": 1,
            "file": "Multiple files",
            "finding": f"{comments_addressed} review comment(s) addressed",
            "found_by": "Code Review",
            "fixed_by": "PROrchestrator (feedback)",
            "commit_sha": sha,
            "commit_url": commit_url,
            "status": "✅ Fixed",
        })

    # Add triage actionable items that weren't addressed as "needs judgment"
    if triage_output:
        addressed_thread_ids = set()
        for detail in addressed_details:
            tid = detail.get("thread_id", "")
            if tid:
                addressed_thread_ids.add(str(tid))

        # When all comments were addressed but we lack per-thread detail,
        # treat every triage-actionable item as addressed (don't re-list as "Needs judgment").
        all_addressed = phase_5.all_addressed
        if all_addressed and not addressed_thread_ids and comments_addressed > 0:
            all_triage_addressed = True
        else:
            all_triage_addressed = False

        for item in triage_output.get("actionable", []):
            tid = str(item.get("thread_id", ""))
            if tid in addressed_thread_ids:
                continue  # already in the table as a fix
            if all_triage_addressed:
                continue  # bulk-addressed without per-thread detail
            next_num = len(feedback_findings) + 1
            # The triage script already extracts clean finding text from HTML.
            # Apply light cleanup for any remaining markdown formatting.
            body = clean_html(item.get("body", "Review comment"))
            if "--- _Posted by" in body:
                body = body[:body.index("--- _Posted by")].strip()
            elif "--- _" in body:
                body = body[:body.index("--- _")].strip()
            body = re.sub(r'^\*\*\w+\*\*\s*\S+\s*Code Review\s*', '', body, flags=re.IGNORECASE).strip()
            if body.startswith("Code Review: "):
                body = body[len("Code Review: "):]
            body = re.sub(r'^PR Assistant\s+AI Code Review\s+Iteration\d+\s+', '', body).strip()
            body = clean_html(body, max_length=150)
            # Set status based on diff scope
            item_scope = item.get("scope", "in_diff")
            if item_scope == "out_of_diff_scope":
                status = "⚠️ Out of diff — needs judgment"
            else:
                status = "⚠️ Needs judgment"
            # Build view URL — thread link for feedback items
            file_path = item.get("file", "Unknown")
            thread_url = build_thread_url(pr_url, tid) if tid else ""
            file_url = build_file_url(pr_url, file_path) if file_path else ""
            view_url = thread_url or file_url
            feedback_findings.append({
                "num": next_num,
                "file": (file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path),
                "file_url": file_url,
                "finding": body,
                "found_by": "Reviewer",
                "commit_sha": "",
                "commit_url": "",
                "status": status,
                "thread_id": tid,
                "view_url": view_url,
            })

    existing.setdefault("findings", {})["feedback"] = feedback_findings

    # Update prevalidate findings that were resolved by address_feedback
    if addressed_details:
        prevalidate = existing.get("findings", {}).get("prevalidate", [])
        for detail in addressed_details:
            detail_file = detail.get("file", "")
            detail_finding = clean_html(detail.get("finding_summary", ""), max_length=150)
            resolution = detail.get("resolution", "fixed").lower().replace("-", "").replace(" ", "")
            status = RESOLUTION_STATUS.get(resolution, "✅ Fixed")
            sha = detail.get("commit_sha", "")
            for pf in prevalidate:
                pf_file = pf.get("file", "")
                pf_finding = pf.get("finding", "")
                # Match by file + partial finding text overlap
                if (detail_file and pf_file and detail_file.rstrip("/") in pf_file
                        and "Needs judgment" in pf.get("status", "")):
                    pf["status"] = status
                    if sha:
                        pf["commit_sha"] = sha
                        pf["commit_url"] = build_commit_url(pr_url, sha)
                    break

    # Update timeline
    for t in existing.get("timeline", []):
        if t.get("phase") == "Address Feedback":
            if phase_5.status == "no_feedback":
                t["duration"] = "< 1 min"
                t["result"] = "✅ No feedback to address"
            elif phase_5.all_addressed:
                t["duration"] = f"{phase_5.iteration or 1} iteration(s)"
                t["result"] = f"✅ {phase_5.comments_addressed} addressed"
            elif phase_5.comments_addressed:
                t["duration"] = f"{phase_5.iteration or 1} iteration(s)"
                t["result"] = f"⚠️ {phase_5.comments_remaining} remaining"
            elif phase_5.address_feedback.get("final_verdict"):
                verdict = str(phase_5.address_feedback["final_verdict"]).lower()
                t["duration"] = "< 1 min"
                if verdict in ("completed", "no_feedback", "done"):
                    t["result"] = "✅ No feedback to address"
                else:
                    t["result"] = f"✅ {verdict.replace('_', ' ').title()}"
            elif phase_5.address_feedback.get("digest_updated"):
                t["duration"] = "< 1 min"
                t["result"] = "✅ Complete"
            else:
                t["duration"] = f"{phase_5.iteration or 1} iteration(s)"
                t["result"] = f"⚠️ {phase_5.comments_remaining} remaining"

    # Update verdict for final digest
    if phase_5.all_addressed and existing.get("verdict") != "changes_needed":
        gate_statuses = [g.get("status", "") for g in existing.get("gates", [])]
        # Gates with only warnings (no failures) are acceptable after resolution
        no_gate_failures = all("🔴" not in s for s in gate_statuses)
        # Check for unresolved findings across all categories
        all_findings = (
            existing.get("findings", {}).get("prevalidate", [])
            + existing.get("findings", {}).get("watch_fix", [])
            + existing.get("findings", {}).get("feedback", [])
        )
        has_unresolved = any(
            "Needs judgment" in f.get("status", "") or "🔴" in f.get("status", "")
            for f in all_findings
        )
        if no_gate_failures and not has_unresolved:
            existing["verdict"] = "approved"
        elif has_unresolved:
            existing["verdict"] = "warnings"

    existing["footer_variant"] = "Final Digest (all phases complete)"

    return existing

def _load_optional_json(path: str | None, label: str) -> dict | None:
    """Load an optional JSON file via the shared robust loader."""
    if not path:
        return None
    loaded = load_json_robust(path, label=label, default=None)
    return _clean_thread_payload(loaded) if isinstance(loaded, (dict, list)) else loaded

def _load_merge_base(merge_path: str, upstream_fallback: str | None, *, scrape_waf: dict | None = None) -> dict:
    """Load the merge base (existing digest-input.json) with fallback to upstream-data.json.

    Fallback chain:
      1. Try merge_path directly
      2. Try upstream_fallback → rebuild a full baseline via build_digest_input()
      3. Exit non-zero (refuse to produce a misleading digest from Phase 5 data alone)
    """
    existing = load_json_robust(merge_path, label="merge", default=None)
    if isinstance(existing, dict):
        existing = _clean_thread_payload(existing)
        if existing.get("gates"):
            return existing
        print(f"WARNING: Merge file {merge_path} loaded but has no gates — may be corrupt.", file=sys.stderr)

    if upstream_fallback:
        print(f"Falling back to upstream data: {upstream_fallback}", file=sys.stderr)
        upstream_data = load_json_robust(upstream_fallback, label="upstream-fallback", default=None)
        if isinstance(upstream_data, dict):
            upstream_data = _clean_thread_payload(upstream_data)
            upstream_valid, upstream_issues = validate_upstream_data(upstream_data)
            if upstream_valid:
                normalize_upstream(upstream_data)
                existing = build_digest_input(upstream_data, scrape_waf=scrape_waf)
                print(f"Rebuilt baseline from {upstream_fallback}: {len(existing.get('findings', {}).get('prevalidate', []))} findings", file=sys.stderr)
                return existing
            print(f"WARNING: Upstream fallback {upstream_fallback} failed validation", file=sys.stderr)
            for issue in upstream_issues:
                print(f"  - {issue}", file=sys.stderr)
        else:
            print(f"WARNING: Could not load upstream fallback {upstream_fallback}", file=sys.stderr)

    print("ERROR: Cannot build a trustworthy merge base. Both merge file and upstream fallback failed.", file=sys.stderr)
    print("Refusing to produce a digest from Phase 5 data alone (would lose all prior-phase data).", file=sys.stderr)
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Build digest-input.json from upstream outputs")
    parser.add_argument("input_file", help="JSON file with raw upstream outputs")
    parser.add_argument("--output-file", "-o", required=True, help="Output digest-input.json path")
    parser.add_argument("--merge", help="Merge Phase 5 data into existing digest-input.json at this path")
    parser.add_argument("--scrape-waf-file", help="JSON file from scrape-commits.py for Watch & Fix phase commits")
    parser.add_argument("--scrape-feedback-file", help="JSON file from scrape-commits.py for Address Feedback phase commits")
    parser.add_argument("--thread-state-file", help="JSON file from scrape-threads.py with thread state and addressed_details")
    parser.add_argument("--triage-file", help="JSON file from triage-threads.py output (for Phase 5 triage summary)")
    parser.add_argument("--upstream-fallback", help="Fallback JSON file (upstream-data.json) to rebuild baseline if --merge file is corrupt")
    parser.add_argument("--repo-root", help="Path to git repo for resolving short SHAs via git rev-parse")
    args = parser.parse_args()

    data = load_json_robust(args.input_file, label="input", default=None)
    if not isinstance(data, dict):
        print(f"ERROR: Failed to parse {args.input_file}", file=sys.stderr)
        sys.exit(1)
    data = _clean_thread_payload(data)

    # Normalize flat state keys into expected nested schema
    normalize_upstream(data)

    # Load optional scraped data files — errors are non-fatal (skip with warning)
    scrape_waf = _load_optional_json(args.scrape_waf_file, "scrape-waf")
    scrape_feedback = _load_optional_json(args.scrape_feedback_file, "scrape-feedback")
    thread_state = _load_optional_json(args.thread_state_file, "thread-state")
    triage_output = _load_optional_json(args.triage_file, "triage")
    repo_root = args.repo_root

    if args.merge:
        existing = _load_merge_base(args.merge, args.upstream_fallback, scrape_waf=scrape_waf)
        result = merge_phase5(existing, data, scrape_feedback=scrape_feedback, thread_state=thread_state, triage_output=triage_output, repo_root=repo_root)
    else:
        result = build_digest_input(data, scrape_waf=scrape_waf, repo_root=repo_root)

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Also print summary to stderr for logging
    findings = result.get("findings", {})
    total = len(findings.get("prevalidate", [])) + len(findings.get("watch_fix", [])) + len(findings.get("feedback", []))
    print(f"Built digest-input.json: {total} findings, verdict={result.get('verdict')}, engine={result.get('review_engine')}", file=sys.stderr)

if __name__ == "__main__":
    main()
