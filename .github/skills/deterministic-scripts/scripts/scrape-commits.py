#!/usr/bin/env python3
"""Scrape git commits between two SHAs.

Deterministically collects commit metadata (SHA, message, author, files changed)
for all commits after a given SHA up to HEAD (or a specified branch). Designed
to replace LLM-reported fix_commits with ground-truth git data.

Usage:
    python scrape-commits.py --since-sha abc123 --output-file commits.json
    python scrape-commits.py --since-sha abc123 --output-file commits.json --branch main
    python scrape-commits.py --since-sha abc123 --output-file commits.json --repo-dir /path/to/repo

Output: JSON file with commit list
{
  "since_sha": "abc123",
  "head_sha": "def456",
  "commits": [
    {
      "sha": "0123456789abcdef0123456789abcdef01234567",
      "short_sha": "0123456",
      "message": "fix: resolve build failure",
      "author": "user@example.com",
      "files_changed": ["file1.cs", "file2.cs"]
    }
  ],
  "commit_count": 1
}

The `sha` field is always the full 40-character commit SHA. `short_sha` is a
7-character display convenience derived from that full SHA.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    """Run a git command and return the completed process."""
    cmd = ["git"] + args
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def resolve_head(branch: str | None, cwd: str) -> str:
    """Resolve HEAD sha for the given branch (or HEAD if None)."""
    ref = branch if branch else "HEAD"
    result = run_git(["rev-parse", ref], cwd=cwd)
    if result.returncode != 0:
        print(f"Error: failed to resolve {ref}: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def validate_sha(sha: str, cwd: str) -> None:
    """Validate that a SHA exists in the repo."""
    result = run_git(["rev-parse", "--verify", f"{sha}^{{commit}}"], cwd=cwd)
    if result.returncode != 0:
        print(f"Error: since-sha '{sha}' is not a valid commit: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def get_commits(since_sha: str, branch: str | None, cwd: str) -> list[dict]:
    """Get commits between since_sha and HEAD/branch in chronological order."""
    ref = branch if branch else "HEAD"
    result = run_git(
        ["log", f"{since_sha}..{ref}", "--format=%H|||%s|||%ae", "--reverse"],
        cwd=cwd,
    )
    if result.returncode != 0:
        print(f"Error: git log failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    commits: list[dict] = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|||")
        if len(parts) < 3:
            continue
        sha, message, author = parts[0].strip(), parts[1], parts[2]
        short_sha = sha[:7]
        files = get_files_changed(sha, cwd)
        commits.append({
            "sha": sha,
            "short_sha": short_sha,
            "message": message,
            "author": author,
            "files_changed": files,
        })
    return commits


def get_files_changed(sha: str, cwd: str) -> list[str]:
    """Get list of files changed in a commit."""
    result = run_git(["diff-tree", "--no-commit-id", "--name-only", "-r", sha], cwd=cwd)
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f.strip()]


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Scrape git commits between two SHAs.")
    parser.add_argument("--since-sha", required=True, help="Start SHA (exclusive)")
    parser.add_argument("--output-file", required=True, help="Path to write JSON output")
    parser.add_argument("--branch", default=None, help="Branch to log from (default: HEAD)")
    parser.add_argument("--repo-dir", default=".", help="Git repo directory (default: cwd)")
    args = parser.parse_args()

    cwd = os.path.abspath(args.repo_dir)

    # Strip whitespace from SHA — Conductor stdout may include trailing newlines
    since_sha = args.since_sha.strip()

    # Verify git is available
    try:
        subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: git is not available", file=sys.stderr)
        sys.exit(1)

    # Validate since-sha
    validate_sha(since_sha, cwd)

    # Resolve head
    head_sha = resolve_head(args.branch, cwd)

    # Collect commits
    commits = get_commits(since_sha, args.branch, cwd)

    # Build output
    output = {
        "since_sha": since_sha,
        "head_sha": head_sha,
        "commits": commits,
        "commit_count": len(commits),
    }

    # Ensure output directory exists
    out_path = Path(args.output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Print path for Conductor to capture
    print(str(out_path))


if __name__ == "__main__":
    main()
