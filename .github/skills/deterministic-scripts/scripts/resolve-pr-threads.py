#!/usr/bin/env python3
"""Deterministic PR thread resolution.

Resolves (marks as Fixed/WontFix) PR comment threads on Azure DevOps or GitHub.
Replaces manual `az rest` calls in LLM agent prompts with a reliable script.

Usage:
    # Resolve specific threads as Fixed
    python resolve-pr-threads.py --pr-url URL --thread-ids 123 456 789

    # Resolve from scrape-fb-threads.json (Phase 5 output)
    python resolve-pr-threads.py --pr-url URL --from-file scrape-fb-threads.json

    # Resolve the digest thread
    python resolve-pr-threads.py --pr-url URL --digest-thread-id 123

    # Dry run
    python resolve-pr-threads.py --pr-url URL --thread-ids 123 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pr_url_utils import parse_pr_url


# ADO thread status codes
STATUS_FIXED = 2
STATUS_WONT_FIX = 5
STATUS_CLOSED = 4

# Resolve az CLI path — on Windows it's az.cmd which subprocess can't find without shell=True
_AZ_CMD = shutil.which("az") or "az"


def _ado_resolve_thread(
    org: str, project: str, repo: str, pr_id: str, thread_id: str,
    status: int = STATUS_FIXED, dry_run: bool = False,
) -> dict:
    """Resolve a single ADO PR thread via az rest."""
    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}"
        f"/pullRequests/{pr_id}/threads/{thread_id}?api-version=7.1"
    )
    body = json.dumps({"status": status})

    if dry_run:
        return {"thread_id": thread_id, "status": "dry_run", "target_status": status}

    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [
                _AZ_CMD, "rest",
                "--method", "patch",
                "--url", url,
                "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
                "--body", body,
                "--headers", "Content-Type=application/json",
            ],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
            errors="replace", env=env,
        )
        # Check stdout for thread response — if it contains the status we set,
        # treat as success even if az rest returned warnings on stderr.
        if result.returncode == 0:
            return {"thread_id": thread_id, "status": "resolved", "target_status": status}

        # az rest may return non-zero but still succeed (e.g. stderr encoding warnings).
        # Check if stdout contains a valid JSON response with our thread.
        stdout = (result.stdout or "").strip()
        if stdout.startswith("{"):
            try:
                resp = json.loads(stdout)
                resp_status = resp.get("status")
                if resp_status == status or resp.get("id"):
                    return {"thread_id": thread_id, "status": "resolved", "target_status": status}
            except json.JSONDecodeError:
                pass

        return {
            "thread_id": thread_id,
            "status": "failed",
            "error": result.stderr.strip()[:200],
        }
    except Exception as exc:
        return {"thread_id": thread_id, "status": "error", "error": str(exc)[:200]}


def _github_resolve_thread(
    owner: str, repo: str, pr_num: str, thread_id: str,
    dry_run: bool = False,
) -> dict:
    """GitHub doesn't have thread resolution on issue comments."""
    return {"thread_id": thread_id, "status": "skipped", "reason": "GitHub lacks thread resolution"}


def resolve_threads(
    pr_url: str,
    thread_ids: list[str],
    status: int = STATUS_FIXED,
    dry_run: bool = False,
) -> list[dict]:
    """Resolve a list of threads on the PR."""
    parsed = parse_pr_url(pr_url)
    if not parsed:
        return [{"error": f"Cannot parse PR URL: {pr_url}"}]

    results = []
    platform = parsed.get("platform")

    for tid in thread_ids:
        tid = str(tid).strip()
        if not tid:
            continue

        if platform == "ado":
            r = _ado_resolve_thread(
                parsed["org"], parsed["project"], parsed["repo"],
                parsed["pr_id"], tid, status=status, dry_run=dry_run,
            )
        elif platform == "github":
            r = _github_resolve_thread(
                parsed["owner"], parsed["repo"], parsed["pr_id"],
                tid, dry_run=dry_run,
            )
        else:
            r = {"thread_id": tid, "status": "error", "error": f"Unknown platform: {platform}"}

        results.append(r)

    return results


