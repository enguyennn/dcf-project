#!/usr/bin/env python3
"""Post code review findings as inline PR comments.

Reads findings JSON (from code_review output) and posts each finding
as an inline comment thread on the PR at the correct file/line.

Usage:
    python post-findings.py --platform ado --pr-url "https://..." --findings-file findings.json
    python post-findings.py --platform github --pr-url "https://..." --findings-file findings.json
    python post-findings.py --dry-run ...  # show what would be posted

Input JSON schema (code_review.output.code_review_findings):
{
  "findings": {
    "Important": [
      {"id": 1, "file": "path/to/file.cs", "line": 42, "description": "...", "mechanical": true, ...}
    ],
    "Suggestion": [...]
  }
}

Output: JSON { "posted": N, "skipped": N, "errors": [...] }
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import platform as _platform
from urllib.parse import quote

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


def run_cmd(cmd: list[str], timeout: int = 30) -> dict:
    """Run a CLI command and return result."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=env,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("CLI command failed before completion: %s", cmd[:4], exc_info=e)
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def severity_emoji(severity: str) -> str:
    """Map severity to emoji prefix."""
    return {
        "Critical": "🔴 Critical",
        "Important": "🟡 Important",
        "Suggestion": "💡 Suggestion",
    }.get(severity, severity)


def build_file_link(pr_url: str, file_path: str, line: int | None, platform: str) -> str | None:
    """Build a direct link to the file/line in the PR diff."""
    if not file_path or not line or "..." in file_path:
        return None
    normalized = f"/{file_path}" if not file_path.startswith("/") else file_path
    if platform == "ado":
        parts = parse_ado_url(pr_url)
        if not parts:
            return None
        encoded_path = quote(normalized, safe="")
        return (
            f"https://dev.azure.com/{parts['org']}/{parts['project']}/_git/{parts['repo']}"
            f"/pullrequest/{parts['pr_id']}?path={encoded_path}"
            f"&line={line}&lineEnd={line + 1}&lineStartColumn=1&lineEndColumn=1"
            f"&lineStyle=plain&_a=files"
        )
    elif platform == "github":
        # GitHub inline links require the file SHA which we don't have here
        # Fall back to the files tab with a path hint
        parts = parse_github_url(pr_url)
        if not parts:
            return None
        return f"https://github.com/{parts['owner']}/{parts['repo']}/pull/{parts['pr_num']}/files"
    return None


def format_comment(finding: dict, severity: str, pr_url: str = "", platform: str = "") -> str:
    """Format a finding into a PR comment body."""
    file_path = finding.get("file", "")
    line = finding.get("line")
    category = finding.get("category", "Code Review")
    # Display "Needs Review" instead of "human-judgment" for readability
    if category.lower() == "human-judgment":
        category = "Needs Review"

    lines = [f"**{severity_emoji(severity)}** — {category}"]

    # File link — clickable path to the exact location in the PR diff
    if file_path and line and pr_url:
        link = build_file_link(pr_url, normalize_file_path(file_path), line, platform)
        short_name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
        if link:
            lines.append(f"\n📄 **[{short_name}, line {line}]({link})**")
        else:
            lines.append(f"\n📄 **{short_name}, line {line}**")

    lines.append("")
    lines.append(finding.get("description", "No description"))

    # Rich context for human-judgment findings
    if finding.get("code_context"):
        lines.append("")
        lines.append(f"**What the code does:** {finding['code_context']}")
    if finding.get("why_not_auto_fixed"):
        lines.append("")
        lines.append(f"**Why this needs review:** {finding['why_not_auto_fixed']}")
    if finding.get("decision_guide"):
        lines.append("")
        lines.append(f"**How to decide:** {finding['decision_guide']}")

    if finding.get("recommended_fix"):
        lines.append("")
        lines.append(f"**Suggested fix:** {finding['recommended_fix']}")
    mechanical = finding.get("mechanical", False)
    if mechanical:
        lines.append("")
        lines.append("_Classification: mechanical (auto-fixable)_")
    lines.append("")
    lines.append("---")
    lines.append("_Posted by [PR Orchestrator](https://github.com/azure-core/octane) code review_")
    return "\n".join(lines)


