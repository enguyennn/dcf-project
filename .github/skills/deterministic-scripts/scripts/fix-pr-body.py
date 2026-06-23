#!/usr/bin/env python3
"""Post-process PR body to enforce template structure deterministically.

After Phase 2, the LLM may have deviated from the pr-body.md template —
wrong digest link placement, missing sections, short descriptions.  This
script extracts the LLM-written Intent and Changes content, then rebuilds
the body from the canonical template with deterministic gate data.

Usage:
    python fix-pr-body.py --state-file state.json --pr-body-file body.md
    python fix-pr-body.py --state-file state.json --pr-body-file body.md --output-file fixed.md

The script is a pure data transformation — no side effects (no API calls).
The caller (run-phases.py) handles fetching/updating the PR.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

try:
    from phase_contracts import read_phase_output
except ImportError:  # pragma: no cover - backward-compatible fallback
    _FALLBACK_PHASE_ALIASES = {
        "1a": {"test_count": "tests_run"},
    }
    _FALLBACK_PHASE_KEYS = {
        "1a": ["tests_run", "tests_passed", "tests_failed"],
        "1c": ["code_review_findings"],
        "2": ["pr_title", "work_items_linked"],
    }

    def read_phase_output(state: dict, phase_id: str) -> dict | None:
        if not isinstance(state, dict):
            return None
        phases = state.get("_phases", {})
        raw = {}
        if isinstance(phases, dict) and isinstance(phases.get(phase_id), dict):
            raw = dict(phases[phase_id])
        else:
            for key in _FALLBACK_PHASE_KEYS.get(phase_id, []):
                if key in state:
                    raw[key] = state[key]
            for key in _FALLBACK_PHASE_ALIASES.get(phase_id, {}):
                if key in state:
                    raw[key] = state[key]
            if not raw:
                return None
        for alias_key, canonical_key in _FALLBACK_PHASE_ALIASES.get(phase_id, {}).items():
            if alias_key in raw:
                raw.setdefault(canonical_key, raw[alias_key])
                raw.pop(alias_key, None)
        return raw



def _phase_output(state: dict, phase_id: str) -> dict:
    phase_data = read_phase_output(state, phase_id)
    return dict(phase_data) if isinstance(phase_data, dict) else {}


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

def extract_section(body: str, heading: str) -> str:
    """Extract content under a markdown ## heading until the next ## or end.

    Case-insensitive heading match.  Returns empty string if not found.
    """
    # Match ## heading (with optional leading whitespace)
    pattern = re.compile(
        rf"^\s*##\s+{re.escape(heading)}\b.*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(body)
    if not m:
        return ""

    start = m.end()
    # Find next ## heading
    next_heading = re.search(r"^\s*##\s+", body[start:], re.MULTILINE)
    if next_heading:
        end = start + next_heading.start()
    else:
        # Find horizontal rule or footer
        footer = re.search(r"^---\s*$", body[start:], re.MULTILINE)
        end = start + footer.start() if footer else len(body)

    content = body[start:end].strip()

    # Remove the blockquote hint line if the LLM copied it from the template
    content = re.sub(
        r"^>\s*_(?:What does this change accomplish|Logical grouping).*?_\s*$",
        "",
        content,
        flags=re.MULTILINE,
    ).strip()

    return content


def extract_pr_title(body: str) -> str:
    """Extract PR title from # heading at top of body."""
    m = re.search(r"^\s*#\s+(.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_digest_url(body: str) -> Optional[str]:
    """Extract any digest URL the LLM may have inserted (instead of placeholder)."""
    # Match markdown link with URL
    m = re.search(r"\[.*?[Dd]igest.*?\]\((https?://[^\s)]+)\)", body)
    if m:
        url = m.group(1)
        if "DIGEST_LINK_PLACEHOLDER" not in url:
            return url
    # Match raw URL near "digest" text
    m = re.search(r"(?:digest|review).*?(https?://\S+)", body, re.IGNORECASE)
    if m:
        url = m.group(1).rstrip(")")
        if "DIGEST_LINK_PLACEHOLDER" not in url:
            return url
    return None



def build_code_review_oneliner(state: dict) -> str:
    """Build compact code review summary from state."""
    phase_1c = _phase_output(state, "1c")
    cr = phase_1c.get("code_review_findings", {})
    if isinstance(cr, str):
        try:
            cr = json.loads(cr)
        except (json.JSONDecodeError, TypeError):
            cr = {}

    if not isinstance(cr, dict):
        return "No review data"

    engine = str(cr.get("review_engine", "")).strip().lower()
    if engine == "unavailable":
        return "⚠️ No review engine available"

    # Try to count from findings
    total = 0
    for key in ("important", "Important", "critical", "Critical",
                "suggestion", "Suggestion", "suggestions", "medium",
                "Medium", "low", "Low", "high", "High"):
        items = cr.get(key, [])
        if isinstance(items, list):
            total += len(items)
        nested = cr.get("findings", {})
        if isinstance(nested, dict):
            items2 = nested.get(key, [])
            if isinstance(items2, list):
                total += len(items2)

    if total == 0:
        return "✅ No issues"

    return f"⚠️ {total} finding(s)"


def build_test_summary(state: dict) -> str:
    """Build test summary from state."""
    phase_1a = _phase_output(state, "1a")
    run_count = phase_1a.get("tests_run", "—")
    passed = phase_1a.get("tests_passed", "—")
    failed = phase_1a.get("tests_failed", "0")
    return f"{run_count} run, {passed} passed, {failed} failed"


# ---------------------------------------------------------------------------
# Template assembly
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE = """\
<!-- pr-orchestrator -->
# {pr_title}

> 📋 **[Review Digest]({digest_link})** — Shows what requires human judgment, what was mechanically fixed by agents with evidence, and all automated gate results.

## Intent

> _What does this change accomplish and why?_

{intent}

## Changes

> _Logical grouping of changes, not a file-by-file list._

{changes}

## Validation

**Tests**: {tests}
**Code Review**: {code_review}

### Related Work Items

{work_items}

---

<sub>Generated by [PR Orchestrator](https://github.com/azure-core/octane) — Phase 2</sub>
"""


def fix_pr_body(
    llm_body: str,
    state: dict,
    template: Optional[str] = None,
    pr_title_override: Optional[str] = None,
) -> str:
    """Rebuild PR body from template with LLM content + deterministic data.

    Args:
        llm_body: The PR description written by the Phase 2 LLM agent.
        state: Cross-phase state dict (for gate data, PR title, etc.).
        template: Optional pr-body.md template.  Uses built-in default if None.
        pr_title_override: Force a specific PR title.

    Returns:
        The corrected PR body string.
    """
    # Extract LLM-written content
    intent = extract_section(llm_body, "Intent")
    changes = extract_section(llm_body, "Changes")

    # Fallbacks: if sections not found, try to extract meaningful content
    if not intent:
        # Try "Summary" or "Description" sections
        intent = extract_section(llm_body, "Summary") or extract_section(llm_body, "Description")
    if not intent:
        # Try business_logic_digest from state (Phase 1a output)
        phase_1a = _phase_output(state, "1a")
        bld = phase_1a.get("business_logic_digest", "")
        if bld and len(bld) > 20:
            # Use the first paragraph as intent
            first_para = bld.split("\n\n")[0].strip()
            if first_para:
                intent = first_para
    if not intent:
        # Last resort: use the whole body minus boilerplate as intent
        # Strip known template parts
        stripped = re.sub(r"<!--.*?-->", "", llm_body, flags=re.DOTALL)
        stripped = re.sub(r"^#\s+.*$", "", stripped, flags=re.MULTILINE)
        stripped = re.sub(r"^---\s*$.*", "", stripped, flags=re.DOTALL | re.MULTILINE)
        stripped = re.sub(r"<sub>.*?</sub>", "", stripped, flags=re.DOTALL)
        stripped = re.sub(r"^>\s*.*$", "", stripped, flags=re.MULTILINE)
        stripped = re.sub(r"^\|.*\|$", "", stripped, flags=re.MULTILINE)
        stripped = stripped.strip()
        if stripped:
            intent = stripped

    if not changes:
        # Try "Modifications" or "What Changed"
        changes = extract_section(llm_body, "Modifications") or extract_section(llm_body, "What Changed")
    if not changes:
        # Try business_logic_digest from state for changes
        phase_1a = _phase_output(state, "1a")
        bld = phase_1a.get("business_logic_digest", "")
        if bld:
            # Use all but first paragraph as changes description
            paragraphs = [p.strip() for p in bld.split("\n\n") if p.strip()]
            if len(paragraphs) > 1:
                changes = "\n\n".join(paragraphs[1:])
    if not changes:
        changes = "_See commit diff for details._"

    # PR title
    phase_2 = _phase_output(state, "2")
    pr_title = pr_title_override or extract_pr_title(llm_body) or phase_2.get("pr_title") or "Pull Request"

    # Digest link: preserve placeholder for Phase 4 to replace
    # If the LLM already inserted a real URL, capture it but still use placeholder
    # so Phase 4 can replace uniformly
    digest_link = "DIGEST_LINK_PLACEHOLDER"

    tests = build_test_summary(state)
    code_review = build_code_review_oneliner(state)

    # Work items
    work_items = phase_2.get("work_items_linked", "None")
    if isinstance(work_items, list):
        work_items = ", ".join(str(w) for w in work_items) if work_items else "None"
    if not work_items:
        work_items = "None"

    # Use template or default
    tmpl = template if template else _DEFAULT_TEMPLATE

    # Replace template placeholders
    body = tmpl.format(
        pr_title=pr_title,
        digest_link=digest_link,
        intent=intent,
        changes=changes,
        tests=tests,
        code_review=code_review,
        work_items=work_items,
    )

    return body


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fix PR body to enforce template structure")
    parser.add_argument("--state-file", required=True, help="Path to cross-phase state JSON")
    parser.add_argument("--pr-body-file", required=True, help="Path to file with LLM-written PR body")
    parser.add_argument("--template-file", default=None, help="Path to pr-body.md template (optional)")
    parser.add_argument("--pr-title", default=None, help="Override PR title")
    parser.add_argument("--output-file", default=None, help="Write output to file instead of stdout")
    args = parser.parse_args()

    # Read inputs
    state_path = Path(args.state_file)
    if not state_path.exists():
        print(f"Error: state file not found: {state_path}", file=sys.stderr)
        sys.exit(1)

    state = json.loads(state_path.read_text(encoding="utf-8"))

    body_path = Path(args.pr_body_file)
    if not body_path.exists():
        print(f"Error: PR body file not found: {body_path}", file=sys.stderr)
        sys.exit(1)

    llm_body = body_path.read_text(encoding="utf-8")

    template = None
    if args.template_file:
        tmpl_path = Path(args.template_file)
        if tmpl_path.exists():
            template = tmpl_path.read_text(encoding="utf-8")

    # Fix
    fixed = fix_pr_body(llm_body, state, template=template, pr_title_override=args.pr_title)

    # Output
    if args.output_file:
        Path(args.output_file).write_text(fixed, encoding="utf-8")
        print(f"Fixed PR body written to {args.output_file}", file=sys.stderr)
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.write(fixed)


if __name__ == "__main__":
    main()
