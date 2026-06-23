#!/usr/bin/env python3
"""Merge sub-agent classification results and generate final reports.

This script handles Phase 3, Steps 4-6 of the replay analysis pipeline:
- Phase 3: Merge per-batch classification JSONs, auto-MISS unmatched comments
- Step 4: Calculate coverage metrics
- Step 5: Identify gap patterns
- Step 6: Generate replay-analysis.json and replay-analysis-report.md

Usage:
    python merge_classifications.py \
        --batches <classify-batches.json> \
        --results <results_dir> \
        --comments <pr_comments.json> \
        --violations <all_violations.json> \
        --output-dir <output_dir> \
        [--pr-url <url>] [--pr-title <title>] [--platform <platform>]
"""

import argparse
import json
import os
import pathlib
import sys
from collections import Counter
from datetime import datetime, timezone


def _safe_line(val) -> int:
    """Parse a line number that may be a range like '242-243'."""
    s = str(val).split("-")[0].strip() if val else "0"
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


def _safe_int(val, default: int = 0) -> int:
    """Convert val to int, returning default on error."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _normalize_field_names(cls: dict) -> dict:
    """Normalize alternative field names to canonical schema.

    The CommentClassifier agent spec uses: sem, score, matched_guideline, reason.
    Some sub-agent runtimes return alternatives (e.g. semantic_score, total_score,
    rationale).  This function maps them so merge logic works regardless of which
    schema the sub-agent emitted.
    """
    _ALIASES = {
        "semantic_score": "sem",
        "total_score": "score",
        "proximity_score": "proximity",
        "rationale": "reason",
    }
    for alt, canonical in _ALIASES.items():
        if alt in cls and canonical not in cls:
            cls[canonical] = cls[alt]
    # matched_guideline is the guideline *name*; matched_violation is the
    # violation *description*.  When only matched_violation is present and it
    # looks like a guideline slug (no spaces, kebab-case), treat it as the
    # guideline name.
    if "matched_guideline" not in cls and "matched_violation" in cls:
        mv = cls["matched_violation"]
        if mv and isinstance(mv, str) and " " not in mv:
            cls["matched_guideline"] = mv
    # Normalize comment_id to string for consistent lookups
    if "comment_id" in cls:
        cls["comment_id"] = str(cls["comment_id"])
    return cls


_REQUIRED_FIELDS = {"comment_id", "classification"}


def load_batch_results(results_dir: str) -> list:
    """Load all classify-*.json result files from the results directory."""
    rd = pathlib.Path(results_dir)
    all_classifications = []
    for f in sorted(rd.glob("classify-*.json")):
        data = json.loads(f.read_text(encoding="utf-8-sig"))
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "classifications" in data:
            items = data["classifications"]
        for item in items:
            _normalize_field_names(item)
            missing = _REQUIRED_FIELDS - item.keys()
            if missing:
                print(
                    f"WARNING: {f.name} missing fields {missing} "
                    f"for comment {item.get('comment_id', '?')}",
                    file=sys.stderr,
                )
            all_classifications.append(item)
    return all_classifications


def merge_and_validate(
    classifications: list,
    comments: list,
    no_violation_ids: list,
) -> list:
    """Merge classifications, auto-MISS unmatched, validate completeness."""
    # Build lookup for enriching classifications with comment metadata
    # Normalize comment_id to string for consistent matching
    comment_lookup = {str(c["comment_id"]): c for c in comments}

    # Enrich sub-agent results with metadata from the original comments
    _metadata_fields = (
        "iteration_id",
        "file_path",
        "file",
        "line_number",
        "comment_body",
        "comment_type",
        "author",
    )
    for cls in classifications:
        comment = comment_lookup.get(str(cls["comment_id"]))
        if comment:
            for field in _metadata_fields:
                if field not in cls and field in comment:
                    cls[field] = comment[field]
            # Normalize file_path from 'file' if missing
            if "file_path" not in cls:
                cls["file_path"] = cls.get("file") or comment.get("file") or ""

    classified_ids = {str(c["comment_id"]) for c in classifications}

    # Auto-MISS comments on files with no violations
    for cid in no_violation_ids:
        cid_str = str(cid)
        if cid_str not in classified_ids:
            comment = next((c for c in comments if str(c["comment_id"]) == cid_str), None)
            if comment:
                classifications.append(
                    {
                        "comment_id": cid_str,
                        "iteration_id": comment.get("iteration_id"),
                        "file_path": comment.get("file_path") or comment.get("file", ""),                        "line_number": comment.get("line_number", 0),
                        "comment_body": comment.get("comment_body", ""),
                        "comment_type": comment.get("comment_type", ""),
                        "author": comment.get("author", ""),
                        "sem": 0,
                        "score": 0,
                        "classification": "MISSED",
                        "matched_guideline": None,
                        "matched_violation": None,
                        "reason": "No Gatekeeper violations on this file",
                    }
                )
                classified_ids.add(cid_str)

    # Auto-MISS any remaining unclassified comments (sub-agent failures)
    for c in comments:
        cid_str = str(c["comment_id"])
        if cid_str not in classified_ids:
            classifications.append(
                {
                    "comment_id": cid_str,
                    "iteration_id": c.get("iteration_id"),
                    "file_path": c.get("file_path") or c.get("file", ""),
                    "line_number": c.get("line_number", 0),
                    "comment_body": c.get("comment_body", ""),
                    "comment_type": c.get("comment_type", ""),
                    "author": c.get("author", ""),
                    "sem": 0,
                    "score": 0,
                    "classification": "MISSED",
                    "matched_guideline": None,
                    "matched_violation": None,
                    "reason": "Sub-agent did not return classification",
                }
            )

    # Sort deterministically by iteration_id then line_number
    classifications.sort(
        key=lambda x: (
            _safe_int(x.get("iteration_id", 0)),
            os.path.basename(str(x.get("file_path", ""))),
            _safe_line(x.get("line_number", 0)),
        )
    )

    return classifications


def compute_metrics(classifications: list) -> dict:
    """Step 4: Calculate coverage metrics."""
    counts = Counter(c["classification"] for c in classifications)
    total = len(classifications)
    caught = counts.get("CAUGHT", 0)
    partial = counts.get("PARTIAL", 0)
    missed = counts.get("MISSED", 0)
    oos = counts.get("OUT_OF_SCOPE", 0)
    actionable = caught + partial + missed

    return {
        "total_pr_comments": total,
        "actionable_comments": actionable,
        "caught": caught,
        "partial": partial,
        "missed": missed,
        "out_of_scope": oos,
        "avoidable_pct": round((caught + partial) / actionable * 100, 1)
        if actionable
        else 0,
        "caught_pct": round(caught / actionable * 100, 1) if actionable else 0,
        "overall_coverage_pct": round((caught + partial) / total * 100, 1)
        if total
        else 0,
    }


def identify_gaps(classifications: list) -> dict:
    """Step 5: Identify missed comment patterns."""
    missed = [c for c in classifications if c["classification"] == "MISSED"]

    missed_by_type = Counter(c.get("comment_type", "unknown") for c in missed)
    missed_by_file = Counter(
        os.path.basename(str(c.get("file_path", ""))) for c in missed
    )

    # Group missed themes
    themes = []
    for ctype, count in missed_by_type.most_common(5):
        examples = [
            c["comment_body"][:80]
            for c in missed
            if c.get("comment_type") == ctype
        ][:3]
        themes.append(
            {
                "theme": ctype,
                "missed_comment_count": count,
                "examples": examples,
            }
        )

    return {
        "missed_by_type": dict(missed_by_type.most_common()),
        "missed_by_file": dict(missed_by_file.most_common()),
        "suggested_guidelines": themes,
    }


def generate_json_report(
    classifications, metrics, gaps, violations, pr_metadata, merge_summary
) -> dict:
    """Step 6a: Generate the JSON report."""
    return {
        "pr_link": pr_metadata.get("url", ""),
        "pr_title": pr_metadata.get("title", ""),
        "platform": pr_metadata.get("platform", ""),
        "analysis_timestamp": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "iterations_reviewed": merge_summary.get("iterations_processed", 0),
        "summary": {
            **metrics,
            "total_gk_violations": merge_summary.get("total_violations_raw", 0),
            "unique_gk_violations": merge_summary.get("unique_violations", 0),
            "guidelines_reviewed": merge_summary.get("total_guidelines", 0),
            "files_reviewed": merge_summary.get("total_files", 0),
        },
        "comment_classifications": classifications,
        "gaps": gaps,
    }


def generate_md_report(
    classifications, metrics, gaps, pr_metadata, merge_summary
) -> str:
    """Step 6b: Generate the Markdown report."""
    lines = []

    # Header
    lines.append("# Gatekeeper Replay Analysis Report\n")
    lines.append("## PR Overview\n")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    title = pr_metadata.get("title", "")
    url = pr_metadata.get("url", "")
    lines.append(f"| **Pull Request** | [{title}]({url}) |")
    lines.append(f"| **Platform** | {pr_metadata.get('platform', '')} |")
    lines.append(
        f"| **Iterations Reviewed** | {merge_summary.get('iterations_processed', 0)} |"
    )
    lines.append(
        f"| **Analysis Date** | {datetime.now(timezone.utc).strftime('%Y-%m-%d')} |\n"
    )

    # Coverage summary
    total = metrics["total_pr_comments"]
    actionable = metrics["actionable_comments"]
    lines.append("## Coverage Summary\n")
    lines.append("| Classification | Count | % of Actionable |")
    lines.append("|---|---:|---:|")
    for cls in ["caught", "partial", "missed"]:
        n = metrics[cls]
        pct = round(n / actionable * 100, 1) if actionable else 0
        lines.append(f"| {cls.upper()} | {n} | {pct}% |")
    lines.append(f"| OUT_OF_SCOPE | {metrics['out_of_scope']} | --- |")
    lines.append(f"| **Total** | **{total}** | **100%** |\n")

    lines.append("### Key Finding\n")
    lines.append(
        f"> **{metrics['avoidable_pct']}% of actionable PR comments could have been avoided** if Gatekeeper had been running."
    )
    lines.append(
        f"> {metrics['caught']} comments ({metrics['caught_pct']}%) were directly CAUGHT.\n"
    )

    # Gatekeeper summary
    lines.append("## Gatekeeper Results Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(
        f"| Total Violations Found | {merge_summary.get('total_violations_raw', 0)} |"
    )
    lines.append(
        f"| Unique Violations | {merge_summary.get('unique_violations', 0)} |"
    )
    lines.append(
        f"| Guidelines Reviewed | {merge_summary.get('total_guidelines', 0)} |"
    )
    lines.append(
        f"| Files Reviewed | {merge_summary.get('total_files', 0)} |\n"
    )

    # CAUGHT table
    caught = [c for c in classifications if c["classification"] == "CAUGHT"]
    lines.append("## CAUGHT \u2014 Comments Gatekeeper Would Have Prevented\n")
    if caught:
        lines.append(
            "| Iter | Comment | File | Line | Matched Guideline | Sem | Score | Rationale |"
        )
        lines.append("|---:|---|---|---:|---|---:|---:|---|")
        for c in caught:
            f = os.path.basename(str(c.get("file_path", "") or c.get("file", "")))
            cb = str(c.get("comment_body", "")).replace("|", "\\|")
            g = c.get("matched_guideline", "")
            reason = str(c.get("reason", "")).replace("|", "\\|")
            lines.append(
                f"| {c.get('iteration_id', '')} | {cb} | {f} | {c.get('line_number', '')} | `{g}` | {c.get('sem', '')} | {c.get('score', '')} | {reason} |"
            )
    else:
        lines.append("No comments were caught.\n")

    # PARTIAL table
    partial = [c for c in classifications if c["classification"] == "PARTIAL"]
    lines.append(f"\n## PARTIAL \u2014 Comments With Related Violations\n")
    if partial:
        lines.append(
            "| Iter | Comment | File | Line | Related Guideline | Sem | Score | Rationale |"
        )
        lines.append("|---:|---|---|---:|---|---:|---:|---|")
        for c in partial:
            f = os.path.basename(str(c.get("file_path", "") or c.get("file", "")))
            cb = str(c.get("comment_body", "")).replace("|", "\\|")
            g = c.get("matched_guideline", "")
            reason = str(c.get("reason", "")).replace("|", "\\|")
            lines.append(
                f"| {c.get('iteration_id', '')} | {cb} | {f} | {c.get('line_number', '')} | `{g}` | {c.get('sem', '')} | {c.get('score', '')} | {reason} |"
            )
    else:
        lines.append("No comments were partially matched.\n")

    # MISSED table
    missed = [c for c in classifications if c["classification"] == "MISSED"]
    lines.append(f"\n## MISSED \u2014 Comments Gatekeeper Did Not Catch\n")
    if missed:
        lines.append("| Iter | Comment | File | Line | Type | Rationale |")
        lines.append("|---:|---|---|---:|---|---|")
        for c in missed:
            f = os.path.basename(str(c.get("file_path", "") or c.get("file", "")))
            cb = str(c.get("comment_body", "")).replace("|", "\\|")
            reason = str(c.get("reason", "")).replace("|", "\\|")
            lines.append(
                f"| {c.get('iteration_id', '')} | {cb} | {f} | {c.get('line_number', '')} | {c.get('comment_type', '')} | {reason} |"
            )
    else:
        lines.append("No comments were missed.\n")

    # Gap analysis
    lines.append("\n## Gap Analysis\n")
    if gaps.get("missed_by_type"):
        lines.append("### Missed Comment Themes\n")
        lines.append("| Type | Count |")
        lines.append("|---|---:|")
        for t, n in sorted(gaps["missed_by_type"].items(), key=lambda x: -x[1]):
            lines.append(f"| {t} | {n} |")

    if gaps.get("missed_by_file"):
        lines.append("\n### Files with Most Misses\n")
        lines.append("| File | Count |")
        lines.append("|---|---:|")
        for f, n in sorted(gaps["missed_by_file"].items(), key=lambda x: -x[1])[:10]:
            lines.append(f"| {f} | {n} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Merge classification results and generate reports"
    )
    parser.add_argument(
        "--batches", required=True, help="Path to classify-batches.json"
    )
    parser.add_argument(
        "--results", required=True, help="Directory containing classify-*.json results"
    )
    parser.add_argument(
        "--comments", required=True, help="Path to pr-comments.json"
    )
    parser.add_argument(
        "--violations", required=True, help="Path to all-violations.json"
    )
    parser.add_argument(
        "--merge-summary", help="Path to merge-summary.json (from merge_violations.py)"
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory to write reports"
    )
    parser.add_argument("--pr-url", default="", help="PR URL")
    parser.add_argument("--pr-title", default="", help="PR title")
    parser.add_argument("--platform", default="", help="Platform (azure-devops/github)")
    args = parser.parse_args()

    # Load inputs
    batches_data = json.loads(
        pathlib.Path(args.batches).read_text(encoding="utf-8-sig")
    )
    comments = json.loads(
        pathlib.Path(args.comments).read_text(encoding="utf-8-sig")
    )
    violations = json.loads(
        pathlib.Path(args.violations).read_text(encoding="utf-8-sig")
    )
    merge_summary = {}
    if args.merge_summary:
        ms_path = pathlib.Path(args.merge_summary)
        if ms_path.exists():
            merge_summary = json.loads(ms_path.read_text(encoding="utf-8-sig"))

    no_violation_ids = batches_data.get("no_violation_comment_ids", [])

    # Phase 3: Load and merge sub-agent results
    classifications = load_batch_results(args.results)
    classifications = merge_and_validate(classifications, comments, no_violation_ids)

    # Step 4: Metrics
    metrics = compute_metrics(classifications)

    # Step 5: Gaps
    gaps = identify_gaps(classifications)

    pr_metadata = {
        "url": args.pr_url,
        "title": args.pr_title,
        "platform": args.platform,
    }

    # Step 6: Reports
    out = pathlib.Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_report = generate_json_report(
        classifications, metrics, gaps, violations, pr_metadata, merge_summary
    )
    (out / "replay-analysis.json").write_text(
        json.dumps(json_report, indent=2, default=str), encoding="utf-8"
    )

    md_report = generate_md_report(
        classifications, metrics, gaps, pr_metadata, merge_summary
    )
    (out / "replay-analysis-report.md").write_text(md_report, encoding="utf-8")

    # Summary
    print(
        f"Report: {metrics['caught']} CAUGHT, {metrics['partial']} PARTIAL, "
        f"{metrics['missed']} MISSED, {metrics['out_of_scope']} OOS "
        f"({metrics['avoidable_pct']}% avoidable)"
    )
    missing_count = len(comments) - len(
        {c["comment_id"] for c in classifications}
    )
    if missing_count > 0:
        print(f"  WARNING: {missing_count} comments had no classification result")

    return 0


if __name__ == "__main__":
    sys.exit(main())