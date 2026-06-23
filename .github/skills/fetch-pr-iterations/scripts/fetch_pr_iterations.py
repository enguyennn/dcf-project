#!/usr/bin/env python3
"""Fetch PR iterations with comments from Azure DevOps or GitHub.

Given a PR link, returns a JSON array of iterations that received reviewer
comments, in the format expected by the Gatekeeper Replay pipeline.

Usage:
    python fetch_pr_iterations.py --pr-url <url> [--output <path>]

Supports:
    - Azure DevOps: https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}
    - Azure DevOps (old): https://{org}.visualstudio.com/{project}/_git/{repo}/pullrequest/{id}
    - GitHub: https://github.com/{owner}/{repo}/pull/{number}
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime


def _run(cmd: list[str], **kwargs) -> str:
    """Run a command and return stdout, raising on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True, **kwargs)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def parse_pr_url(url: str) -> dict:
    """Parse a PR URL into platform, org, project, repo, pr_id."""
    # Azure DevOps (new format)
    m = re.match(
        r"https://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)/pullrequest/(\d+)",
        url,
    )
    if m:
        return {
            "platform": "azure-devops",
            "org": m.group(1),
            "project": m.group(2),
            "repo": m.group(3),
            "pr_id": int(m.group(4)),
        }

    # Azure DevOps (old visualstudio.com format)
    m = re.match(
        r"https://([^.]+)\.visualstudio\.com/([^/]+)/_git/([^/]+)/pullrequest/(\d+)",
        url,
    )
    if m:
        return {
            "platform": "azure-devops",
            "org": m.group(1),
            "project": m.group(2),
            "repo": m.group(3),
            "pr_id": int(m.group(4)),
        }

    # GitHub
    m = re.match(
        r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)",
        url,
    )
    if m:
        return {
            "platform": "github",
            "owner": m.group(1),
            "repo": m.group(2),
            "pr_id": int(m.group(3)),
        }

    print(f"ERROR: Unrecognized PR URL format: {url}", file=sys.stderr)
    sys.exit(1)


def _get_ado_token() -> str:
    """Get an Azure DevOps access token via az CLI."""
    return _run([
        "az", "account", "get-access-token",
        "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
        "--query", "accessToken", "-o", "tsv",
    ])


