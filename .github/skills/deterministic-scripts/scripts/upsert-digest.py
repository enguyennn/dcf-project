#!/usr/bin/env python3
"""Upsert (create or update) the PR Orchestrator digest comment on a PR.

Finds the digest comment by HTML marker, creates if not found, updates if exists.
Uses az CLI (ADO) or gh CLI (GitHub) — no direct REST API calls.

Usage:
    python upsert-digest.py --platform ado --pr-url "https://dev.azure.com/org/project/_git/repo/pullrequest/123" --content-file digest.md
    python upsert-digest.py --platform github --pr-url "https://github.com/owner/repo/pull/42" --content-file digest.md
    python upsert-digest.py --dry-run ...  # show what would happen without posting

Output: JSON { "action": "created|updated|dry_run", "comment_id": "...", "thread_id": "..." }
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pr_url_utils import parse_ado_pr_url as parse_ado_url
from pr_url_utils import parse_github_pr_url as parse_github_url

try:
    from pr_platform import DigestOps, PrRef
    _HAS_PLATFORM = True
except ImportError:
    DigestOps = None
    PrRef = None
    _HAS_PLATFORM = False
    print("[fallback] pr_platform not available — using CLI fallback", file=sys.stderr)

DIGEST_MARKER = "<!-- ai-agent:pr-orchestrator-digest -->"
logger = logging.getLogger(__name__)


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    """Return the directory for per-run artifacts."""
    if workspace_dir:
        path = Path(workspace_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    fallback = Path(tempfile.gettempdir())
    print(
        "WARNING: --workspace-dir not provided; falling back to the shared temp directory",
        file=sys.stderr,
    )
    return fallback


def run_cmd(cmd: list[str], timeout: int = 30) -> dict:
    """Run a CLI command and return result."""
    import platform
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    use_shell = platform.system() == "Windows"
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", shell=use_shell, env=env,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("CLI command failed before completion: %s", cmd[:4], exc_info=e)
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


def upsert_ado(pr_url: str, content: str, dry_run: bool, workspace_dir: Path) -> dict:
    """Upsert digest comment on ADO PR."""
    parts = parse_ado_url(pr_url)
    if not parts:
        return {"error": f"Cannot parse ADO PR URL: {pr_url}"}

    if _HAS_PLATFORM:
        try:
            ref = PrRef.from_url(pr_url)
            ops = DigestOps(ref)
            existing = ops.find_existing(DIGEST_MARKER)
            if dry_run:
                return {
                    "action": "dry_run",
                    "would_do": "would_update" if existing else "would_create",
                    "thread_id": str((existing or {}).get("thread_id", "")),
                    "comment_id": str((existing or {}).get("comment_id", "")),
                }
            return ops.upsert(content, DIGEST_MARKER)
        except Exception as exc:
            print(f"[fallback] pr_platform.DigestOps.upsert failed ({exc}) — using CLI", file=sys.stderr)

    project = parts["project"]
    pr_id = parts["pr_id"]
    api_base = parts["api_base"]
    threads_file = workspace_dir / "pr-threads.json"
    result = run_cmd([
        "az", "rest", "--method", "get",
        "--url", f"{api_base}/{project}/_apis/git/repositories/{parts['repo']}/pullRequests/{pr_id}/threads?api-version=7.1",
        "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
        "--output-file", str(threads_file),
    ], timeout=30)

    existing_thread_id = None
    existing_comment_id = None
    if result["exit_code"] == 0:
        try:
            with open(threads_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            threads = data.get("value", [])
            for thread in threads:
                comments = thread.get("comments", [])
                if comments and DIGEST_MARKER in (comments[0].get("content", "")):
                    existing_thread_id = thread["id"]
                    existing_comment_id = comments[0]["id"]
                    break
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to parse existing ADO digest thread payload; assuming no existing digest", exc_info=exc)

    if dry_run:
        action = "would_update" if existing_thread_id else "would_create"
        return {
            "action": "dry_run",
            "would_do": action,
            "thread_id": str(existing_thread_id or ""),
            "comment_id": str(existing_comment_id or ""),
        }

    if existing_thread_id and existing_comment_id:
        body = json.dumps({"content": content})
        body_file = workspace_dir / "upsert-body.json"
        with open(body_file, "w", encoding="utf-8") as f:
            f.write(body)
        result = run_cmd([
            "az", "rest", "--method", "patch",
            "--url", f"{api_base}/{project}/_apis/git/repositories/{parts['repo']}/pullRequests/{pr_id}/threads/{existing_thread_id}/comments/{existing_comment_id}?api-version=7.1",
            "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
            "--body", f"@{body_file}",
            "--headers", "Content-Type=application/json",
        ])
        if result["exit_code"] == 0:
            return {
                "action": "updated",
                "thread_id": str(existing_thread_id),
                "comment_id": str(existing_comment_id),
            }
        return {"error": f"Failed to update: {result['stderr']}"}

    body = json.dumps({
        "comments": [{"parentCommentId": 0, "content": content, "commentType": 1}],
        "status": 1,
    })
    body_file = workspace_dir / "upsert-body.json"
    with open(body_file, "w", encoding="utf-8") as f:
        f.write(body)
    result = run_cmd([
        "az", "rest", "--method", "post",
        "--url", f"{api_base}/{project}/_apis/git/repositories/{parts['repo']}/pullRequests/{pr_id}/threads?api-version=7.1",
        "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
        "--body", f"@{body_file}",
        "--headers", "Content-Type=application/json",
    ])
    if result["exit_code"] == 0:
        try:
            data = json.loads(result["stdout"])
            return {
                "action": "created",
                "thread_id": str(data.get("id", "")),
                "comment_id": str(data.get("comments", [{}])[0].get("id", "")),
            }
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.warning("ADO digest create succeeded but response parsing failed; returning empty ids", exc_info=exc)
            return {"action": "created", "thread_id": "", "comment_id": ""}
    return {"error": f"Failed to create: {result['stderr']}"}


def upsert_github(pr_url: str, content: str, dry_run: bool) -> dict:
    """Upsert digest comment on GitHub PR."""
    parts = parse_github_url(pr_url)
    if not parts:
        return {"error": f"Cannot parse GitHub PR URL: {pr_url}"}

    if _HAS_PLATFORM:
        try:
            ref = PrRef.from_url(pr_url)
            ops = DigestOps(ref)
            existing = ops.find_existing(DIGEST_MARKER)
            if dry_run:
                return {
                    "action": "dry_run",
                    "would_do": "would_update" if existing else "would_create",
                    "comment_id": str((existing or {}).get("comment_id", "")),
                }
            return ops.upsert(content, DIGEST_MARKER)
        except Exception as exc:
            print(f"[fallback] pr_platform.DigestOps.upsert failed ({exc}) — using CLI", file=sys.stderr)

    owner = parts["owner"]
    repo = parts["repo"]
    pr_num = parts["pr_num"]
    result = run_cmd([
        "gh", "api", f"repos/{owner}/{repo}/issues/{pr_num}/comments",
        "--jq", f'.[] | select(.body | contains("{DIGEST_MARKER}")) | {{id: .id}}',
    ])

    existing_id = None
    if result["exit_code"] == 0 and result["stdout"].strip():
        try:
            data = json.loads(result["stdout"].strip().split("\n")[0])
            existing_id = data.get("id")
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse GitHub digest lookup response; assuming no existing digest", exc_info=exc)

    if dry_run:
        action = "would_update" if existing_id else "would_create"
        return {"action": "dry_run", "would_do": action, "comment_id": str(existing_id or "")}

    if existing_id:
        body_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", encoding="utf-8", delete=False,
        )
        try:
            json.dump({"body": content}, body_file, ensure_ascii=False)
            body_file.close()
            result = run_cmd([
                "gh", "api", f"repos/{owner}/{repo}/issues/comments/{existing_id}",
                "-X", "PATCH", "--input", body_file.name,
            ])
        finally:
            os.unlink(body_file.name)
        if result["exit_code"] == 0:
            return {"action": "updated", "comment_id": str(existing_id)}
        return {"error": f"Failed to update: {result['stderr']}"}

    body_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False,
    )
    try:
        json.dump({"body": content}, body_file, ensure_ascii=False)
        body_file.close()
        result = run_cmd([
            "gh", "api", f"repos/{owner}/{repo}/issues/{pr_num}/comments",
            "--input", body_file.name,
        ])
    finally:
        os.unlink(body_file.name)
    if result["exit_code"] == 0:
        try:
            data = json.loads(result["stdout"])
            return {"action": "created", "comment_id": str(data.get("id", ""))}
        except json.JSONDecodeError as exc:
            logger.warning("GitHub digest create succeeded but response parsing failed; returning empty comment id", exc_info=exc)
            return {"action": "created", "comment_id": ""}
    return {"error": f"Failed to create: {result['stderr']}"}


def _resolve_platform(raw_platform: str, pr_url: str, hint_dir: str = "") -> str:
    """Resolve platform with fallback: argument → PR URL inference → detect-platform.py."""
    if raw_platform in ("ado", "github"):
        return raw_platform

    if pr_url:
        if "dev.azure.com" in pr_url or "visualstudio.com" in pr_url:
            return "ado"
        if "github.com" in pr_url:
            return "github"

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    detect_script = os.path.join(scripts_dir, "detect-platform.py")
    if os.path.isfile(detect_script):
        # Run detect-platform.py from the repo directory so git config lookup finds the right remote.
        repo_cwd = hint_dir if hint_dir else None
        try:
            result = subprocess.run(
                [sys.executable, detect_script],
                capture_output=True, text=True, timeout=10,
                cwd=repo_cwd,
            )
            if result.returncode == 0:
                detected = json.loads(result.stdout.strip()).get("platform", "")
                if detected in ("ado", "github"):
                    return detected
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass

    print("ERROR: Unable to determine platform", file=sys.stderr, flush=True)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Upsert PR Orchestrator digest comment")
    parser.add_argument("--platform", default="", help="ado|github; auto-detected if empty")
    parser.add_argument("--pr-url", required=True, help="Full PR URL")
    parser.add_argument("--content-file", required=True, help="Path to digest markdown file")
    parser.add_argument("--workspace-dir", default="", help="Directory for per-run workspace artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without posting")
    args = parser.parse_args()

    with open(args.content_file, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        print(json.dumps({"error": "Empty content file"}))
        sys.exit(1)

    if DIGEST_MARKER not in content:
        content = DIGEST_MARKER + "\n" + content

    platform = _resolve_platform(args.platform, args.pr_url, hint_dir=os.path.dirname(os.path.abspath(args.content_file)))
    workspace_dir = _resolve_workspace_dir(args.workspace_dir) if platform == "ado" else None

    if platform == "ado":
        result = upsert_ado(args.pr_url, content, args.dry_run, workspace_dir)
    else:
        result = upsert_github(args.pr_url, content, args.dry_run)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