def normalize_file_path(file_path: str) -> str:
    """Normalize file path: strip leading slashes, handle Frontend/... prefix."""
    path = file_path.strip()
    # Remove leading / or ./
    path = re.sub(r"^[./\\]+", "", path)
    # Handle "Frontend/.../utils/StringUtils.ts" ellipsis patterns
    # These can't be posted as inline comments — return as-is for PR-level
    return path


def post_ado(pr_url: str, findings: list[dict], dry_run: bool) -> dict:
    """Post findings as inline PR comment threads on ADO."""
    parts = parse_ado_url(pr_url)
    if not parts:
        return {"error": f"Cannot parse ADO PR URL: {pr_url}"}

    api_base = parts["api_base"]
    project = parts["project"]
    repo = parts["repo"]
    pr_id = parts["pr_id"]
    ops = ReviewThreadOps(PrRef.from_url(pr_url)) if _HAS_PLATFORM else None

    posted = 0
    skipped = 0
    errors = []

    for finding in findings:
        file_path = normalize_file_path(finding.get("file", ""))
        line = finding.get("line")
        severity = finding.get("_severity", "Suggestion")
        comment_body = format_comment(finding, severity, pr_url, "ado")

        if dry_run:
            print(f"[DRY RUN] Would post: {file_path}:{line} — {finding.get('description', '')[:80]}", file=sys.stderr)
            posted += 1
            continue

        try:
            if ops:
                if not file_path or "..." in file_path:
                    ops.post_pr_level(comment_body)
                else:
                    thread_status = 1 if severity.lower() in ("critical", "important") else 5
                    ops.post_inline(comment_body, file_path, line or 1, status=thread_status)
                posted += 1
                continue
        except Exception as exc:
            print(f"[fallback] pr_platform.ReviewThreadOps.post_inline failed ({exc}) — using CLI", file=sys.stderr)

        if not file_path or "..." in file_path:
            thread_body = {
                "comments": [{"parentCommentId": 0, "content": comment_body, "commentType": 1}],
                "status": 4,
            }
        else:
            thread_status = 1 if severity.lower() in ("critical", "important") else 5
            thread_body = {
                "comments": [{"parentCommentId": 0, "content": comment_body, "commentType": 1}],
                "status": thread_status,
                "threadContext": {
                    "filePath": f"/{file_path}" if not file_path.startswith("/") else file_path,
                },
            }
            if line and isinstance(line, int) and line > 0:
                thread_body["threadContext"]["rightFileStart"] = {"line": line, "offset": 1}
                thread_body["threadContext"]["rightFileEnd"] = {"line": line, "offset": 999}

        body_file = os.path.join(tempfile.gettempdir(), f"finding-{finding.get('id', posted)}.json")
        with open(body_file, "w", encoding="utf-8") as f:
            json.dump(thread_body, f, ensure_ascii=False)

        try:
            result = run_cmd([
                "az", "rest", "--method", "post",
                "--url", f"{api_base}/{project}/_apis/git/repositories/{repo}/pullRequests/{pr_id}/threads?api-version=7.1",
                "--resource", ADO_RESOURCE,
                "--body", f"@{body_file}",
                "--headers", "Content-Type=application/json",
            ])
        finally:
            try:
                os.unlink(body_file)
            except OSError as exc:
                logger.debug("Failed to remove temporary ADO findings payload: %s", body_file, exc_info=exc)

        if result["exit_code"] == 0:
            posted += 1
        else:
            errors.append(f"Finding {finding.get('id')}: {result['stderr'][:200]}")
            skipped += 1

    return {"posted": posted, "skipped": skipped, "errors": errors}


