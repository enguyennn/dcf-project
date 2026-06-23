#!/usr/bin/env python3
"""Merge per-iteration replay-analysis.json files into a unified report.

After the parallel replay pipeline produces per-iteration analysis results,
this script combines them into a single unified replay-analysis.json and
replay-analysis-report.md with the same schema as the whole-PR analysis.

Usage:
    python merge_iteration_analyses.py \
        --iteration-dir <replay_output_dir> \
        --output-dir <output_dir> \
        [--pr-url <url>] [--pr-title <title>] [--platform <platform>]
"""

import argparse
import json
import os
import pathlib
import re
import sys
from collections import Counter
from datetime import datetime, timezone


def discover_iteration_analyses(iteration_dir: str) -> list:
    """Find all iteration-*/replay-analysis.json files, sorted by iteration ID."""
    base = pathlib.Path(iteration_dir)
    analyses = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and re.match(r"iteration-\d+", d.name):
            analysis_file = d / "replay-analysis.json"
            if analysis_file.exists():
                iter_num = int(re.search(r"\d+", d.name).group())
                analyses.append((iter_num, analysis_file))
    analyses.sort(key=lambda x: x[0])
    return analyses


def merge_analyses(analyses: list) -> dict:
    """Merge per-iteration replay-analysis.json files into unified data."""
    all_classifications = []
    all_gaps_by_type = Counter()
    all_gaps_by_file = Counter()
    all_suggested = []

    total_violations_raw = 0
    unique_violations = 0
    total_guidelines = set()
    total_files = set()
    iterations_reviewed = 0

    for iter_num, path in analyses:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        iterations_reviewed += 1

        # Collect classifications
        classifications = data.get("comment_classifications", [])
        all_classifications.extend(classifications)

        # Collect gap info
        gaps = data.get("gaps", {})
        for t, n in gaps.get("missed_by_type", {}).items():
            all_gaps_by_type[t] += n
        for f, n in gaps.get("missed_by_file", {}).items():
            all_gaps_by_file[f] += n
        for sg in gaps.get("suggested_guidelines", []):
            all_suggested.append(sg)

        # Collect violation/guideline/file counts from summary
        summary = data.get("summary", {})
        total_violations_raw += summary.get("total_gk_violations", 0)
        unique_violations += summary.get("unique_gk_violations", 0)

        # Collect guideline and file names if available
        if "guidelines_reviewed" in summary:
            val = summary["guidelines_reviewed"]
            if isinstance(val, list):
                total_guidelines.update(val)
        if "files_reviewed" in summary:
            val = summary["files_reviewed"]
            if isinstance(val, list):
                total_files.update(val)

    return {
        "classifications": all_classifications,
        "iterations_reviewed": iterations_reviewed,
        "total_violations_raw": total_violations_raw,
        "unique_violations": unique_violations,
        "total_guidelines": len(total_guidelines) if total_guidelines else 0,
        "total_files": len(total_files) if total_files else 0,
        "gaps_by_type": dict(all_gaps_by_type.most_common()),
        "gaps_by_file": dict(all_gaps_by_file.most_common()),
        "suggested_guidelines": all_suggested,
    }


def _safe_line(val) -> int:
    """Parse a line number that may be a range like '242-243'."""
    s = str(val).split("-")[0].strip() if val else "0"
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


def compute_metrics(classifications: list) -> dict:
    """Calculate coverage metrics from merged classifications."""
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


def deduplicate_suggested_guidelines(suggested: list) -> list:
    """Deduplicate suggested guidelines by theme, summing counts."""
    by_theme = {}
    for sg in suggested:
        theme = sg.get("theme", "unknown")
        if theme not in by_theme:
            by_theme[theme] = {
                "theme": theme,
                "missed_comment_count": 0,
                "examples": [],
            }
        by_theme[theme]["missed_comment_count"] += sg.get("missed_comment_count", 0)
        for ex in sg.get("examples", []):
            if ex not in by_theme[theme]["examples"]:
                by_theme[theme]["examples"].append(ex)
                if len(by_theme[theme]["examples"]) >= 5:
                    break

    return sorted(
        by_theme.values(),
        key=lambda x: -x["missed_comment_count"],
    )


def generate_json_report(
    classifications, metrics, merged, pr_metadata
) -> dict:
    """Generate the unified JSON report."""
    merge_summary = {
        "iterations_processed": merged["iterations_reviewed"],
        "total_violations_raw": merged["total_violations_raw"],
        "unique_violations": merged["unique_violations"],
        "total_guidelines": merged["total_guidelines"],
        "total_files": merged["total_files"],
    }

    return {
        "pr_link": pr_metadata.get("url", ""),
        "pr_title": pr_metadata.get("title", ""),
        "platform": pr_metadata.get("platform", ""),
        "analysis_timestamp": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "iterations_reviewed": merged["iterations_reviewed"],
        "summary": {
            **metrics,
            "total_gk_violations": merged["total_violations_raw"],
            "unique_gk_violations": merged["unique_violations"],
            "guidelines_reviewed": merged["total_guidelines"],
            "files_reviewed": merged["total_files"],
        },
        "comment_classifications": classifications,
        "gaps": {
            "missed_by_type": merged["gaps_by_type"],
            "missed_by_file": merged["gaps_by_file"],
            "suggested_guidelines": deduplicate_suggested_guidelines(
                merged["suggested_guidelines"]
            ),
        },
    }


