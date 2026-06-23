#!/usr/bin/env python3
"""Group PR comments by file and pair with violations for parallel classification.

This script is Phase 1 of the replay analysis classification pipeline.
It produces deterministic batches: same inputs always produce same outputs.

Usage:
    python group_comments.py \
        --comments <pr_comments.json> \
        --violations <all_violations.json> \
        --output <classify-batches.json> \
        [--max-per-batch 8]
"""

import argparse
import json
import os
import pathlib
import sys


def _vfile(v):
    """Get file basename from a violation (handles 'file_name' or 'file' keys)."""
    return os.path.basename(v.get("file_name") or v.get("file") or "")


def deduplicate_violations(violations: list) -> list:
    """Deduplicate violations by (basename, startline, guideline)."""
    seen = set()
    unique = []
    for v in violations:
        key = (
            _vfile(v),
            str(v.get("startline", "")),
            v.get("guideline", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def group_by_file(comments: list) -> dict:
    """Group comments by file basename, sorted deterministically."""
    groups = {}
    def _file(x):
        return x.get("file_path") or x.get("file") or ""

    for c in sorted(
        comments, key=lambda x: (os.path.basename(_file(x)), x.get("line_number") or 0)
    ):
        basename = os.path.basename(_file(c))
        groups.setdefault(basename, []).append(c)
    return groups


def build_batches(
    file_groups: dict, unique_violations: list, max_per_batch: int
) -> tuple:
    """Build classification batches. Returns (batches, no_violation_comment_ids)."""
    violation_basenames = set(
        _vfile(v) for v in unique_violations
    )

    batches = []
    no_violation_ids = []
    batch_num = 1

    for basename in sorted(file_groups.keys()):
        group_comments = file_groups[basename]

        # Find all violations for this file
        file_violations = sorted(
            [
                v
                for v in unique_violations
                if _vfile(v) == basename
            ],
            key=lambda v: int(v.get("startline") or 0),
        )

        # Track comments on files with no violations
        if basename not in violation_basenames:
            for c in group_comments:
                no_violation_ids.append(c.get("comment_id", ""))
            continue

        # Split into chunks if needed
        for i in range(0, len(group_comments), max_per_batch):
            chunk = group_comments[i : i + max_per_batch]
            batches.append(
                {
                    "batch_id": f"classify-{batch_num:03d}",
                    "file": basename,
                    "comments": chunk,
                    "violations": file_violations,
                }
            )
            batch_num += 1

    return batches, no_violation_ids


def main():
    parser = argparse.ArgumentParser(description="Group PR comments for classification")
    parser.add_argument("--comments", required=True, help="Path to PR comments JSON")
    parser.add_argument(
        "--violations", required=True, help="Path to all-violations JSON"
    )
    parser.add_argument("--output", required=True, help="Output path for batches JSON")
    parser.add_argument(
        "--max-per-batch",
        type=int,
        default=8,
        help="Max comments per batch (default: 8)",
    )
    args = parser.parse_args()

    # Load inputs
    comments = json.loads(
        pathlib.Path(args.comments).read_text(encoding="utf-8-sig")
    )
    violations = json.loads(
        pathlib.Path(args.violations).read_text(encoding="utf-8-sig")
    )

    # Process
    unique_violations = deduplicate_violations(violations)
    file_groups = group_by_file(comments)
    batches, no_violation_ids = build_batches(
        file_groups, unique_violations, args.max_per_batch
    )

    # Write output
    output = {
        "batches": batches,
        "total_comments": len(comments),
        "total_batches": len(batches),
        "unique_files": len(file_groups),
        "unique_violations": len(unique_violations),
        "no_violation_comment_ids": no_violation_ids,
    }

    pathlib.Path(args.output).write_text(
        json.dumps(output, indent=2, default=str), encoding="utf-8"
    )

    print(
        f"Created {len(batches)} batches from {len(file_groups)} files, "
        f"{len(comments)} comments, {len(unique_violations)} unique violations"
    )
    if no_violation_ids:
        print(
            f"  {len(no_violation_ids)} comments on files with no violations (auto-MISSED)"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())