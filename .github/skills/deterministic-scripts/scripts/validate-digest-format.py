#!/usr/bin/env python3
"""Validate PR Orchestrator digest format against the review-summary.md template.

Usage:
    python validate-digest-format.py < digest.md
    python validate-digest-format.py digest.md
    echo '...' | python validate-digest-format.py

Output: JSON { "valid": bool, "violations": [...] }
Exit code: 0 if valid, 1 if violations found.
"""

import json
import os
import re
import sys


def read_input():
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if not os.path.exists(path):
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            print(f"ERROR: Could not read {path}: {exc}", file=sys.stderr)
            return None
    return sys.stdin.read()


def count_table_columns(line: str) -> int:
    """Count columns in a markdown table row."""
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return 0
    cells = stripped.split("|")
    # Leading and trailing empty strings from split
    return len(cells) - 2


def validate(content: str) -> list[str]:
    violations = []
    lines = content.split("\n")

    # 1. Sentinel check
    if "<!-- ai-agent:pr-orchestrator-digest -->" not in content:
        violations.append("Missing sentinel: <!-- ai-agent:pr-orchestrator-digest -->")

    # 2. Required section headings (in order)
    required_headings = [
        (r"#\s+PR Orchestrator\s*.{0,3}\s*Review Digest", "# PR Orchestrator — Review Digest"),
        (r"##\s+Risk Level:", "## Risk Level:"),
        (r"##\s+.*Needs Your Judgment", "## 👁️ Needs Your Judgment"),
        (r"##\s+.*What Was Fixed", "## 🔧 What Was Fixed"),
        (r"####?\s+Pre-Validate", "#### Pre-Validate (Step 1)"),
        (r"####?\s+Watch\s*[&\+]\s*Fix", "#### Watch & Fix CI (Step 3)"),
        (r"####?\s+Address\s+Review\s+Feedback", "#### Address Review Feedback (Step 5)"),
        (r"##\s+Validation Timeline", "## Validation Timeline"),
        (r"##\s+.*Mechanically Verified", "## ✅ Mechanically Verified"),
    ]

    last_pos = 0
    for pattern, name in required_headings:
        found = False
        for i in range(last_pos, len(lines)):
            if re.search(pattern, lines[i]):
                last_pos = i + 1
                found = True
                break
        if not found:
            violations.append(f"Missing or out-of-order section: {name}")

    # 3. "What Was Fixed" tables must have 6 columns
    in_what_was_fixed = False
    table_section = None
    for i, line in enumerate(lines):
        if re.search(r"##\s+.*What Was Fixed", line):
            in_what_was_fixed = True
            table_section = None
            continue
        # Exit on any heading at ## or ### level that isn't a sub-section of What Was Fixed
        if in_what_was_fixed and re.search(r"^#{2,3}\s+", line) and "What Was Fixed" not in line:
            # Allow #### sub-headings (Pre-Validate, Watch & Fix, etc.) but exit on ## or ###
            if not line.strip().startswith("####"):
                in_what_was_fixed = False
                table_section = None
                continue

        if in_what_was_fixed and re.search(r"^####\s+", line):
            table_section = line.strip()

        if in_what_was_fixed and line.strip().startswith("|") and table_section:
            # Skip separator rows
            if re.match(r"^\s*\|[\s\-:|]+\|\s*$", line):
                continue
            cols = count_table_columns(line)
            if cols > 0 and cols != 6:
                violations.append(
                    f"Table under '{table_section}' has {cols} columns, expected 6 "
                    f"(# | File | Finding | Found By | Commit | Status) — line {i + 1}"
                )

    # 4. Validation Timeline checks
    timeline_started = False
    phase_rows = 0
    for i, line in enumerate(lines):
        if re.search(r"##\s+Validation Timeline", line):
            timeline_started = True
            continue
        if timeline_started and re.search(r"^##\s+", line):
            timeline_started = False
            continue

        if timeline_started and line.strip().startswith("|"):
            # Skip header and separator
            if re.match(r"^\s*\|\s*Phase\s*\|", line) or re.match(r"^\s*\|[\s\-:|]+\|\s*$", line):
                continue
            phase_rows += 1
            # Check for em-dash durations
            cells = [c.strip() for c in line.strip().split("|")]
            if len(cells) >= 4:
                duration = cells[2]  # Duration is second data column
                if duration == "—" or duration == "–" or duration == "-":
                    violations.append(
                        f"Timeline duration is blank ('{duration}') for row: {cells[1].strip()} — line {i + 1}. "
                        f"Use approximate times (e.g., '~8 min') or '⏳ Pending'."
                    )

    if phase_rows > 0 and phase_rows < 5:
        violations.append(f"Validation Timeline has {phase_rows} phase rows, expected 5")

    # 5. Mechanically Verified table — 2 gate rows (Code Review + CI Build)
    mech_started = False
    gate_rows = 0
    for i, line in enumerate(lines):
        if re.search(r"##\s+.*Mechanically Verified", line):
            mech_started = True
            continue
        if mech_started and re.search(r"^##\s+", line):
            mech_started = False
            continue
        if mech_started and re.search(r"^\*\*Verdict:", line):
            mech_started = False
            continue

        if mech_started and line.strip().startswith("|"):
            if re.match(r"^\s*\|\s*Check\s*\|", line) or re.match(r"^\s*\|[\s\-:|]+\|\s*$", line):
                continue
            gate_rows += 1

    if gate_rows > 0 and gate_rows < 2:
        violations.append(f"Mechanically Verified has {gate_rows} gate rows, expected 2")

    # 6. Footer check
    footer_pattern = r"Generated by \[PR Orchestrator\]"
    if not re.search(footer_pattern, content):
        violations.append("Missing footer: 'Generated by [PR Orchestrator](...)'")

    # 7. Unreplaced template variables
    template_vars = re.findall(r"\{\{[A-Z_]+\}\}", content)
    if template_vars:
        unique_vars = list(set(template_vars))
        violations.append(f"Unreplaced template variables: {', '.join(unique_vars[:5])}")

    return violations


def main():
    content = read_input()
    if content is None:
        result = {"valid": False, "violations": ["Input file not found or unreadable"]}
    elif not content.strip():
        result = {"valid": False, "violations": ["Empty input — no digest content provided"]}
    else:
        viols = validate(content)
        result = {"valid": len(viols) == 0, "violations": viols}

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
