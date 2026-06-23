#!/usr/bin/env python3
"""Fetch PR code-level comments from Azure DevOps or GitHub.

Given a PR link and an iterations JSON file (from fetch_pr_iterations.py),
returns a JSON array of reviewer comments mapped to iterations, in the format
expected by the Gatekeeper Replay pipeline.

Usage:
    python fetch_pr_comments.py \
        --pr-url <url> \
        --iterations <pr-iterations.json> \
        [--output <path>]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime


def _run(cmd: list[str], **kwargs) -> str:
    """Run a command and return stdout, raising on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def parse_pr_url(url: str) -> dict:
    """Parse a PR URL into platform, org, project, repo, pr_id."""
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
    """Get an Azure DevOps access token.

    Checks AGENCY_MCP_AUTH_ADO_SYSTEM_ACCESS_TOKEN first (set by the 1ES
    Agency pipeline template when mcpConfiguration.ado is declared), then
    falls back to az CLI.
    """
    token = os.environ.get("AGENCY_MCP_AUTH_ADO_SYSTEM_ACCESS_TOKEN", "").strip()
    if token:
        return token
    return _run([
        "az", "account", "get-access-token",
        "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
        "--query", "accessToken", "-o", "tsv",
    ])


def _ado_api_get(url: str, token: str):
    """Call an ADO REST API endpoint using urllib."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} from {url}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


def _strip_html(text: str) -> str:
    """Remove HTML tags from comment body."""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_iso_datetime(date_str: str) -> datetime:
    """Parse an ISO 8601 datetime string, handling Z suffix."""
    return datetime.fromisoformat(
        date_str.replace("Z", "+00:00") if "Z" in date_str else date_str
    )


def _find_iteration(sorted_iters: list, comment_date_str: str) -> dict | None:
    """Find the latest iteration created before the given comment date."""
    comment_dt = _parse_iso_datetime(comment_date_str)
    best = None
    for it in sorted_iters:
        it_dt = _parse_iso_datetime(it["createdDate"])
        if it_dt <= comment_dt:
            best = it
        else:
            break
    return best


def fetch_ado_comments(parsed: dict, iteration_ids: set[int]) -> list:
    """Fetch code-level comments from Azure DevOps, mapped to iterations."""
    org = parsed["org"]
    project = parsed["project"]
    repo = parsed["repo"]
    pr_id = parsed["pr_id"]

    token = _get_ado_token()
    base = (
        f"https://dev.azure.com/{org}/{project}/_apis/git"
        f"/repositories/{repo}/pullRequests/{pr_id}"
    )

    # Fetch iterations (needed for date-based mapping)
    iters_data = _ado_api_get(f"{base}/iterations?api-version=7.1", token)
    iterations = iters_data if isinstance(iters_data, list) else iters_data.get("value", [])
    sorted_iters = sorted(iterations, key=lambda i: i["createdDate"])

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

    comments = []
    for t in code_threads:
        first_comment = t["comments"][0]
        published = first_comment["publishedDate"]
        matched_iter = _find_iteration(sorted_iters, published)
        if not matched_iter:
            continue

        iter_id = matched_iter["id"]
        # Only include comments for iterations that have comments (from the
        # iterations file)
        if iteration_ids and iter_id not in iteration_ids:
            continue

        file_path = t["threadContext"]["filePath"]
        if file_path.startswith("/"):
            file_path = file_path[1:]

        line_start = (t["threadContext"].get("rightFileStart") or {}).get("line")
        line_end = (t["threadContext"].get("rightFileEnd") or {}).get("line")
        if not line_start:
            line_number = "0"
        elif line_start == line_end or not line_end:
            line_number = str(line_start)
        else:
            line_number = f"{line_start}-{line_end}"

        body = _strip_html(first_comment.get("content", ""))
        body = " ".join(body.split())  # normalize whitespace

        comments.append({
            "comment_id": str(t["id"]),
            "iteration_id": str(iter_id),
            "file_path": file_path,
            "line_number": line_number,
            "comment_body": body,
            "author": first_comment["author"]["displayName"],
        })

    # Sort by iteration_id, then file, then line
    comments.sort(key=lambda c: (
        int(c["iteration_id"]),
        os.path.basename(c["file_path"]),
        int(c["line_number"].split("-")[0]) if c["line_number"] != "0" else 0,
    ))

    return comments


def fetch_github_comments(parsed: dict, iteration_ids: set[int]) -> list:
    """Fetch code-level comments from GitHub."""
    owner = parsed["owner"]
    repo = parsed["repo"]
    pr_id = parsed["pr_id"]

    raw = _run([
        "gh", "api", f"repos/{owner}/{repo}/pulls/{pr_id}/comments",
        "--paginate",
    ])
    api_comments = json.loads(raw)

    comments = []
    for c in api_comments:
        comments.append({
            "comment_id": str(c["id"]),
            "iteration_id": str(c.get("pull_request_review_id", "0")),
            "file_path": c.get("path", ""),
            "line_number": str(c.get("original_line") or c.get("line", 0)),
            "comment_body": c.get("body", ""),
            "author": c.get("user", {}).get("login", ""),
        })

    comments.sort(key=lambda c: (
        c["iteration_id"],
        os.path.basename(c["file_path"]),
        int(c["line_number"].split("-")[0]) if c["line_number"] != "0" else 0,
    ))

    return comments


def main():
    parser = argparse.ArgumentParser(
        description="Fetch PR code-level comments for Gatekeeper Replay"
    )
    parser.add_argument("--pr-url", help="PR URL (ADO or GitHub)")
    parser.add_argument("--org", help="ADO organization (alternative to --pr-url)")
    parser.add_argument("--project", help="ADO project (alternative to --pr-url)")
    parser.add_argument("--repository-id", help="ADO repository ID/name (alternative to --pr-url)")
    parser.add_argument("--pr-id", type=int, help="Pull request ID (alternative to --pr-url)")
    parser.add_argument(
        "--iterations",
        help="Path to pr-iterations.json (from fetch_pr_iterations.py). "
             "Used to validate comment-iteration mapping.",
    )
    parser.add_argument(
        "--iteration-id",
        help="Filter output to only comments for this specific iteration ID.",
    )
    parser.add_argument("--output", help="Output JSON file path (default: stdout)")
    args = parser.parse_args()

    if args.pr_url:
        parsed = parse_pr_url(args.pr_url)
    elif args.org and args.project and args.repository_id and args.pr_id:
        parsed = {
            "platform": "azure-devops",
            "org": args.org,
            "project": args.project,
            "repo": args.repository_id,
            "pr_id": args.pr_id,
        }
    else:
        parser.error("Provide either --pr-url or all of --org, --project, --repository-id, --pr-id")

    # Load iteration IDs if provided
    iteration_ids: set[int] = set()
    if args.iterations:
        with open(args.iterations, encoding="utf-8") as f:
            iter_data = json.load(f)
        for entry in iter_data.get("iteration_timeline", []):
            iteration_ids.add(int(entry["iteration_id"]))

    if parsed["platform"] == "azure-devops":
        comments = fetch_ado_comments(parsed, iteration_ids)
    else:
        comments = fetch_github_comments(parsed, iteration_ids)

    # Filter to a specific iteration if requested
    if args.iteration_id:
        comments = [c for c in comments if c["iteration_id"] == args.iteration_id]

    output = json.dumps(comments, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output)

    # Summary to stderr
    iter_counts: dict[str, int] = {}
    for c in comments:
        iter_counts[c["iteration_id"]] = iter_counts.get(c["iteration_id"], 0) + 1
    print(
        f"Total comments: {len(comments)}\n"
        f"Iterations: {', '.join(f'{k}({v})' for k, v in sorted(iter_counts.items(), key=lambda x: int(x[0])))}",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