def generate_md_report(classifications, metrics, merged, pr_metadata) -> str:
    """Generate the unified Markdown report."""
    lines = []

    lines.append("# Gatekeeper Replay Analysis Report\n")
    lines.append("## PR Overview\n")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    title = pr_metadata.get("title", "")
    url = pr_metadata.get("url", "")
    lines.append(f"| **Pull Request** | [{title}]({url}) |")
    lines.append(f"| **Platform** | {pr_metadata.get('platform', '')} |")
    lines.append(f"| **Iterations Reviewed** | {merged['iterations_reviewed']} |")
    lines.append(
        f"| **Analysis Date** | {datetime.now(timezone.utc).strftime('%Y-%m-%d')} |\n"
    )

    # Coverage summary
    actionable = metrics["actionable_comments"]
    total = metrics["total_pr_comments"]
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
        f"> **{metrics['avoidable_pct']}% of actionable PR comments could have been avoided** "
        f"if Gatekeeper had been running."
    )
    lines.append(
        f"> {metrics['caught']} comments ({metrics['caught_pct']}%) were directly CAUGHT.\n"
    )

    # Gatekeeper summary
    lines.append("## Gatekeeper Results Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total Violations Found | {merged['total_violations_raw']} |")
    lines.append(f"| Unique Violations | {merged['unique_violations']} |")
    lines.append(f"| Guidelines Reviewed | {merged['total_guidelines']} |")
    lines.append(f"| Files Reviewed | {merged['total_files']} |\n")

    # CAUGHT table
    caught = [c for c in classifications if c["classification"] == "CAUGHT"]
    lines.append("## CAUGHT — Comments Gatekeeper Would Have Prevented\n")
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
                f"| {c.get('iteration_id', '')} | {cb} | {f} | {c.get('line_number', '')} "
                f"| `{g}` | {c.get('sem', '')} | {c.get('score', '')} | {reason} |"
            )
    else:
        lines.append("No comments were caught.\n")

    # PARTIAL table
    partial = [c for c in classifications if c["classification"] == "PARTIAL"]
    lines.append(f"\n## PARTIAL — Comments With Related Violations\n")
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
                f"| {c.get('iteration_id', '')} | {cb} | {f} | {c.get('line_number', '')} "
                f"| `{g}` | {c.get('sem', '')} | {c.get('score', '')} | {reason} |"
            )
    else:
        lines.append("No comments were partially matched.\n")

    # MISSED table
    missed = [c for c in classifications if c["classification"] == "MISSED"]
    lines.append(f"\n## MISSED — Comments Gatekeeper Did Not Catch\n")
    if missed:
        lines.append("| Iter | Comment | File | Line | Type | Rationale |")
        lines.append("|---:|---|---|---:|---|---|")
        for c in missed:
            f = os.path.basename(str(c.get("file_path", "") or c.get("file", "")))
            cb = str(c.get("comment_body", "")).replace("|", "\\|")
            reason = str(c.get("reason", "")).replace("|", "\\|")
            lines.append(
                f"| {c.get('iteration_id', '')} | {cb} | {f} | {c.get('line_number', '')} "
                f"| {c.get('comment_type', '')} | {reason} |"
            )
    else:
        lines.append("No comments were missed.\n")

    # Gap analysis
    lines.append("\n## Gap Analysis\n")
    if merged["gaps_by_type"]:
        lines.append("### Missed Comment Themes\n")
        lines.append("| Type | Count |")
        lines.append("|---|---:|")
        for t, n in sorted(merged["gaps_by_type"].items(), key=lambda x: -x[1]):
            lines.append(f"| {t} | {n} |")

    if merged["gaps_by_file"]:
        lines.append("\n### Files with Most Misses\n")
        lines.append("| File | Count |")
        lines.append("|---|---:|")
        items = sorted(merged["gaps_by_file"].items(), key=lambda x: -x[1])[:10]
        for f, n in items:
            lines.append(f"| {f} | {n} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Merge per-iteration replay-analysis.json files"
    )
    parser.add_argument(
        "--iteration-dir",
        required=True,
        help="Directory containing iteration-*/ subdirectories with replay-analysis.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write merged reports",
    )
    parser.add_argument("--pr-url", default="", help="PR URL")
    parser.add_argument("--pr-title", default="", help="PR title")
    parser.add_argument("--platform", default="", help="Platform (azure-devops/github)")
    args = parser.parse_args()

    analyses = discover_iteration_analyses(args.iteration_dir)
    if not analyses:
        print("ERROR: No iteration replay-analysis.json files found.", file=sys.stderr)
        return 1

    merged = merge_analyses(analyses)

    # Sort classifications deterministically
    merged["classifications"].sort(
        key=lambda x: (
            int(x.get("iteration_id", 0)),
            os.path.basename(str(x.get("file_path", ""))),
            _safe_line(x.get("line_number", 0)),
        )
    )

    metrics = compute_metrics(merged["classifications"])

    pr_metadata = {
        "url": args.pr_url,
        "title": args.pr_title,
        "platform": args.platform,
    }

    out = pathlib.Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_report = generate_json_report(
        merged["classifications"], metrics, merged, pr_metadata
    )
    (out / "replay-analysis.json").write_text(
        json.dumps(json_report, indent=2, default=str), encoding="utf-8"
    )

    md_report = generate_md_report(
        merged["classifications"], metrics, merged, pr_metadata
    )
    (out / "replay-analysis-report.md").write_text(md_report, encoding="utf-8")

    print(
        f"Merged {len(analyses)} iteration analyses: "
        f"{metrics['caught']} CAUGHT, {metrics['partial']} PARTIAL, "
        f"{metrics['missed']} MISSED, {metrics['out_of_scope']} OOS "
        f"({metrics['avoidable_pct']}% avoidable)"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
