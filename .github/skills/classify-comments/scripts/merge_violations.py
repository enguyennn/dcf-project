#!/usr/bin/env python3
"""Load, merge, and deduplicate Gatekeeper violations from per-iteration reports.

This script handles Steps 1 and 2 of the replay analysis pipeline:
- Step 1: Load and merge all iteration final-review.json files
- Step 2: Deduplicate violations by (file_name, startline, guideline),
  keeping the earliest iteration and tracking iteration_count.

Usage:
    python merge_violations.py \
        --iteration-dir <replay_output_dir> \
        --output <all_violations.json> \
        [--summary <merge_summary.json>]

    Or with explicit file paths:
    python merge_violations.py \
        --files <iter5/final-review.json> <iter9/final-review.json> ... \
        --output <all_violations.json>
"""

import argparse
import json
import os
import pathlib
import re
import sys


def discover_iteration_reports(iteration_dir: str) -> list:
    """Find all iteration-*/final-review.json files, sorted by iteration ID."""
    base = pathlib.Path(iteration_dir)
    reports = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and re.match(r"iteration-\d+", d.name):
            review_file = d / "final-review.json"
            if review_file.exists():
                # Extract iteration number for sorting
                m = re.search(r"\d+", d.name)
                iter_num = int(m.group()) if m else 0
                reports.append((iter_num, review_file))
    reports.sort(key=lambda x: x[0])
    return reports


def _normalize_guideline(guideline: str) -> str:
    """Extract short guideline name from a full path or SKILL.md reference.

    Handles:
      - Full paths: ``D:\\...\\skills\\dead-code-not-removed\\SKILL.md`` -> ``dead-code-not-removed``
      - Relative paths: ``skills/dead-code-not-removed/SKILL.md`` -> ``dead-code-not-removed``
      - Already short: ``dead-code-not-removed`` -> ``dead-code-not-removed``
    """
    if not guideline:
        return guideline
    # Strip SKILL.md suffix then take the last path component
    cleaned = re.sub(r"[/\\]SKILL\.md$", "", guideline, flags=re.IGNORECASE)
    return os.path.basename(cleaned)


def load_and_merge(reports: list) -> dict:
    """Load all reports and merge violations, guidelines, and files."""
    all_violations = []
    all_guidelines = set()
    all_files = set()
    iteration_violation_counts = {}

    for iter_num, report_path in reports:
        data = json.loads(report_path.read_text(encoding="utf-8-sig"))

        violations = data.get("violations", [])
        for v in violations:
            v["_source_iteration"] = iter_num
            # Normalize file_name to basename and guideline to short name
            if v.get("file_name"):
                v["file_name"] = os.path.basename(v["file_name"])
            if v.get("guideline"):
                v["guideline"] = _normalize_guideline(v["guideline"])
            all_violations.append(v)

        iteration_violation_counts[iter_num] = len(violations)

        gr = data.get("guidelines_reviewed", [])
        if isinstance(gr, list):
            for g in gr:
                all_guidelines.add(g)

        fr = data.get("files_reviewed", [])
        if isinstance(fr, list):
            for f in fr:
                all_files.add(f)

    return {
        "all_violations": all_violations,
        "guidelines_reviewed": sorted(all_guidelines),
        "files_reviewed": sorted(all_files),
        "iteration_violation_counts": iteration_violation_counts,
    }


def deduplicate(violations: list) -> list:
    """Deduplicate by (basename, startline, guideline). Keep earliest iteration."""
    seen = {}
    for v in sorted(violations, key=lambda x: x.get("_source_iteration", 0)):
        basename = os.path.basename(v.get("file_name", ""))
        key = (basename, str(v.get("startline", "")), v.get("guideline", ""))
        if key not in seen:
            v["iteration_count"] = 1
            seen[key] = v
        else:
            seen[key]["iteration_count"] = seen[key].get("iteration_count", 1) + 1
    return sorted(
        seen.values(),
        key=lambda v: (
            os.path.basename(v.get("file_name", "")),
            int(v.get("startline") or 0),
        ),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Merge and deduplicate Gatekeeper iteration reports"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--iteration-dir",
        help="Directory containing iteration-*/ subdirectories with final-review.json",
    )
    group.add_argument(
        "--files", nargs="+", help="Explicit list of final-review.json file paths"
    )
    parser.add_argument(
        "--output", required=True, help="Output path for merged violations JSON"
    )
    parser.add_argument(
        "--summary", help="Optional output path for merge summary JSON"
    )
    args = parser.parse_args()

    # Discover or parse report paths
    if args.iteration_dir:
        reports = discover_iteration_reports(args.iteration_dir)
    else:
        reports = []
        for f in args.files:
            p = pathlib.Path(f)
            match = re.search(r"iteration-(\d+)", str(p))
            iter_num = int(match.group(1)) if match else len(reports) + 1
            reports.append((iter_num, p))
        reports.sort(key=lambda x: x[0])

    if not reports:
        print("ERROR: No iteration reports found.", file=sys.stderr)
        return 1

    # Step 1: Load and merge
    merged = load_and_merge(reports)
    total_raw = len(merged["all_violations"])

    # Step 2: Deduplicate
    unique = deduplicate(merged["all_violations"])

    # Write merged violations
    pathlib.Path(args.output).write_text(
        json.dumps(unique, indent=2, default=str), encoding="utf-8"
    )

    # Write summary if requested
    if args.summary:
        summary = {
            "iterations_processed": len(reports),
            "iteration_ids": [r[0] for r in reports],
            "total_violations_raw": total_raw,
            "unique_violations": len(unique),
            "duplicates_removed": total_raw - len(unique),
            "guidelines_reviewed": merged["guidelines_reviewed"],
            "total_guidelines": len(merged["guidelines_reviewed"]),
            "files_reviewed": merged["files_reviewed"],
            "total_files": len(merged["files_reviewed"]),
            "iteration_violation_counts": merged["iteration_violation_counts"],
        }
        pathlib.Path(args.summary).write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    print(
        f"Merged {len(reports)} iterations: {total_raw} raw violations -> "
        f"{len(unique)} unique ({total_raw - len(unique)} duplicates removed)"
    )
    print(
        f"  {len(merged['guidelines_reviewed'])} guidelines, "
        f"{len(merged['files_reviewed'])} files reviewed"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())