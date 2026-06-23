#!/usr/bin/env python3
"""Apply deterministic PR body template — standalone entry point.

This script wraps fix-pr-body.py with platform I/O so it can be called
from Conductor workflows (Phase 2, Phase 4) OR from run-phases.py.

It fetches the current PR body, runs fix-pr-body.py to enforce template
structure, optionally replaces DIGEST_LINK_PLACEHOLDER, and updates the PR.

Usage:
    python apply-pr-body-template.py --pr-url <url> [--state-file <path>]
        [--digest-url <url>] [--work-dir <path>]

Exit codes:
    0 — success (body updated or already correct)
    1 — error (logged to stderr, non-fatal for callers)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pr_url_utils import parse_pr_url

try:
    from pr_platform import PrBodyOps, PrRef, run_cli
    _HAS_PLATFORM = True
except ImportError:
    PrBodyOps = None
    PrRef = None
    run_cli = None
    _HAS_PLATFORM = False
    print("[fallback] pr_platform not available — using CLI fallback", file=sys.stderr)


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
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


def _find_state_file(work_dir: Path) -> Path | None:
    """Find state file by convention: $TEMP/pr-orchestrator-state-{branch}.json."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(work_dir), timeout=10,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip().replace("/", "_")
        state_path = Path(tempfile.gettempdir()) / f"pr-orchestrator-state-{branch}.json"
        return state_path if state_path.exists() else None
    except Exception:
        return None


def _detect_platform(work_dir: Path) -> dict:
    """Detect platform from git remote URL."""
    scripts_dir = Path(__file__).parent
    detect_script = scripts_dir / "detect-platform.py"
    if not detect_script.exists():
        return {}
    try:
        result = subprocess.run(
            [sys.executable, str(detect_script)],
            capture_output=True, text=True, cwd=str(work_dir), timeout=10,
        )
        return json.loads(result.stdout.strip()) if result.returncode == 0 else {}
    except Exception:
        return {}


