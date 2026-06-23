#!/usr/bin/env python3
"""Compose the PR Orchestrator review digest from structured JSON data.

Takes structured input and produces markdown that exactly matches the
review-summary.md template. Guarantees 7-column tables, 5-phase timeline,
5-gate rows. No LLM involved — pure string formatting.

Usage:
    python compose-digest.py input.json
    echo '{"risk": {...}, ...}' | python compose-digest.py

Input: JSON object (see schema below)
Output: Complete digest markdown to stdout

Input schema:
{
  "pr_url": "https://dev.azure.com/.../pullrequest/123 or https://github.com/.../pull/123",
  "risk": {
    "level": "low|medium|high",
    "signals": "description string",
    "review_requirement": "AI review sufficient — human review optional"
  },
  "judgment_items": "markdown string or empty",
  "findings": {
    "prevalidate": [
      {"num": 1, "file": "path.cs", "finding": "description", "found_by": "Gatekeeper", "fixed_by": "Auto-fix", "commit_sha": "abc1234", "commit_url": "https://...", "status": "✅ Fixed"}
    ],
    "watch_fix": [],
    "feedback": []
  },
  "timeline": [
    {"phase": "Pre-Validate", "duration": "~8 min", "result": "✅ Complete"}
  ],
  "gates": [
    {"check": "🔍 Lint", "status": "✅ Passed", "details": "No errors"}
  ],
  "verdict": "ready|warnings|changes_needed|running",
  "review_engine": "Gatekeeper|Unavailable",
  "footer_variant": "Phase 4 Review Digest"
}
"""

import json
import re
import sys

from encoding_utils import clean_html, load_json_robust, sanitize_llm_json


RISK_ICONS = {"low": "🟢", "medium": "🟡", "high": "🔴"}
RISK_LABELS = {"low": "Low", "medium": "Medium", "high": "High", "unknown": "Not assessed"}
DIGEST_MARKER = "<!-- ai-agent:pr-orchestrator-digest -->"

VERDICT_DISPLAY = {
    "ready": "✅ Ready for review",
    "warnings": "⚠️ Warnings — review recommended",
    "changes_needed": "❌ Changes needed",
    "running": "⏳ Still running",
    "approved": "✅ Approved — all findings addressed",
}


def shorten_path(file_path: str, max_len: int = 40) -> str:
    """Shorten a file path to fit in narrow table columns."""
    if len(file_path) <= max_len:
        return file_path
    # Try removing common prefixes
    short = file_path
    for prefix in ["Frontend/src/CirrusPortal/src/typescripts/", "Frontend/src/", "CirrusPortalAPI/", "CirrusPortalAPI.Tests/"]:
        if short.startswith(prefix):
            short = short[len(prefix):]
            break
    # Strip parenthetical line references for table (they're in the inline comment)
    short = re.sub(r"\s*\(lines?\s+[^)]+\)", "", short)
    # Strip trailing "+ OtherFile.ts (...)" references
    short = re.sub(r"\s*\+\s+\S+.*", "", short)
    if len(short) > max_len:
        short = "…" + short[-(max_len - 1):]
    return short


def strip_html(text: str) -> str:
    """Backward-compatible wrapper for the shared HTML cleaner."""
    return clean_html(text)


def sanitize_markdown_cell(text: str) -> str:
    """Escape and clean text for safe use in a markdown table cell."""
    if not text:
        return ""
    # Safety net for any thread HTML that leaked through upstream ingestion.
    text = clean_html(text)
    # Replace pipes (break table columns)
    text = text.replace("|", "∣")
    # Replace newlines (break table rows)
    text = re.sub(r"\r?\n", " ", text)
    # Collapse repeated whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def format_findings_table(findings: list) -> str:
    """Format a list of findings into a 6-column markdown table."""
    if not findings:
        return ""

    rows = []
    for f in findings:
        commit_sha = f.get("commit_sha", "")
        commit_url = f.get("commit_url", "")
        if commit_url:
            commit_cell = f"[`{commit_sha[:7]}`]({commit_url})"
        elif commit_sha:
            commit_cell = f"`{commit_sha[:7]}`"
        else:
            commit_cell = "—"
        file_short = shorten_path(f.get("file", "—"))
        file_url = f.get("file_url", "")
        file_cell = f"[`{file_short}`]({file_url})" if file_url else f"`{file_short}`"
        finding_text = sanitize_markdown_cell(f.get("finding", "—"))
        rows.append(
            f"| {f.get('num', '')} "
            f"| {file_cell} "
            f"| {finding_text} "
            f"| {f.get('found_by', '—')} "
            f"| {commit_cell} "
            f"| {f.get('status', '—')} |"
        )
    return "\n".join(rows)


