#!/usr/bin/env python3
"""Collect deterministic PR bootstrap metadata for PR Orchestrator workflows."""

import argparse
import json
import subprocess
import sys


def run_cmd(args):
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError as exc:
        print(f"Command not found: {args[0]} ({exc})", file=sys.stderr)
        raise SystemExit(1) from exc
    except OSError as exc:
        print(f"Failed to run {' '.join(args)}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def require_git_output(args, label):
    result = run_cmd(args)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        print(f"{label} failed: {err}", file=sys.stderr)
        raise SystemExit(1)
    return result.stdout.strip()


def detect_platform():
    remote_output = require_git_output(["git", "remote", "-v"], "git remote -v")
    remote_text = remote_output.lower()
    if "dev.azure.com" in remote_text or "visualstudio.com" in remote_text:
        return "ado"
    if "github.com" in remote_text:
        return "github"
    print("Unable to detect platform from git remote -v", file=sys.stderr)
    raise SystemExit(1)


def check_auth(platform):
    cmd = ["az", "account", "show", "--output", "none"] if platform == "ado" else ["gh", "auth", "status"]
    try:
        result = run_cmd(cmd)
    except SystemExit:
        # On Windows, 'az' may be a bash shim that Python subprocess cannot execute
        # directly (FileNotFoundError). Fall back to az.cmd if available.
        import shutil
        fallback = "az.cmd" if platform == "ado" else None
        if fallback and shutil.which(fallback):
            try:
                result = subprocess.run(
                    [fallback, *(cmd[1:])],
                    capture_output=True, text=True, shell=True,
                )
            except Exception:
                print(f"Warning: auth check skipped for {platform} (command not executable)", file=sys.stderr)
                return False
        else:
            print(f"Warning: auth check skipped for {platform} (command not executable)", file=sys.stderr)
            return False
    if result.returncode == 0:
        return True
    err = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
    print(f"Warning: auth check failed for {platform}: {err}", file=sys.stderr)
    return False


def get_changed_files(target_branch):
    candidates = [target_branch]
    if not target_branch.startswith("origin/"):
        candidates.append(f"origin/{target_branch}")

    last_error = ""
    for candidate in candidates:
        result = run_cmd(["git", "diff", "--name-only", f"{candidate}...HEAD"])
        if result.returncode == 0:
            return [line for line in result.stdout.splitlines() if line.strip()]
        last_error = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        print(f"Warning: git diff against {candidate} failed: {last_error}", file=sys.stderr)

    print(f"Unable to get changed files for target branch '{target_branch}': {last_error}", file=sys.stderr)
    raise SystemExit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Deterministic bootstrap for PR Orchestrator")
    parser.add_argument("--target-branch", required=True, help="Target branch to diff against")
    parser.add_argument("--existing-pr", default="", help="Existing PR URL to pass through")
    parser.add_argument("--json", action="store_true", help="Output JSON (default behavior)")
    return parser.parse_args()


def main():
    args = parse_args()
    platform = detect_platform()
    result = {
        "platform": platform,
        "pr_author": require_git_output(["git", "config", "user.email"], "git config user.email"),
        "changed_files": get_changed_files(args.target_branch),
        "source_branch": require_git_output(["git", "branch", "--show-current"], "git branch --show-current"),
        "existing_pr": args.existing_pr,
        "auth_ok": check_auth(platform),
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