def load_thread_ids_from_file(filepath: str) -> tuple[list[str], list[str]]:
    """Load thread IDs from scrape-fb-threads.json.

    Returns (resolved_ids, suggestion_ids) — resolved get Fixed, suggestions get WontFix.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"  ⚠ Cannot read {filepath}: {exc}", file=sys.stderr, flush=True)
        return [], []

    threads = data.get("threads", {})
    resolved = threads.get("resolved", [])
    actionable = threads.get("actionable", [])

    resolved_ids = [str(t.get("thread_id", "")) for t in resolved if t.get("thread_id")]
    # Suggestions that weren't fixed — mark as WontFix
    suggestion_ids = [
        str(t.get("thread_id", ""))
        for t in actionable
        if t.get("thread_id") and t.get("classification") in ("suggestion", "wont_fix")
    ]

    return resolved_ids, suggestion_ids


def main():
    parser = argparse.ArgumentParser(description="Deterministic PR thread resolution")
    parser.add_argument("--pr-url", required=True, help="PR URL")
    parser.add_argument("--thread-ids", nargs="*", default=[], help="Thread IDs to resolve as Fixed")
    parser.add_argument("--digest-thread-id", help="Digest thread ID to resolve as Fixed")
    parser.add_argument("--from-file", help="Path to scrape-fb-threads.json")
    parser.add_argument("--status", type=int, default=STATUS_FIXED,
                        help=f"ADO thread status code (default: {STATUS_FIXED}=Fixed)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    args = parser.parse_args()

    all_results = []

    # Digest thread
    if args.digest_thread_id:
        results = resolve_threads(
            args.pr_url, [args.digest_thread_id],
            status=STATUS_FIXED, dry_run=args.dry_run,
        )
        all_results.extend(results)
        for r in results:
            status_str = r.get("status", "?")
            print(f"  ▸ resolve-thread-digest-{r.get('thread_id', '?')}: {status_str}", flush=True)

    # Explicit thread IDs
    if args.thread_ids:
        results = resolve_threads(
            args.pr_url, args.thread_ids,
            status=args.status, dry_run=args.dry_run,
        )
        all_results.extend(results)
        for r in results:
            status_str = r.get("status", "?")
            print(f"  ▸ resolve-thread-{r.get('thread_id', '?')}: {status_str}", flush=True)

    # From scrape file
    if args.from_file:
        resolved_ids, suggestion_ids = load_thread_ids_from_file(args.from_file)

        if resolved_ids:
            results = resolve_threads(
                args.pr_url, resolved_ids,
                status=STATUS_FIXED, dry_run=args.dry_run,
            )
            all_results.extend(results)
            for r in results:
                status_str = r.get("status", "?")
                print(f"  ▸ resolve-thread-feedback-{r.get('thread_id', '?')}: {status_str}", flush=True)

        if suggestion_ids:
            results = resolve_threads(
                args.pr_url, suggestion_ids,
                status=STATUS_WONT_FIX, dry_run=args.dry_run,
            )
            all_results.extend(results)
            for r in results:
                status_str = r.get("status", "?")
                print(f"  ▸ resolve-thread-suggestion-{r.get('thread_id', '?')}: {status_str}", flush=True)

    # Summary
    success = sum(1 for r in all_results if r.get("status") in ("resolved", "dry_run", "skipped"))
    failed = sum(1 for r in all_results if r.get("status") in ("failed", "error"))
    total = len(all_results)

    if total == 0:
        print("  ▸ No threads to resolve", flush=True)
    else:
        print(f"  ▸ Thread resolution: {success}/{total} succeeded, {failed} failed", flush=True)

    # Output JSON for downstream consumption
    print(json.dumps({
        "total": total,
        "resolved": success,
        "failed": failed,
        "details": all_results,
    }))


if __name__ == "__main__":
    main()