def _ado_api_get(url: str, token: str) -> dict:
    """Call an ADO REST API endpoint using urllib."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} from {url}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


def fetch_ado_iterations(parsed: dict) -> dict:
    """Fetch iterations and threads from Azure DevOps."""
    org = parsed["org"]
    project = parsed["project"]
    repo = parsed["repo"]
    pr_id = parsed["pr_id"]

    token = _get_ado_token()
    base = f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}/pullRequests/{pr_id}"

    # Fetch PR details
    pr = _ado_api_get(f"{base}?api-version=7.1", token)
    pr_title = pr.get("title", "")

    # Fetch iterations
    iters_data = _ado_api_get(f"{base}/iterations?api-version=7.1", token)
    iterations = iters_data if isinstance(iters_data, list) else iters_data.get("value", [])

    # Fetch threads
    threads_data = _ado_api_get(f"{base}/threads?api-version=7.1", token)
    threads = threads_data if isinstance(threads_data, list) else threads_data.get("value", [])

    # Filter to human code-level comment threads
    bot_authors = {"MerlinBot", "Microsoft.VisualStudio.Services.TFS"}
    code_threads = [
        t for t in threads
        if t.get("threadContext") and t["threadContext"].get("filePath")
        and t["comments"][0]["author"]["displayName"] not in bot_authors
        and t["comments"][0].get("commentType") != "system"
    ]

    # Sort iterations by createdDate
    sorted_iters = sorted(iterations, key=lambda i: i["createdDate"])

    # Map each comment thread to the latest iteration created before the comment
    def _find_iteration(comment_date_str: str):
        comment_dt = datetime.fromisoformat(
            comment_date_str.replace("Z", "+00:00")
            if "Z" in comment_date_str
            else comment_date_str
        )
        best = None
        for it in sorted_iters:
            it_dt = datetime.fromisoformat(
                it["createdDate"].replace("Z", "+00:00")
                if "Z" in it["createdDate"]
                else it["createdDate"]
            )
            if it_dt <= comment_dt:
                best = it
            else:
                break
        return best

    # Build iteration → comments mapping
    iter_comments: dict[int, list] = {}
    for t in code_threads:
        published = t["comments"][0]["publishedDate"]
        matched = _find_iteration(published)
        if matched:
            iter_id = matched["id"]
            iter_comments.setdefault(iter_id, []).append(t)

    # Build output
    timeline = []
    for it in sorted_iters:
        iter_id = it["id"]
        comments = iter_comments.get(iter_id, [])
        source = it["sourceRefCommit"]["commitId"]
        target = it["targetRefCommit"]["commitId"]
        entry = {
            "iteration_id": iter_id,
            "base_commit": target,
            "head_commit": source,
            "commit_range": f"{target}...{source}",
            "has_comments": len(comments) > 0,
            "comment_count": len(comments),
        }
        timeline.append(entry)

    # Filter to commented iterations only
    commented = [e for e in timeline if e["has_comments"]]

    return {
        "pr_url": f"https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{pr_id}",
        "pr_title": pr_title,
        "platform": "Azure DevOps",
        "total_iterations": len(timeline),
        "iterations_with_comments": len(commented),
        "total_code_comments": len(code_threads),
        "iteration_timeline": commented,
    }


def fetch_github_iterations(parsed: dict) -> dict:
    """Fetch iterations and comments from GitHub."""
    owner = parsed["owner"]
    repo = parsed["repo"]
    pr_id = parsed["pr_id"]

    # Get PR details
    pr_json = _run(["gh", "pr", "view", str(pr_id),
                     "--repo", f"{owner}/{repo}", "--json",
                     "title,baseRefName,headRefName,commits,reviews,reviewComments"])
    pr = json.loads(pr_json)
    pr_title = pr.get("title", "")

    # Get review comments (code-level)
    comments_json = _run(["gh", "api",
                          f"repos/{owner}/{repo}/pulls/{pr_id}/comments",
                          "--paginate"])
    comments = json.loads(comments_json)

    # Get commits timeline
    commits = pr.get("commits", [])

    # Map comments to commits by date
    commit_comments: dict[str, list] = {}
    for c in comments:
        # Find the commit this comment was made on
        commit_id = c.get("original_commit_id") or c.get("commit_id", "")
        commit_comments.setdefault(commit_id, []).append(c)

    # Build timeline from commits
    timeline = []
    for i, commit in enumerate(commits):
        sha = commit.get("oid", "")
        ccount = len(commit_comments.get(sha, []))
        entry = {
            "iteration_id": i + 1,
            "base_commit": commits[0]["oid"] + "~1" if i == 0 else commits[i - 1]["oid"],
            "head_commit": sha,
            "commit_range": f"{commits[0]['oid']}~1...{sha}",
            "has_comments": ccount > 0,
            "comment_count": ccount,
        }
        timeline.append(entry)

    commented = [e for e in timeline if e["has_comments"]]

    return {
        "pr_url": f"https://github.com/{owner}/{repo}/pull/{pr_id}",
        "pr_title": pr_title,
        "platform": "GitHub",
        "total_iterations": len(timeline),
        "iterations_with_comments": len(commented),
        "total_code_comments": len(comments),
        "iteration_timeline": commented,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PR iterations with comments for Gatekeeper Replay"
    )
    parser.add_argument("--pr-url", required=True, help="PR URL (ADO or GitHub)")
    parser.add_argument("--output", help="Output JSON file path (default: stdout)")
    args = parser.parse_args()

    parsed = parse_pr_url(args.pr_url)

    if parsed["platform"] == "azure-devops":
        result = fetch_ado_iterations(parsed)
    else:
        result = fetch_github_iterations(parsed)

    output = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output)

    # Summary to stderr
    print(
        f"PR: {result['pr_title']}\n"
        f"Platform: {result['platform']}\n"
        f"Iterations: {result['total_iterations']} total, "
        f"{result['iterations_with_comments']} with comments\n"
        f"Code comments: {result['total_code_comments']}",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