def compose(data: dict) -> str:
    """Compose the full digest markdown from structured data."""
    risk = data.get("risk", {})
    risk_level = risk.get("level", "unknown")
    risk_icon = RISK_ICONS.get(risk_level, "⚪")
    risk_label = RISK_LABELS.get(risk_level, "Not assessed")
    risk_req = risk.get("review_requirement", "Not assessed — no risk classification available")
    risk_signals = risk.get("signals", "Not assessed")
    risk_signals_line = "" if risk_level not in RISK_ICONS and risk_signals == "Not assessed" else f">\n> **Signals**: {risk_signals}\n"

    judgment = data.get("judgment_items", "")

    # Auto-generate judgment items from findings with non-fixed status
    # Collect items across all phases with deep links back to source
    judgment_from_findings = []
    findings = data.get("findings", {})
    prevalidate = findings.get("prevalidate", [])
    watch_fix = findings.get("watch_fix", [])
    feedback = findings.get("feedback", [])

    phase_findings = [
        ("Step 1", prevalidate),
        ("Step 3", watch_fix),
        ("Step 5", feedback),
    ]
    judgment_num = 0
    for phase_label, phase_list in phase_findings:
        for f in phase_list:
            raw_status = f.get("status", "")
            if not raw_status:
                print(
                    f"WARNING: finding in {phase_label} has missing 'status' field — defaulting to 'unknown'",
                    file=sys.stderr,
                )
            status = str(raw_status).lower() if raw_status else "unknown"
            if any(kw in status for kw in ["open", "judgment", "needs"]):
                judgment_num += 1
                file_ref = f.get("file", "unknown")
                file_url = f.get("file_url", "")
                view_url = f.get("view_url", file_url)
                desc = sanitize_markdown_cell(
                    f.get("finding", f.get("description", ""))
                )
                file_cell = (
                    f"[`{shorten_path(file_ref)}`]({file_url})"
                    if file_url
                    else f"`{shorten_path(file_ref)}`"
                )
                view_cell = (
                    f"[View →]({view_url})"
                    if view_url
                    else f"§{phase_label}"
                )
                judgment_from_findings.append(
                    f"| {judgment_num} "
                    f"| {phase_label} "
                    f"| {file_cell} "
                    f"| {desc} "
                    f"| {view_cell} |"
                )

    if judgment_from_findings:
        judgment = (
            "| # | Source | File | Issue | Review |\n"
            "|---|--------|------|-------|--------|\n"
            + "\n".join(judgment_from_findings)
        )
    elif not judgment or judgment == "No items requiring human judgment.":
        judgment = "No items requiring human judgment."

    prevalidate_table = format_findings_table(prevalidate)
    if not prevalidate_table:
        prevalidate_table = "No findings in pre-validate."

    # Watch & Fix section
    if watch_fix:
        fix_count = len(watch_fix)
        watch_fix_section = (
            f"**{fix_count} fix commit(s)** were pushed automatically to resolve CI failures:\n"
            f"| # | File | Finding | Found By | Commit | Status |\n"
            f"|---|------|---------|----------|--------|--------|\n"
            f"{format_findings_table(watch_fix)}"
        )
    else:
        watch_fix_section = "CI passed on the first attempt — no fixes needed."

    # Feedback section — always show triage summary + findings table if any
    triage = data.get("triage_summary", {})
    triage_total = triage.get("total", 0)
    triage_actionable = triage.get("actionable", 0)
    triage_skipped = triage.get("skipped", 0)
    triage_reasons = triage.get("skip_reasons", {})

    feedback_parts = []
    if triage_total > 0:
        feedback_parts.append(
            f"Triaged **{triage_total}** thread(s): "
            f"**{triage_actionable}** actionable, **{triage_skipped}** skipped"
        )
        if triage_reasons:
            reason_strs = [f"{reason} ({count})" for reason, count in sorted(triage_reasons.items(), key=lambda x: -x[1])]
            feedback_parts.append(f"Skipped reasons: {', '.join(reason_strs)}")
    elif not feedback:
        feedback_parts.append("No review feedback received.")

    if feedback:
        feedback_parts.append(
            f"| # | File | Finding | Found By | Commit | Status |\n"
            f"|---|------|---------|----------|--------|--------|\n"
            f"{format_findings_table(feedback)}"
        )

    feedback_section = "\n".join(feedback_parts) if feedback_parts else "No review feedback received."

    # Timeline — always 5 rows
    timeline = data.get("timeline", [])
    default_phases = ["Pre-Validate", "Create PR", "Watch & Fix CI", "Review Digest", "Address Feedback"]
    timeline_rows = []
    for phase_name in default_phases:
        row = next((t for t in timeline if t.get("phase", "").lower() == phase_name.lower()), None)
        if row:
            timeline_rows.append(f"| {row['phase']} | {row.get('duration', '⏳ Pending')} | {row.get('result', '⏳ Pending')} |")
        else:
            timeline_rows.append(f"| {phase_name} | ⏳ Pending | ⏳ Pending |")
    timeline_table = "\n".join(timeline_rows)
    total_duration = data.get("total_duration", "—")

    # Gates — 2 rows (Code Review + CI Build)
    gates = data.get("gates", [])
    review_engine = data.get("review_engine", "Gatekeeper")
    default_gates = [
        (f"🔍 Code Review ({review_engine})", "code_review"),
        ("🔨 Build (CI)", "build"),
    ]
    gate_rows = []
    for display_name, key in default_gates:
        gate = next((g for g in gates if key in g.get("check", "").lower().replace(" ", "_")), None)
        if gate:
            gate_rows.append(f"| {gate['check']} | {gate.get('status', '⏳')} | {gate.get('details', '—')} |")
        else:
            gate_rows.append(f"| {display_name} | ⏳ Pending | — |")
    gate_table = "\n".join(gate_rows)

    verdict = data.get("verdict", "running")
    verdict_display = VERDICT_DISPLAY.get(verdict, verdict)

    # Advisory (removed — only render if somehow present for back-compat)
    advisory = data.get("advisory", [])
    if advisory:
        advisory_rows = "\n".join(
            f"| {a.get('check', '—')} | {a.get('findings', '—')} |"
            for a in advisory
        )
        advisory_section = f"""<details>
<summary>🛡️ AI Advisory</summary>

| Check | Findings |
|-------|----------|
{advisory_rows}

</details>"""
    else:
        advisory_section = ""

    footer_variant = data.get("footer_variant", "Phase 4 Review Digest")

    # Assemble the full digest
    digest = f"""{DIGEST_MARKER}
# PR Orchestrator — Review Digest

> _Single summary of all automated validation for human reviewers._

## Risk Level: {risk_icon} {risk_label}

> {risk_req}
{risk_signals_line}
## 👁️ Needs Your Judgment
{judgment}

## 🔧 What Was Fixed

> _Every finding tracked end-to-end. Click File to see the inline comment, click Commit to see the fix diff._

#### Pre-Validate (Step 1)

| # | File | Finding | Found By | Commit | Status |
|---|------|---------|----------|--------|--------|
{prevalidate_table}

#### Watch & Fix CI (Step 3)

{watch_fix_section}

#### Address Review Feedback (Step 5)

{feedback_section}

## Validation Timeline

| Phase | Duration | Result |
|-------|----------|--------|
{timeline_table}

**Total elapsed**: {total_duration}

## ✅ Mechanically Verified

| Check | Status | Details |
|-------|--------|---------|
{gate_table}

**Verdict: {verdict_display}**
{f"{chr(10)}{advisory_section}" if advisory_section else ""}

---

<sub>Generated by [PR Orchestrator](https://github.com/azure-core/octane) — {footer_variant}</sub>
"""
    return digest


def main():
    import argparse as _ap
    parser = _ap.ArgumentParser(description="Compose PR Orchestrator review digest")
    parser.add_argument("input_file", nargs="?", help="JSON input file (reads stdin if omitted)")
    parser.add_argument("--output-file", "-o", help="Write output to file instead of stdout (avoids PowerShell encoding issues)")
    args = parser.parse_args()

    if args.input_file:
        data = load_json_robust(args.input_file, label="compose-input", default=None)
    else:
        try:
            data = json.loads(sanitize_llm_json(sys.stdin.read()))
        except json.JSONDecodeError as exc:
            print(f"ERROR: Invalid JSON on stdin: {exc}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(data, dict):
        raise SystemExit("compose-digest.py expected a JSON object")

    digest = compose(data)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(digest)
    else:
        # Ensure UTF-8 output on Windows
        sys.stdout.reconfigure(encoding="utf-8")
        print(digest)


if __name__ == "__main__":
    main()
