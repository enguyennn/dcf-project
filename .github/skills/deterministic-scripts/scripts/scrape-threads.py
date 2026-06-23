#!/usr/bin/env python3
"""Scrape PR thread state and enrich with commit attribution.

Calls triage-threads.py to get current thread state, loads commit data from
scrape-commits.py output, and builds addressed_details by matching resolved
threads to commits that touched the same files.

Usage:
    python scrape-threads.py --platform ado --pr-url "https://..." \
        --commits-file commits.json --output-file threads.json
    python scrape-threads.py --platform ado --pr-url "https://..." \
        --commits-file commits.json --output-file threads.json --baseline-file baseline.json

Output: JSON with thread state and addressed_details
{
  "threads": {
    "actionable": [...],
    "resolved": [...],
    "skipped": [...]
  },
  "addressed_details": [...],
  "summary": {
    "total_threads": 10,
    "actionable": 2,
    "resolved": 5,
    "skipped": 3,
    "newly_resolved": 5
  }
}
"""

import argparse
import json
import logging
import os
import platform as _platform
import subprocess
import sys
from typing import Any

from encoding_utils import clean_html, load_json_robust

logger = logging.getLogger(__name__)


def strip_html(text: str) -> str:
    """Backward-compatible wrapper for shared HTML cleaning."""
    return clean_html(text)


