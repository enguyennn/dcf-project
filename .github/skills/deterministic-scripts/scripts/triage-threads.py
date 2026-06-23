#!/usr/bin/env python3
"""Fetch and triage PR review threads.

Fetches all comment threads from a PR, filters out system/digest threads,
and classifies each as actionable or not. Optionally marks threads on files
outside the PR diff as out_of_diff_scope.

Usage:
    python triage-threads.py --platform ado --pr-url "https://..."
    python triage-threads.py --platform github --pr-url "https://..." --changed-files '["src/a.cs","src/b.ts"]'

Output: JSON with triaged threads
{
  "actionable": [
    {"thread_id": "123", "file": "/path.cs", "line": 42, "author": "GitOps", "body": "...", "verdict": "should_consider", "scope": "in_diff"},
    ...
  ],
  "skipped": [
    {"thread_id": "456", "reason": "digest_comment"},
    ...
  ],
  "summary": {"total": 10, "actionable": 3, "skipped": 7}
}
"""

import argparse
import json
import logging
import os
import platform as _platform
import re
import subprocess
import sys
import time

from encoding_utils import clean_html, load_json_robust

from pr_url_utils import parse_ado_pr_url as parse_ado_url
from pr_url_utils import parse_github_pr_url as parse_github_url

try:
    from pr_platform import PrRef, ReviewThreadOps
    _HAS_PLATFORM = True
except ImportError:
    PrRef = None
    ReviewThreadOps = None
    _HAS_PLATFORM = False
    print("[fallback] pr_platform not available — using CLI fallback", file=sys.stderr)


ADO_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
logger = logging.getLogger(__name__)

DIGEST_MARKER = "<!-- ai-agent:pr-orchestrator-digest -->"

BOT_PATTERNS = [
    r"GitOps",
    r"PR\s*Assistant",
    r"github-actions\[bot\]",
    r"copilot\[bot\]",
    r"\[bot\]$",
    r"Microsoft\.VisualStudio\.Services\.TFS",
]

ORCHESTRATOR_MARKER = "Posted by [PR Orchestrator]"

SYSTEM_CONTENT_PATTERNS = [
    r"^Ownership Enforcer",
    r"^The reference refs/",
    r"^Merged PR \d+",
    r"updated the pull request",
    r"has been updated with summary",
    r"Pull request description has been updated",
    r"voted on the pull request",
    r"marked the pull request as",
]


