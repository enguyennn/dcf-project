#!/usr/bin/env python3
"""Merge batch code-review results into a unified final report.

Reads per-batch JSON result files produced by code-review agents and
specialist results from the SQL database, then generates:
  - final-review.json   (machine-readable aggregated results)
  - final-review-report.md (human-readable Markdown report)

Usage:
    python merge_reports.py --input-dir <dir> --output-dir <dir>
    python merge_reports.py --input-files f1.json f2.json --output-dir <dir>
    python merge_reports.py --input-files f1.json --db <path> --output-dir <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("merge-reports")


# ---------------------------------------------------------------------------
# Guideline normalization
# ---------------------------------------------------------------------------

# Regex matching common skills-root path prefixes (absolute or relative).
# Captures everything up to and including the skills directory separator.
# Examples matched:
#   D:\a\_work\1\s\.github\skills\  →  stripped
#   /home/runner/work/repo/.github/skills/  →  stripped
#   .github/skills/  →  stripped
#   .github\skills\  →  stripped
_SKILLS_ROOT_PREFIX_RE = re.compile(
    r"^(?:[A-Za-z]:\\|/)?"  # optional drive letter or leading slash
    r"(?:.*?[/\\])?"  # any path prefix
    r"\.github[/\\]skills[/\\]",  # the .github/skills/ anchor
    re.IGNORECASE,
)

# Trailing punctuation that LLMs sometimes append (colons, commas, semicolons).
_TRAILING_PUNCT_RE = re.compile(r"[,:;]+$")


def _normalize_guideline(value: str) -> str:
    """Normalize a guideline identifier to a canonical form.

    Applies generic, repo-agnostic path cleanup:
      1. Strip absolute/relative path prefixes up to the skills root.
      2. Normalize path separators to forward-slash.
      3. Strip trailing punctuation (colons, commas) the LLM may append.
      4. Collapse repeated slashes and strip leading/trailing slashes.

    The result is a relative path from the skills root, e.g.:
      "my-guideline/SKILL.md" or "my-guideline/subdoc.md"
    """
    if not value:
        return value

    # 1. Strip skills-root prefix if present
    s = _SKILLS_ROOT_PREFIX_RE.sub("", value)

    # 2. Normalize path separators
    s = s.replace("\\", "/")

    # 3. Strip trailing punctuation
    s = _TRAILING_PUNCT_RE.sub("", s)

    # 4. Collapse repeated slashes, strip leading/trailing slashes
    s = re.sub(r"/+", "/", s)
    s = s.strip("/")

    return s


def _normalize_violations(violations: list[dict]) -> list[dict]:
    """Normalize guideline fields on all violations in-place."""
    for v in violations:
        guideline = v.get("guideline")
        if isinstance(guideline, str):
            v["guideline"] = _normalize_guideline(guideline)
    return violations


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _collect_input_files(args: argparse.Namespace) -> list[Path]:
    """Return the list of JSON files to process."""
    if args.input_files:
        paths = [Path(f) for f in args.input_files]
    elif args.input_dir:
        input_dir = Path(args.input_dir)
        if not input_dir.is_dir():
            logger.error("Input directory does not exist: %s", input_dir)
            sys.exit(1)
        paths = sorted(input_dir.glob("*.json"))
    else:
        # No batch files — only specialist results from --db
        return []

    return paths


def _load_batch(path: Path) -> dict | None:
    """Load a single batch JSON file, returning *None* on error."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        logger.info("Loaded %s", path)
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None


def _aggregate(batches: list[dict]) -> dict:
    """Merge a list of batch dicts into a single aggregated dict."""
    guidelines: set[str] = set()
    files: set[str] = set()
    violations: list[dict] = []
    non_violations: list[dict] = []
    errors: list[str] = []

    for batch in batches:
        guidelines.update(batch.get("guidelines_reviewed", []))
        files.update(batch.get("files_reviewed", []))
        for item in batch.get("violations", []):
            if isinstance(item, dict):
                violations.append(item)
            else:
                logger.warning("Skipping non-dict violation entry in batch: %s", type(item).__name__)
        for item in batch.get("non_violations", []):
            if isinstance(item, dict):
                non_violations.append(item)
            else:
                logger.warning("Skipping non-dict non_violation entry in batch: %s", type(item).__name__)
        err = batch.get("error")
        if err:
            errors.append(err)

    result: dict = {
        "guidelines_reviewed": sorted(guidelines),
        "files_reviewed": sorted(files),
        "violations": violations,
        "non_violations": non_violations,
    }

    if errors:
        result["errors"] = errors

    return result