def _fetch_pr_body(
    platform: str, pr_url: str, platform_info: dict, workspace_dir: Path,
) -> tuple[str, str, str | None, str | None]:
    """Fetch PR body and title. Returns (body, title, pr_id, cli_cmd)."""
    tmp = workspace_dir

    # Prefer Phase 2's workspace-local body file (avoids ADO newline normalization)
    phase2_body = tmp / "pr-body.txt"
    if phase2_body.exists():
        body = phase2_body.read_text(encoding="utf-8")
        if body.strip() and body.strip() != "<!-- pr-orchestrator -->":
            print(f"  ▸ apply-template: using Phase 2 temp body ({len(body)} chars)", flush=True)
            pr_id, cli_cmd = _resolve_cli(platform, pr_url, platform_info)
            return body, "", pr_id, cli_cmd

    pr_id, cli_cmd = _resolve_cli(platform, pr_url, platform_info)
    if not pr_id or not cli_cmd:
        return "", "", None, None

    if _HAS_PLATFORM:
        try:
            ref = PrRef.from_url(pr_url)
            body = PrBodyOps(ref).fetch()
            if platform == "ado":
                title = run_cli([
                    "az", "repos", "pr", "show", "--id", pr_id,
                    "--org", str(ref.base_url), "--detect", "false", "--query", "title", "-o", "tsv",
                ]).stdout.rstrip("\r\n")
            else:
                title = run_cli(["gh", "pr", "view", pr_url, "--json", "title", "-q", ".title"]).stdout.rstrip("\r\n")
            return body, title, pr_id, cli_cmd
        except Exception as exc:
            print(f"[fallback] pr_platform.PrBodyOps.fetch failed ({exc}) — using CLI", file=sys.stderr)

    max_retries = 2
    backoff_s = 5

    if max_retries == 0:
        print("[fetch_pr_body] max_retries is 0 — no fetch attempts will be made", file=sys.stderr)

    if platform == "ado":
        org = platform_info.get("org", "")
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    [cli_cmd, "repos", "pr", "show", "--id", pr_id,
                     "--org", f"https://dev.azure.com/{org}",
                     "--output", "json", "--detect", "false"],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=90,
                )
            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    print(f"  ▸ apply-template: az repos pr show timed out (90s), retrying in {backoff_s}s...", flush=True)
                    time.sleep(backoff_s)
                    continue
                print(f"  ▸ apply-template: az repos pr show timed out (90s) after {max_retries} attempts", flush=True)
                return "", "", pr_id, cli_cmd
            if result.returncode != 0:
                if attempt < max_retries - 1:
                    print(f"  ▸ apply-template: az repos pr show failed (rc={result.returncode}), retrying in {backoff_s}s...", flush=True)
                    time.sleep(backoff_s)
                    continue
                print(f"  ▸ apply-template: az repos pr show failed: {result.stderr[:200]}", flush=True)
                return "", "", pr_id, cli_cmd
            pr_data = json.loads(result.stdout)
            return pr_data.get("description", ""), pr_data.get("title", ""), pr_id, cli_cmd

    elif platform == "github":
        owner = platform_info.get("owner", "")
        repo = platform_info.get("repo", "")
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    [cli_cmd, "pr", "view", pr_id, "--repo", f"{owner}/{repo}",
                     "--json", "title,body"],
                    capture_output=True, text=True, timeout=60,
                )
            except subprocess.TimeoutExpired:
                if attempt < max_retries - 1:
                    print(f"  ▸ apply-template: gh pr view timed out (60s), retrying in {backoff_s}s...", flush=True)
                    time.sleep(backoff_s)
                    continue
                print(f"  ▸ apply-template: gh pr view timed out (60s) after {max_retries} attempts", flush=True)
                return "", "", pr_id, cli_cmd
            if result.returncode != 0:
                if attempt < max_retries - 1:
                    print(f"  ▸ apply-template: gh pr view failed (rc={result.returncode}), retrying in {backoff_s}s...", flush=True)
                    time.sleep(backoff_s)
                    continue
                print(f"  ▸ apply-template: gh pr view failed: {result.stderr[:200]}", flush=True)
                return "", "", pr_id, cli_cmd
            pr_data = json.loads(result.stdout)
            return pr_data.get("body", ""), pr_data.get("title", ""), pr_id, cli_cmd

    return "", "", pr_id, cli_cmd


def _resolve_cli(platform: str, pr_url: str, platform_info: dict) -> tuple[str | None, str | None]:
    """Resolve PR ID and CLI command path."""
    parts = parse_pr_url(pr_url)
    if parts.get("platform") != platform:
        return None, None
    if platform == "ado":
        return parts.get("pr_id"), shutil.which("az")
    if platform == "github":
        return parts.get("pr_num", parts.get("pr_id")), shutil.which("gh")
    return None, None


ADO_DESCRIPTION_MAX = 3900  # ADO limit is 4000; stay under to account for encoding