def post_github(pr_url: str, findings: list[dict], dry_run: bool) -> dict:
    """Post findings as PR review comments on GitHub."""
    parts = parse_github_url(pr_url)
    if not parts:
        return {"error": f"Cannot parse GitHub PR URL: {pr_url}"}

    owner = parts["owner"]
    repo = parts["repo"]
    pr_num = parts["pr_num"]
    ops = ReviewThreadOps(PrRef.from_url(pr_url)) if _HAS_PLATFORM else None

    posted = 0
    skipped = 0
    errors = []

    for finding in findings:
        file_path = normalize_file_path(finding.get("file", ""))
        line = finding.get("line")
        severity = finding.get("_severity", "Suggestion")
        comment_body = format_comment(finding, severity, pr_url, "github")

        if dry_run:
            print(f"[DRY RUN] Would post: {file_path}:{line} — {finding.get('description', '')[:80]}", file=sys.stderr)
            posted += 1
            continue

        try:
            if ops:
                if not file_path or "..." in file_path or not line:
                    ops.post_pr_level(comment_body)
                else:
                    ops.post_inline(comment_body, file_path, line)
                posted += 1
                continue
        except Exception as exc:
            print(f"[fallback] pr_platform.ReviewThreadOps.post_inline failed ({exc}) — using CLI", file=sys.stderr)

        if not file_path or "..." in file_path or not line:
            result = run_cmd([
                "gh", "pr", "comment", pr_num,
                "--repo", f"{owner}/{repo}",
                "--body", comment_body,
            ])
        else:
            body = json.dumps({
                "body": comment_body,
                "path": file_path,
                "line": line,
                "side": "RIGHT",
            })
            body_file = os.path.join(tempfile.gettempdir(), f"gh-finding-{finding.get('id', posted)}.json")
            with open(body_file, "w", encoding="utf-8") as f:
                f.write(body)
            try:
                result = run_cmd([
                    "gh", "api",
                    f"/repos/{owner}/{repo}/pulls/{pr_num}/comments",
                    "--method", "POST",
                    "--input", body_file,
                ])
            finally:
                try:
                    os.unlink(body_file)
                except OSError as exc:
                    logger.debug("Failed to remove temporary GitHub findings payload: %s", body_file, exc_info=exc)

        if result["exit_code"] == 0:
            posted += 1
        else:
            errors.append(f"Finding {finding.get('id')}: {result['stderr'][:200]}")
            skipped += 1

    return {"posted": posted, "skipped": skipped, "errors": errors}


def extract_findings(data: dict) -> list[dict]:
    """Extract findings from code_review output JSON, handling both formats.

    Supports:
    - Nested: {"findings": {"Important": [...], "Suggestion": [...]}}
    - Flat array: {"findings": [{"severity": "Important", ...}, ...]}
    - Top-level flat: [{"severity": "Important", ...}, ...]
    """
    findings_list = []

    findings_obj = data.get("findings", data)

    # Handle flat array format (agent passes [{severity: "Important", ...}, ...])
    if isinstance(findings_obj, list):
        for item in findings_obj:
            sev = item.get("severity", item.get("_severity", "Suggestion"))
            item["_severity"] = sev.title()  # Normalize: "critical" → "Critical"
            findings_list.append(item)
    elif isinstance(findings_obj, dict):
        # Handle nested structure: {"Important": [...], "Suggestion": [...]}
        # Case-insensitive key matching (code_review may use "important" or "Important")
        normalized = {k.lower(): v for k, v in findings_obj.items() if isinstance(v, list)}
        for severity, key in [("Critical", "critical"), ("Important", "important"), ("Suggestion", "suggestion"), ("Suggestion", "suggestions")]:
            items = normalized.get(key, [])
            if isinstance(items, list):
                for item in items:
                    item["_severity"] = severity
                    findings_list.append(item)

    # Filter out findings that were already auto-fixed by code_fix
    # All mechanical findings (any severity) are auto-fixed — don't post them
    result = []
    for f in findings_list:
        is_mechanical = f.get("mechanical") is True or f.get("classification") == "mechanical"
        if is_mechanical:
            continue
        result.append(f)

    return result


def main():
    parser = argparse.ArgumentParser(description="Post code review findings as inline PR comments")
    parser.add_argument("--platform", required=True, choices=["ado", "github"])
    parser.add_argument("--pr-url", required=True, help="Full PR URL")
    parser.add_argument("--findings-file", required=True, help="JSON file with code review findings")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be posted without actually posting")
    args = parser.parse_args()

    with open(args.findings_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    findings = extract_findings(data)

    if not findings:
        print(json.dumps({"posted": 0, "skipped": 0, "errors": [], "message": "No findings to post (all were mechanical and auto-fixed)"}))
        return

    if args.platform == "ado":
        result = post_ado(args.pr_url, findings, args.dry_run)
    else:
        result = post_github(args.pr_url, findings, args.dry_run)

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("posted", 0) > 0 or not result.get("errors") else 1)


if __name__ == "__main__":
    main()