def _load_specialist_results(db_path: str) -> tuple[list[dict], list[dict]]:
    """Load specialist reviewer results from the SQL database.

    Returns (completed_results, unavailable_reviewers).
    """
    completed: list[dict] = []
    unavailable: list[dict] = []

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        cursor = conn.execute(
            "SELECT reviewer_name, model, files_reviewed, findings, "
            "non_findings, status, error "
            "FROM gk_specialist_reviews"
        )
        for row in cursor:
            reviewer_name, model, files_json, findings_json, \
                non_findings_json, status, error = row

            if status == "unavailable":
                unavailable.append({
                    "reviewer_name": reviewer_name,
                    "error": error or "Reviewer unavailable",
                })
                continue

            try:
                files = json.loads(files_json) if files_json else []
            except json.JSONDecodeError:
                files = []
            try:
                findings = json.loads(findings_json) if findings_json else []
            except json.JSONDecodeError:
                findings = []
            try:
                non_findings = json.loads(
                    non_findings_json
                ) if non_findings_json else []
            except json.JSONDecodeError:
                non_findings = []

            # Add reviewer attribution to each finding
            for f in findings:
                if isinstance(f, dict):
                    f["reviewer"] = reviewer_name

            completed.append({
                "guidelines_reviewed": [f"{reviewer_name}-review"],
                "files_reviewed": files,
                "violations": findings,
                "non_violations": non_findings,
                "error": error,
            })
    except sqlite3.OperationalError as exc:
        logger.warning(
            "Could not read gk_specialist_reviews: %s", exc
        )
    finally:
        conn.close()

    return completed, unavailable


def _deduplicate_violations(violations: list[dict]) -> list[dict]:
    """Deduplicate violations across reviewers.

    Two findings are duplicates if they share the same file_name AND their
    line ranges overlap (within ±3 lines).
    """
    if not violations:
        return violations

    LINE_TOLERANCE = 3

    def _get_lines(v: dict) -> tuple[int, int]:
        try:
            sl = int(v.get("startline", 0))
        except (ValueError, TypeError):
            sl = 0
        try:
            el = int(v.get("endline", sl))
        except (ValueError, TypeError):
            el = sl
        return sl, el

    def _lines_overlap(
        sl1: int, el1: int, sl2: int, el2: int
    ) -> bool:
        return (
            sl1 <= el2 + LINE_TOLERANCE and sl2 <= el1 + LINE_TOLERANCE
        )

    # Group by file_name
    by_file: dict[str, list[tuple[int, dict]]] = {}
    for idx, v in enumerate(violations):
        fname = v.get("file_name", "")
        by_file.setdefault(fname, []).append((idx, v))

    merged_indices: set[int] = set()
    result: list[dict] = []

    for fname, entries in by_file.items():
        # Find duplicate clusters
        clusters: list[list[int]] = []
        used: set[int] = set()

        for i, (idx_i, vi) in enumerate(entries):
            if idx_i in used:
                continue
            cluster = [idx_i]
            si, ei = _get_lines(vi)

            for j in range(i + 1, len(entries)):
                idx_j, vj = entries[j]
                if idx_j in used:
                    continue
                sj, ej = _get_lines(vj)
                if _lines_overlap(si, ei, sj, ej):
                    cluster.append(idx_j)
                    used.add(idx_j)

            used.add(idx_i)
            clusters.append(cluster)

        for cluster in clusters:
            if len(cluster) == 1:
                v = violations[cluster[0]].copy()
                reviewer = v.get("reviewer", "unknown")
                v["detected_by"] = [reviewer]
                result.append(v)
            else:
                # Merge: pick longest texts, collect all reviewers
                candidates = [violations[idx] for idx in cluster]
                reviewers = list(
                    {c.get("reviewer", "unknown") for c in candidates}
                )

                # Pick the one with longest combined text
                best = max(
                    candidates,
                    key=lambda c: len(c.get("detection", ""))
                    + len(c.get("violation", ""))
                    + len(c.get("suggestion", "")),
                )
                merged = best.copy()
                merged["detected_by"] = sorted(reviewers)
                merged.pop("reviewer", None)
                result.append(merged)

    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Informational"]
_MAX_VIOLATION_TEXT_LEN = 80
_MAX_REASON_TEXT_LEN = 100


def _basename(value: str | None, default: str = "-") -> str:
    """Extract the basename from a path string, or return *default*."""
    return Path(str(value)).name if value else default


def _format_line_range(violation: dict, default: str = "-") -> str:
    """Format startline/endline from a violation dict into a display string."""
    startline = violation.get("startline") or ""
    endline = violation.get("endline") or ""
    sl, el = str(startline), str(endline)
    if sl and el and sl != el:
        return f"{sl}-{el}"
    return sl if sl else default