def run_triage(platform: str, pr_url: str) -> dict:
    """Call triage-threads.py and return parsed output."""
    triage_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "triage-threads.py")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    use_shell = _platform.system() == "Windows"
    try:
        result = subprocess.run(
            [sys.executable, triage_path, "--platform", platform, "--pr-url", pr_url],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace", shell=use_shell, env=env,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("triage-threads.py failed before completion", exc_info=e)
        print(f"ERROR: triage-threads.py failed: {e}", file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(f"ERROR: triage-threads.py exited {result.returncode}: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse triage-threads.py output", exc_info=e)
        print(f"ERROR: Failed to parse triage-threads.py output: {e}", file=sys.stderr)
        sys.exit(1)


def load_json_file(path: str) -> dict | None:
    """Load a JSON file, returning None if missing or invalid."""
    if not path or not os.path.isfile(path):
        return None
    loaded = load_json_robust(path, label="scrape-threads-json", default=None)
    return loaded if isinstance(loaded, dict) else None


def build_file_to_commits(commits_data: dict | None) -> dict[str, list[dict]]:
    """Build a mapping from file path to list of commits that touched it.

    Commits are ordered as they appear in the input (assumed chronological).
    """
    mapping: dict[str, list[dict]] = {}
    if not commits_data:
        return mapping

    commits = commits_data.get("commits", [])
    for commit in commits:
        sha = commit.get("sha", commit.get("commit_sha", ""))
        files_changed = commit.get("files_changed", [])
        for file_path in files_changed:
            normalized = file_path.lstrip("/")
            mapping.setdefault(normalized, []).append({"sha": sha, "commit": commit})
    return mapping


def find_commit_for_file(file_path: str, file_to_commits: dict[str, list[dict]]) -> str:
    """Find the best commit SHA for a resolved thread's file.

    If multiple commits touched the file, return the last (most recent).
    If none match, return empty string.
    """
    if not file_path:
        return ""

    normalized = file_path.lstrip("/")

    # Direct match
    if normalized in file_to_commits:
        return file_to_commits[normalized][-1]["sha"]

    # Try matching by filename suffix (handles path prefix differences)
    for key, commits in file_to_commits.items():
        if key.endswith(normalized) or normalized.endswith(key):
            return commits[-1]["sha"]

    return ""


def build_resolved_threads(
    triage_output: dict,
    baseline: dict | None,
) -> tuple[list[dict], list[dict], int]:
    """Determine resolved threads and newly_resolved count.

    Returns (resolved_list, actionable_for_addressed, newly_resolved_count).
    """
    current_actionable = triage_output.get("actionable", [])
    current_actionable_ids = {t["thread_id"] for t in current_actionable}
    skipped = triage_output.get("skipped", [])

    if baseline is not None:
        # Baseline mode: resolved = threads in baseline.actionable not in current actionable
        baseline_actionable = baseline.get("threads", {}).get("actionable", [])
        if not baseline_actionable:
            baseline_actionable = baseline.get("actionable", [])

        resolved = []
        for thread in baseline_actionable:
            if thread["thread_id"] not in current_actionable_ids:
                resolved.append({
                    "thread_id": thread["thread_id"],
                    "file": thread.get("file", ""),
                    "line": thread.get("line"),
                    "author": thread.get("author", ""),
                    "body": thread.get("body", ""),
                    "status": "resolved",
                })

        newly_resolved = len(resolved)
        return resolved, resolved, newly_resolved
    else:
        # No baseline: resolved threads come from skipped with "already_resolved" reason
        resolved = []
        for s in skipped:
            reason = s.get("reason", "")
            if "already_resolved" in reason:
                resolved.append({
                    "thread_id": s["thread_id"],
                    "file": s.get("file", ""),
                    "line": s.get("line"),
                    "author": s.get("author", ""),
                    "body": clean_html(s.get("body", "")),
                    "status": "resolved",
                })

        newly_resolved = len(resolved)
        return resolved, resolved, newly_resolved


def build_addressed_details(
    threads_for_details: list[dict],
    file_to_commits: dict[str, list[dict]],
) -> list[dict]:
    """Build addressed_details by matching resolved threads to commits."""
    details = []
    for thread in threads_for_details:
        file_path = thread.get("file", "")
        body = thread.get("body", "")
        finding_summary = clean_html(body, max_length=100) if body else ""

        commit_sha = find_commit_for_file(file_path, file_to_commits)

        details.append({
            "thread_id": thread["thread_id"],
            "file": file_path,
            "finding_summary": finding_summary,
            "commit_sha": commit_sha,
            "status": "fixed",
        })
    return details


def write_output(output: dict, output_file: str) -> None:
    """Write JSON output to file."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"ERROR: Failed to write output: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape PR thread state and enrich with commit data")
    parser.add_argument("--platform", required=True, choices=["ado", "github"])
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--commits-file", required=True, help="Path to scrape-commits.py JSON output")
    parser.add_argument("--output-file", required=True, help="Path to write JSON output")
    parser.add_argument("--baseline-file", default=None, help="Path to previous scrape-threads output for diffing")
    args = parser.parse_args()

    # Step 1: Call triage-threads.py
    triage_output = run_triage(args.platform, args.pr_url)

    # Step 2: Load commits data (missing file → empty)
    commits_data = load_json_file(args.commits_file)
    file_to_commits = build_file_to_commits(commits_data)

    # Step 3: Load baseline if provided (missing file → treat as no baseline)
    baseline = load_json_file(args.baseline_file) if args.baseline_file else None

    # Step 4: Build thread state
    current_actionable = triage_output.get("actionable", [])
    skipped = [
        {
            **item,
            "body": clean_html(item.get("body", "")) if isinstance(item, dict) else item,
        }
        if isinstance(item, dict)
        else item
        for item in triage_output.get("skipped", [])
    ]

    # Normalize actionable threads for output
    actionable_out = []
    for t in current_actionable:
        actionable_out.append({
            "thread_id": t["thread_id"],
            "file": t.get("file", ""),
            "line": t.get("line"),
            "author": t.get("author", ""),
            "body": clean_html(t.get("body", "")),
            "status": t.get("status", "active") or "active",
        })

    resolved, threads_for_details, newly_resolved = build_resolved_threads(triage_output, baseline)

    # Step 5: Build addressed_details
    addressed_details = build_addressed_details(threads_for_details, file_to_commits)

    # Step 6: Assemble output
    total_threads = len(actionable_out) + len(resolved) + len(skipped)
    output: dict[str, Any] = {
        "threads": {
            "actionable": actionable_out,
            "resolved": resolved,
            "skipped": skipped,
        },
        "addressed_details": addressed_details,
        "summary": {
            "total_threads": total_threads,
            "actionable": len(actionable_out),
            "resolved": len(resolved),
            "skipped": len(skipped),
            "newly_resolved": newly_resolved,
        },
    }

    write_output(output, args.output_file)
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