def _update_pr(
    platform: str, pr_id: str, cli_cmd: str, body: str, platform_info: dict, workspace_dir: Path,
) -> bool:
    """Update PR description. Returns True on success."""
    tmp = workspace_dir

    # Enforce ADO 4000 char limit
    if platform == "ado" and len(body) > ADO_DESCRIPTION_MAX:
        truncation_marker = "\n\n---\n*Description truncated (4000 char limit)*"
        body = body[: ADO_DESCRIPTION_MAX - len(truncation_marker)] + truncation_marker
        print(f"  ▸ apply-template: truncated to {len(body)} chars (ADO limit)", flush=True)

    body_file = tmp / "pr-body-update.txt"
    body_file.write_text(body, encoding="utf-8")
    json_file = tmp / "pr-body-patch.json"

    try:
        if _HAS_PLATFORM and platform_info.get("_pr_url"):
            try:
                PrBodyOps(PrRef.from_url(platform_info["_pr_url"])).update(body)
                return True
            except Exception as exc:
                print(f"[fallback] pr_platform.PrBodyOps.update failed ({exc}) — using CLI", file=sys.stderr)

        if platform == "ado":
            org = platform_info.get("org", "")
            project = platform_info.get("project", "")
            repo_id = platform_info.get("repo_id", "")

            # Use az rest PATCH — avoids Windows cmd.exe mangling of multi-line
            # --description args and correctly handles @file JSON bodies.
            repo_name = platform_info.get("repo", "") or repo_id
            if org and project and repo_name:
                patch_body = json.dumps({"description": body})
                json_file.write_text(patch_body, encoding="utf-8")
                url = (
                    f"https://dev.azure.com/{org}/{project}"
                    f"/_apis/git/repositories/{repo_name}"
                    f"/pullrequests/{pr_id}?api-version=7.1"
                )
                result = subprocess.run(
                    [cli_cmd, "rest", "--method", "patch",
                     "--url", url,
                     "--body", f"@{json_file}",
                     "--headers", "Content-Type=application/json",
                     "--resource", "499b84ac-1321-427f-aa17-267ca6975798"],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0:
                    return True
                print(
                    f"  ▸ apply-template: az rest failed ({result.returncode}): "
                    f"{result.stderr[:200]}",
                    flush=True,
                )

            # Fallback: az repos pr update with @file
            result = subprocess.run(
                [cli_cmd, "repos", "pr", "update", "--id", pr_id,
                 "--description", f"@{body_file}",
                 "--org", f"https://dev.azure.com/{org}",
                 "--detect", "false", "--output", "json"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                print(f"  ▸ apply-template: PR update failed: {result.stderr[:200]}", flush=True)
                return False

        elif platform == "github":
            owner = platform_info.get("owner", "")
            repo = platform_info.get("repo", "")
            result = subprocess.run(
                [cli_cmd, "pr", "edit", pr_id, "--repo", f"{owner}/{repo}",
                 "--body-file", str(body_file)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                print(f"  ▸ apply-template: PR update failed: {result.stderr[:200]}", flush=True)
                return False

        return True
    except subprocess.TimeoutExpired as exc:
        print(f"  ▸ apply-template: CLI timed out ({exc.timeout}s) during PR update", flush=True)
        return False
    finally:
        try:
            body_file.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            json_file.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply deterministic PR body template")
    parser.add_argument("--pr-url", required=True, help="Full PR URL")
    parser.add_argument("--state-file", help="State JSON path (auto-detected if omitted)")
    parser.add_argument("--digest-url", default="", help="Digest comment URL to replace placeholder")
    parser.add_argument("--work-dir", default=".", help="Working directory (for git/platform detection)")
    parser.add_argument("--workspace-dir", default="", help="Directory for per-run workspace artifacts")
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()
    workspace_dir = _resolve_workspace_dir(args.workspace_dir)
    scripts_dir = Path(__file__).parent

    # Find fix-pr-body.py
    fix_script = scripts_dir / "fix-pr-body.py"
    if not fix_script.exists():
        print(f"  ▸ apply-template: fix-pr-body.py not found at {fix_script}", file=sys.stderr)
        return 1

    # Detect platform
    platform_info = _detect_platform(work_dir)
    platform_info["_pr_url"] = args.pr_url
    if _HAS_PLATFORM:
        try:
            parsed_ref = PrRef.from_url(args.pr_url)
            platform = parsed_ref.platform
            platform_info.setdefault("platform", platform)
            if platform == "ado":
                platform_info.setdefault("org", parsed_ref.org)
                platform_info.setdefault("project", parsed_ref.project)
                platform_info.setdefault("repo", parsed_ref.repo)
            else:
                platform_info.setdefault("owner", parsed_ref.owner)
                platform_info.setdefault("repo", parsed_ref.repo)
        except ValueError:
            parsed_parts = parse_pr_url(args.pr_url)
            platform = parsed_parts.get("platform", platform_info.get("platform", "unknown"))
            platform_info.update({k: v for k, v in parsed_parts.items() if v})
    else:
        parsed_parts = parse_pr_url(args.pr_url)
        platform = parsed_parts.get("platform", platform_info.get("platform", "unknown"))
        platform_info.update({k: v for k, v in parsed_parts.items() if v})
    if platform not in ("ado", "github"):
        print(f"  ▸ apply-template: unknown platform '{platform}'", file=sys.stderr)
        return 1

    # Find state file
    state_file = Path(args.state_file) if args.state_file else _find_state_file(work_dir)
    if not state_file or not state_file.exists():
        print("  ▸ apply-template: no state file found, skipping", file=sys.stderr)
        return 1

    # Fetch current body (prefers $TEMP/pr-body.txt over API)
    body, title, pr_id, cli_cmd = _fetch_pr_body(platform, args.pr_url, platform_info, workspace_dir)
    if not body or body.strip() == "<!-- pr-orchestrator -->":
        # No temp file with real content, and API has only sentinel/empty.
        # Nothing to apply — this is expected on first call before create_pr writes the file.
        print("  ▸ apply-template: no body content available (temp file missing or sentinel), skipping", flush=True)
        return 0

    if not pr_id or not cli_cmd:
        print("  ▸ apply-template: cannot resolve PR ID or CLI tool", file=sys.stderr)
        return 1

    # Run fix-pr-body.py
    tmp = workspace_dir
    body_raw = tmp / "pr-body-raw.txt"
    body_fixed = tmp / "pr-body-fixed.txt"
    try:
        body_raw.write_text(body, encoding="utf-8")

        # Check for bot overwrite (sentinel missing = description was replaced)
        if body and "<!-- pr-orchestrator -->" not in body:
            print("  ⚠️ apply-template: PR description sentinel missing — possible bot overwrite detected", file=sys.stderr)

        cmd = [
            sys.executable, str(fix_script),
            "--state-file", str(state_file),
            "--pr-body-file", str(body_raw),
            "--output-file", str(body_fixed),
        ]
        if title:
            cmd.extend(["--pr-title", title])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  ▸ apply-template: fix-pr-body.py failed: {result.stderr[:200]}", file=sys.stderr)
            return 1

        if not body_fixed.exists():
            print("  ▸ apply-template: fix script produced no output", file=sys.stderr)
            return 1

        fixed_body = body_fixed.read_text(encoding="utf-8")

        # Replace DIGEST_LINK_PLACEHOLDER with actual digest URL
        digest_url = args.digest_url
        state = {}
        if not digest_url:
            # Try state file
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                digest_url = state.get("digest_comment_url", "")
            except Exception:
                pass
        if digest_url and "DIGEST_LINK_PLACEHOLDER" in fixed_body:
            fixed_body = fixed_body.replace("DIGEST_LINK_PLACEHOLDER", digest_url)
            print(f"  ▸ apply-template: replaced DIGEST_LINK_PLACEHOLDER", flush=True)
        if not digest_url and "DIGEST_LINK_PLACEHOLDER" in fixed_body:
            # Only warn in Phase 4+ when digest should exist
            phase_hint = state.get("_completed_phases", []) if state_file.exists() else []
            if any(p.startswith("4") for p in phase_hint):
                print("  ⚠️ apply-template: DIGEST_LINK_PLACEHOLDER remains — no digest_comment_url in state", file=sys.stderr)

        # Update PR
        if _update_pr(platform, pr_id, cli_cmd, fixed_body, platform_info, workspace_dir):
            print("  ✅ apply-template: PR body fixed (template enforced)", flush=True)
            return 0
        else:
            return 1

    finally:
        for f in (body_raw, body_fixed):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