def _render_violation_table(violations: list[dict]) -> list[str]:
    """Render a Markdown table of violations (header + rows)."""
    rows: list[str] = []
    rows.append("| # | File | Lines | Guideline | Violation |")
    rows.append("|---|------|-------|-----------|-----------|")
    for idx, v in enumerate(violations, 1):
        file_name = _basename(v.get("file_name"))
        guideline_name = _basename(v.get("guideline"))
        violation_text = (v.get("violation") or "").replace("|", "\\|")[:_MAX_VIOLATION_TEXT_LEN]
        line_info = _format_line_range(v)
        rows.append(f"| {idx} | {file_name} | {line_info} | {guideline_name} | {violation_text} |")
    return rows


def _generate_markdown(aggregated: dict, batch_count: int, total_count: int = 0, failed_paths: list[str] | None = None, unavailable_reviewers: list[dict] | None = None) -> str:
    """Produce a human-readable Markdown report string."""
    lines: list[str] = []

    guidelines = aggregated["guidelines_reviewed"]
    files = aggregated["files_reviewed"]
    violations = aggregated["violations"]
    non_violations = aggregated["non_violations"]
    errors = aggregated.get("errors", [])

    # -- Header -----------------------------------------------------------
    lines.append("# Final Review Report\n")
    lines.append(f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

    # -- Summary ----------------------------------------------------------
    lines.append("## Summary\n")
    if total_count:
        lines.append(f"- **Batches Processed**: {batch_count} / {total_count}")
    else:
        lines.append(f"- **Batches Processed**: {batch_count}")
    if failed_paths:
        lines.append(f"- **Failed Batches**: {len(failed_paths)}")
    lines.append(f"- **Guidelines Reviewed**: {len(guidelines)}")
    lines.append(f"- **Files Reviewed**: {len(files)}")
    lines.append(f"- **Total Violations**: {len(violations)}")
    lines.append(f"- **Files Without Violations**: {len(non_violations)}")
    if errors:
        lines.append(f"- **Errors Encountered**: {len(errors)}")
    lines.append("")

    # -- Guidelines reviewed ----------------------------------------------
    if guidelines:
        lines.append("## Guidelines Reviewed\n")
        for g in guidelines:
            lines.append(f"- {g}")
        lines.append("")

    # -- Files reviewed ---------------------------------------------------
    if files:
        lines.append("## Files Reviewed\n")
        for f in files:
            lines.append(f"- {f}")
        lines.append("")

    # -- Violations by severity -------------------------------------------
    if violations:
        lines.append("## Violations by Severity\n")
        known_lower = {s.casefold() for s in _SEVERITY_ORDER}
        for severity in _SEVERITY_ORDER:
            sev_violations = [
                v for v in violations
                if (v.get("severity") or "").casefold() == severity.casefold()
            ]
            if not sev_violations:
                continue
            lines.append(f"### {severity} ({len(sev_violations)})\n")
            lines.extend(_render_violation_table(sev_violations))
            lines.append("")

        # Collect violations with severities not in _SEVERITY_ORDER
        other_violations = [
            v for v in violations
            if (v.get("severity") or "").casefold() not in known_lower
        ]
        if other_violations:
            lines.append(f"### Other ({len(other_violations)})\n")
            lines.extend(_render_violation_table(other_violations))
            lines.append("")

        # -- Detailed violations ------------------------------------------
        lines.append("## Detailed Violations\n")
        for idx, v in enumerate(violations, 1):
            lines.append(f"### Violation {idx}\n")
            lines.append(f"- **Severity**: {v.get('severity') or 'N/A'}")
            lines.append(f"- **File**: {v.get('file_name') or 'N/A'}")
            lines.append(f"- **Lines**: {_format_line_range(v, default='N/A')}")
            lines.append(f"- **Guideline**: {v.get('guideline') or 'N/A'}")
            lines.append(f"\n**[DETECTION]**: {v.get('detection') or 'N/A'}")
            lines.append(f"\n**[VIOLATION]**: {v.get('violation') or 'N/A'}")
            suggestion = v.get("suggestion")
            if suggestion:
                lines.append(f"\n**[SUGGESTION]**:\n```\n{suggestion}\n```")
            lines.append("")
    else:
        lines.append("## No Violations Found\n")
        lines.append("The code review did not find any violations against the provided guidelines.\n")

    # -- Non-violations ---------------------------------------------------
    if non_violations:
        lines.append("## Files Without Violations\n")
        lines.append("| File | Reason |")
        lines.append("|------|--------|")
        for nv in non_violations:
            file_name = _basename(nv.get("file_name"))
            reason = (nv.get("reason") or "").replace("|", "\\|")[:_MAX_REASON_TEXT_LEN]
            lines.append(f"| {file_name} | {reason} |")
        lines.append("")

    # -- Unavailable reviewers ---------------------------------------------
    if unavailable_reviewers:
        lines.append("## Unavailable Reviewers\n")
        lines.append("The following reviewers were configured but unavailable:\n")
        lines.append("| Reviewer | Reason |")
        lines.append("|----------|--------|")
        for ur in unavailable_reviewers:
            lines.append(
                f"| {ur.get('reviewer_name', 'unknown')} | "
                f"{ur.get('error', 'Unknown reason')} |"
            )
        lines.append("")

    # -- Errors -----------------------------------------------------------
    if errors or failed_paths:
        lines.append("## Errors Encountered\n")
        for err in errors:
            lines.append(f"- {err}")
        if failed_paths:
            lines.append("")
            lines.append("**Failed batch files**:\n")
            for fp in failed_paths:
                lines.append(f"- `{fp}`")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def _write_outputs(aggregated: dict, batch_count: int, output_dir: Path, total_count: int = 0, failed_paths: list[str] | None = None, unavailable_reviewers: list[dict] | None = None) -> tuple[Path, Path]:
    """Write final-review.json and final-review-report.md to *output_dir*."""
    output_dir.mkdir(parents=True, exist_ok=True)

    output_data = {**aggregated}
    if failed_paths:
        output_data["failed_batches"] = failed_paths
    if unavailable_reviewers:
        output_data["unavailable_reviewers"] = unavailable_reviewers

    json_path = output_dir / "final-review.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(output_data, fh, indent=2)
    logger.info("Wrote %s", json_path)

    md_path = output_dir / "final-review-report.md"
    md_path.write_text(
        _generate_markdown(
            aggregated, batch_count,
            total_count=total_count,
            failed_paths=failed_paths,
            unavailable_reviewers=unavailable_reviewers,
        ),
        encoding="utf-8",
    )
    logger.info("Wrote %s", md_path)

    return json_path, md_path


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge batch code-review JSON results into a unified report."
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--input-dir",
        help="Directory containing batch result JSON files.",
    )
    group.add_argument(
        "--input-files",
        nargs="+",
        help="Explicit list of batch result JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for output files (default: current directory).",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database to read specialist reviewer results "
             "from gk_specialist_reviews table.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow runs with zero batch results. Produces an empty report "
             "instead of aborting. Use for unavailable-reviewer-only runs.",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    args = _build_parser().parse_args()
    input_files = _collect_input_files(args)

    # Load batch results from JSON files
    batches: list[dict] = []
    failed_paths: list[str] = []
    for path in input_files:
        data = _load_batch(path)
        if data is not None:
            batches.append(data)
        else:
            failed_paths.append(str(path))

    # Load specialist results from DB if provided
    unavailable_reviewers: list[dict] = []
    if args.db:
        specialist_batches, unavailable_reviewers = _load_specialist_results(
            args.db
        )
        batches.extend(specialist_batches)
        logger.info(
            "Loaded %d specialist results from DB (%d unavailable)",
            len(specialist_batches), len(unavailable_reviewers),
        )

    if not batches:
        if args.allow_empty:
            logger.info("No batch results — producing empty report (--allow-empty)")
            aggregated = {
                "guidelines_reviewed": [],
                "files_reviewed": [],
                "violations": [],
                "non_violations": [],
            }
            output_dir = Path(args.output_dir)
            json_path, md_path = _write_outputs(
                aggregated, 0, output_dir,
                total_count=0,
                failed_paths=failed_paths if failed_paths else None,
                unavailable_reviewers=unavailable_reviewers if unavailable_reviewers else None,
            )
            print(
                f"Merge complete: 0 batches, 0 guidelines, 0 files, 0 violations."
            )
            if unavailable_reviewers:
                names = [ur["reviewer_name"] for ur in unavailable_reviewers]
                print(f"  Unavailable reviewers: {', '.join(names)}")
            print(f"  -> {json_path}")
            print(f"  -> {md_path}")
            return
        logger.error("No valid batch results loaded — aborting")
        sys.exit(1)

    # Aggregate
    aggregated = _aggregate(batches)

    # Normalize guideline identifiers (generic path cleanup)
    _normalize_violations(aggregated["violations"])

    # Deduplicate violations across reviewers
    aggregated["violations"] = _deduplicate_violations(
        aggregated["violations"]
    )

    # Write outputs
    output_dir = Path(args.output_dir)
    json_path, md_path = _write_outputs(
        aggregated, len(batches), output_dir,
        total_count=len(input_files),
        failed_paths=failed_paths,
        unavailable_reviewers=unavailable_reviewers,
    )

    # Summary to stdout
    violations = aggregated["violations"]
    print(
        f"Merge complete: {len(batches)} batches, "
        f"{len(aggregated['guidelines_reviewed'])} guidelines, "
        f"{len(aggregated['files_reviewed'])} files, "
        f"{len(violations)} violations."
    )
    if unavailable_reviewers:
        names = [ur["reviewer_name"] for ur in unavailable_reviewers]
        print(f"  Unavailable reviewers: {', '.join(names)}")
    print(f"  -> {json_path}")
    print(f"  -> {md_path}")


if __name__ == "__main__":
    main()