def run_cmd(cmd: list[str], timeout: int = 30) -> dict:
    """Run a CLI command and return result."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    use_shell = _platform.system() == "Windows"
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", shell=use_shell, env=env,
        )
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("CLI command failed before completion: %s", cmd[:4], exc_info=e)
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def is_bot(author: str) -> bool:
    """Check if author is a bot/automated system."""
    for pattern in BOT_PATTERNS:
        if re.search(pattern, author, re.IGNORECASE):
            return True
    return False


def is_system_content(content: str) -> bool:
    """Check if content is a system-generated message."""
    normalized = clean_html(content)
    for pattern in SYSTEM_CONTENT_PATTERNS:
        if re.search(pattern, normalized):
            return True
    return False


def clean_thread_body(body: str, max_length: int = 200) -> str:
    """Backward-compatible wrapper for shared HTML cleaning."""
    return clean_html(body, max_length=max_length)


def classify_thread(thread: dict, changed_files: list[str] | None = None) -> dict:
    """Classify a single thread as actionable or skipped."""
    comments = thread.get("comments", [])
    if not comments:
        return {"thread_id": str(thread.get("id", "")), "reason": "empty_thread", "skip": True}

    first_comment = comments[0]
    author = first_comment.get("author", {}).get("displayName", first_comment.get("author", {}).get("uniqueName", "unknown"))
    unique_name = first_comment.get("author", {}).get("uniqueName", "")
    body = first_comment.get("content", "")
    thread_id = str(thread.get("id", ""))
    status = thread.get("status", "")
    file_path = thread.get("threadContext", {}).get("filePath", "") if thread.get("threadContext") else ""
    line = None
    if thread.get("threadContext") and thread["threadContext"].get("rightFileStart"):
        line = thread["threadContext"]["rightFileStart"].get("line")

    # Skip: digest comment (check before resolved — digest threads can be marked closed)
    if DIGEST_MARKER in body:
        return {"thread_id": thread_id, "reason": "digest_comment", "skip": True}

    # Skip: system/TFS messages (check before resolved — system msgs can have resolved status)
    if is_system_content(body):
        return {"thread_id": thread_id, "reason": "system_message", "skip": True}

    # Skip: already resolved — include file/body so downstream can build rich digest rows
    if status and status.lower() in ("fixed", "closed", "wontfix", "bydesign"):
        return {
            "thread_id": thread_id,
            "reason": f"already_resolved ({status})",
            "skip": True,
            "file": file_path,
            "line": line,
            "author": author,
            "body": clean_thread_body(body),
        }

    # Classify verdict
    body_lower = body.lower()
    is_bot_author = is_bot(author)

    # Diff-scope: if changed_files provided, check if thread's file is in the diff
    scope = "in_diff"
    if changed_files is not None and file_path:
        # Normalize: strip leading slash for comparison
        normalized_file = file_path.lstrip("/")
        if not any(normalized_file == cf.lstrip("/") or normalized_file.endswith("/" + cf.lstrip("/")) or cf.lstrip("/").endswith("/" + normalized_file) for cf in changed_files):
            scope = "out_of_diff_scope"

    if any(kw in body_lower for kw in ["security", "vulnerability", "injection", "xss", "csrf"]):
        verdict = "must_fix"
    elif any(kw in body_lower for kw in ["bug", "error", "crash", "broken", "incorrect", "wrong"]):
        verdict = "must_fix"
    elif is_bot_author:
        verdict = "should_consider"
    elif any(kw in body_lower for kw in ["consider", "suggest", "could", "might", "optional"]):
        verdict = "should_consider"
    else:
        verdict = "should_consider"

    clean_body = clean_thread_body(body)

    return {
        "thread_id": thread_id,
        "skip": False,
        "file": file_path,
        "line": line,
        "author": author,
        "is_bot": is_bot_author,
        "body": clean_body,
        "verdict": verdict,
        "scope": scope,
        "status": status,
        "comment_count": len(comments),
    }


def fetch_ado_threads(pr_url: str) -> list[dict]:
    """Fetch threads from ADO PR."""
    parts = parse_ado_url(pr_url)
    if not parts:
        return []

    if _HAS_PLATFORM:
        try:
            return ReviewThreadOps(PrRef.from_url(pr_url)).list_threads()
        except Exception as exc:
            print(f"[fallback] pr_platform.ReviewThreadOps.list_threads failed ({exc}) — using CLI", file=sys.stderr)

    api_base = parts["api_base"]
    project = parts["project"]
    repo = parts["repo"]
    pr_id = parts["pr_id"]

    import tempfile
    out_file = os.path.join(tempfile.gettempdir(), "triage-threads.json")
    result = run_cmd([
        "az", "rest", "--method", "get",
        "--url", f"{api_base}/{project}/_apis/git/repositories/{repo}/pullRequests/{pr_id}/threads?api-version=7.1",
        "--resource", ADO_RESOURCE,
        "--output-file", out_file,
    ], timeout=30)

    if result["exit_code"] != 0:
        print(f"ERROR: Failed to fetch threads: {result['stderr']}", file=sys.stderr)
        return []

    data = load_json_robust(out_file, label="ado-threads", default={})
    if isinstance(data, dict):
        return data.get("value", [])
    print("ERROR: Failed to parse threads", file=sys.stderr)
    return []


def fetch_github_threads(pr_url: str) -> list[dict]:
    """Fetch review comments from GitHub PR."""
    parts = parse_github_url(pr_url)
    if not parts:
        return []

    if _HAS_PLATFORM:
        try:
            return ReviewThreadOps(PrRef.from_url(pr_url)).list_threads()
        except Exception as exc:
            print(f"[fallback] pr_platform.ReviewThreadOps.list_threads failed ({exc}) — using CLI", file=sys.stderr)

    owner = parts["owner"]
    repo = parts["repo"]
    pr_num = parts["pr_num"]

    result = run_cmd([
        "gh", "api", f"/repos/{owner}/{repo}/pulls/{pr_num}/comments",
        "--paginate",
    ], timeout=30)

    if result["exit_code"] != 0:
        return []

    try:
        comments = json.loads(result["stdout"])
        # Convert GitHub format to ADO-like thread format
        threads = []
        for c in comments:
            threads.append({
                "id": c.get("id"),
                "status": "",
                "threadContext": {"filePath": c.get("path", ""), "rightFileStart": {"line": c.get("line")}},
                "comments": [{
                    "content": c.get("body", ""),
                    "author": {"displayName": c.get("user", {}).get("login", ""), "uniqueName": c.get("user", {}).get("login", "")},
                }],
            })
        return threads
    except json.JSONDecodeError:
        return []


def _fetch_and_classify(platform: str, pr_url: str, changed_files: list[str] | None) -> dict:
    """Fetch threads and classify them. Returns the triage output dict."""
    if platform == "ado":
        threads = fetch_ado_threads(pr_url)
    else:
        threads = fetch_github_threads(pr_url)

    actionable = []
    skipped = []

    for thread in threads:
        result = classify_thread(thread, changed_files=changed_files)
        if result.get("skip"):
            skipped.append(result)
        else:
            actionable.append(result)

    return {
        "actionable": actionable,
        "skipped": skipped,
        "summary": {
            "total": len(threads),
            "actionable": len(actionable),
            "skipped": len(skipped),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch and triage PR review threads")
    parser.add_argument("--platform", required=True, choices=["ado", "github"])
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--changed-files", default=None, help="JSON array of changed file paths (inline)")
    parser.add_argument("--changed-files-path", default=None, help="Path to JSON file containing changed file paths")
    parser.add_argument("--retry-delay", type=int, default=0, help="Seconds to wait before retrying when 0 actionable threads found")
    parser.add_argument("--max-retries", type=int, default=0, help="Max retries when 0 actionable threads found (handles API eventual consistency)")
    parser.add_argument("--output-file", default=None, help="Write JSON output to this file (UTF-8, no BOM) in addition to stdout")
    args = parser.parse_args()

    # Parse changed files if provided
    changed_files = None
    if args.changed_files_path:
        try:
            from pathlib import Path
            changed_files = json.loads(Path(args.changed_files_path).read_text(encoding="utf-8"))
            if not isinstance(changed_files, list):
                changed_files = None
        except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
            print(f"WARNING: Could not read --changed-files-path ({e}), disabling diff-scope filtering", file=sys.stderr)
    elif args.changed_files:
        try:
            changed_files = json.loads(args.changed_files)
            if not isinstance(changed_files, list):
                changed_files = None
        except json.JSONDecodeError:
            print(f"WARNING: Could not parse --changed-files JSON, disabling diff-scope filtering", file=sys.stderr)

    output = _fetch_and_classify(args.platform, args.pr_url, changed_files)

    # Retry if no actionable threads found (ADO API eventual consistency)
    retries = 0
    while output["summary"]["actionable"] == 0 and retries < args.max_retries and args.retry_delay > 0:
        retries += 1
        print(f"INFO: 0 actionable threads found, retry {retries}/{args.max_retries} after {args.retry_delay}s delay...", file=sys.stderr)
        time.sleep(args.retry_delay)
        output = _fetch_and_classify(args.platform, args.pr_url, changed_files)

    if retries > 0:
        print(f"INFO: Completed after {retries} retry(ies), found {output['summary']['actionable']} actionable threads", file=sys.stderr)

    json_text = json.dumps(output, indent=2, ensure_ascii=False)
    print(json_text)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(json_text)


if __name__ == "__main__":
    main()
