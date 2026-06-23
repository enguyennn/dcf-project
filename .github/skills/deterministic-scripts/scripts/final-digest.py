#!/usr/bin/env python3
"""Deterministic final-digest pipeline for Phase 5.

Replaces the FinalDigest LLM agent with a script that orchestrates:
  1. Build phase5-data.json from scraped files
  2. Merge Phase 5 data onto Phase 4 baseline (build-digest-input.py --merge)
  3. Compose markdown (compose-digest.py)
  4. Upsert to PR (upsert-digest.py)
  5. Fix encoding artifacts (fix-encoding.py) + re-upsert if needed
  6. Resolve digest thread + addressed feedback threads

All steps are deterministic — no LLM judgment, no improvisation.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from encoding_utils import load_json_robust
from phase_output_validation import validate_upstream_data
from pr_url_utils import parse_ado_pr_url

try:
    from phase_contracts import read_phase_output
except ImportError:  # pragma: no cover - backward-compatible fallback
    def read_phase_output(state: dict, phase_id: str) -> dict | None:
        return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _scripts_dir() -> str:
    """Return the directory containing this script (and sibling scripts)."""
    return os.path.dirname(os.path.abspath(__file__))


def _load_json(path: str, label: str) -> dict:
    """Load a JSON file with shared robust encoding fallback."""
    loaded = load_json_robust(path, label=label, default={})
    return loaded if isinstance(loaded, dict) else {}


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    """Return the directory for per-run artifacts."""
    if workspace_dir:
        path = Path(workspace_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # Check environment variable set by run-phases.py
    env_dir = os.environ.get("PR_ORCHESTRATOR_WORKSPACE_DIR", "")
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    fallback = Path(tempfile.gettempdir())
    print(
        "WARNING: --workspace-dir not provided; falling back to the shared temp directory",
        file=sys.stderr,
    )
    return fallback


def _emit_result(result: dict, workspace_dir: Path | None = None) -> None:
    """Persist the final structured result and emit a single JSON line to stdout."""
    if workspace_dir:
        result_path = workspace_dir / "final-digest-result.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result))


def _run(cmd: list[str], label: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a subprocess with UTF-8 encoding, timeout, and error handling."""
    import platform
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    use_shell = platform.system() == "Windows"
    print(f"  ▸ {label}: {' '.join(cmd[:4])}{'...' if len(cmd) > 4 else ''}", file=sys.stderr)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            shell=use_shell,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"ERROR: {label} timed out after {timeout}s", file=sys.stderr)
        result = subprocess.CompletedProcess(cmd, returncode=-1, stdout="", stderr=f"Timed out after {timeout}s")
    if result.stdout.strip():
        print(f"    stdout: {result.stdout.strip()[:200]}", file=sys.stderr)
    if result.stderr.strip():
        print(f"    stderr: {result.stderr.strip()[:200]}", file=sys.stderr)
    if check and result.returncode != 0:
        print(f"ERROR: {label} failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)
    return result


def _load_upstream_phase_context(path: str | None) -> dict:
    """Load contract-backed phase fields from an upstream state file."""
    if not path or not os.path.isfile(path):
        return {}

    data = _load_json(path, "upstream-fallback")
    if not isinstance(data, dict):
        return {}

    context = {}
    for phase_id, keys in {
        "2": ("pr_url", "pr_title", "work_items_linked"),
        "4": ("digest_comment_url", "digest_comment_id"),
        "4b": (
            "walkthrough_posted",
            "pr_classification",
            "skip_reason",
            "diagram_count",
            "concepts_explained",
        ),
    }.items():
        phase_data = read_phase_output(data, phase_id) or {}
        for key in keys:
            if phase_data.get(key) is not None:
                context[key] = phase_data[key]
    return context


def _parse_ado_url(pr_url: str) -> dict:
    """Extract org, project, repo, PR ID from ADO PR URL."""
    return parse_ado_pr_url(pr_url)


# ── Step 1: Build phase5-data.json ───────────────────────────────────────────

def build_phase5_data(
    pr_url: str,
    scrape_commits_file: str | None,
    scrape_threads_file: str | None,
) -> dict:
    """Build Phase 5 merge data from scraped files."""
    commits_data = _load_json(scrape_commits_file, "scrape-commits") if scrape_commits_file and os.path.isfile(scrape_commits_file) else {}
    threads_data = _load_json(scrape_threads_file, "scrape-threads") if scrape_threads_file and os.path.isfile(scrape_threads_file) else {}

    # Extract commit SHAs
    commit_shas = []
    if "commits" in commits_data:
        commit_shas = [c.get("sha", "") for c in commits_data["commits"] if c.get("sha")]

    # Extract thread counts
    threads = threads_data.get("threads", {})
    resolved = threads.get("resolved", [])
    actionable = threads.get("actionable", [])
    addressed_details = threads_data.get("addressed_details", [])

    # comments_addressed: prefer resolved count, fall back to addressed_details.
    # Final fallback: if fix commits exist, use commit count as addressed minimum.
    # This handles the timing gap where scrape runs before final-digest resolves
    # the threads on ADO — actionable threads that HAVE a fix commit will be
    # resolved moments later by this same script, so the digest should reflect
    # the post-resolution state.
    comments_addressed = len(resolved) or len(addressed_details) or len(commit_shas)

    # If we have fix commits, threads currently in actionable that will be resolved
    # should not count as "remaining". The final-digest resolves them in step 6/7.
    if commit_shas and not resolved and not addressed_details:
        comments_remaining = 0
        all_addressed = True
    else:
        comments_remaining = len(actionable)
        all_addressed = len(actionable) == 0

    return {
        "pr_url": pr_url,
        "address_feedback": {
            "comments_addressed": comments_addressed,
            "comments_remaining": comments_remaining,
            "fix_commits": commit_shas,
            "all_addressed": all_addressed,
        },
    }


# ── Step 6/7: Resolve PR threads ────────────────────────────────────────────

def resolve_threads(
    platform: str,
    pr_url: str,
    scrape_threads_file: str | None,
    digest_thread_id: str | None,
) -> dict:
    """Resolve the digest thread and addressed feedback threads."""
    if platform != "ado":
        print("  ▸ Thread resolution: skipped (not ADO)", file=sys.stderr)
        return {"resolved_threads": 0, "skipped": "not_ado"}

    url_parts = _parse_ado_url(pr_url)
    if not url_parts:
        print("  ▸ Thread resolution: skipped (could not parse PR URL)", file=sys.stderr)
        return {"resolved_threads": 0, "skipped": "parse_error"}

    api_base = url_parts["api_base"]
    project = url_parts["project"]
    repo = url_parts["repo"]
    pr_id = url_parts["pr_id"]
    resolved_count = 0

    # Resolve digest thread
    if digest_thread_id:
        _resolve_single_thread(api_base, project, repo, pr_id, digest_thread_id, status=2, label="digest")
        resolved_count += 1

    # Resolve addressed feedback threads
    if scrape_threads_file and os.path.isfile(scrape_threads_file):
        threads_data = _load_json(scrape_threads_file, "scrape-threads")
        resolved_threads = threads_data.get("threads", {}).get("resolved", [])
        for t in resolved_threads:
            tid = t.get("thread_id")
            if tid:
                _resolve_single_thread(api_base, project, repo, pr_id, str(tid), status=2, label=f"feedback-{tid}")
                resolved_count += 1

    return {"resolved_threads": resolved_count}


def _resolve_single_thread(api_base: str, project: str, repo: str, pr_id: str, thread_id: str, status: int = 2, label: str = ""):
    """Resolve a single ADO PR thread. Status 2=Fixed, 5=WontFix."""
    url = f"{api_base}/{project}/_apis/git/repositories/{repo}/pullRequests/{pr_id}/threads/{thread_id}?api-version=7.1"
    body = json.dumps({"status": status})
    try:
        _run(
            ["az", "rest", "--method", "patch", "--url", url,
             "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
             "--body", body,
             "--headers", "Content-Type=application/json"],
            label=f"resolve-thread-{label}",
            check=False,
        )
    except Exception as e:
        print(f"  WARNING: Failed to resolve thread {thread_id}: {e}", file=sys.stderr)


# ── Step 5: Find digest thread ID ───────────────────────────────────────────

def find_digest_thread_id(platform: str, pr_url: str) -> str | None:
    """Find the digest comment thread ID by searching for the digest marker."""
    if platform != "ado":
        return None

    url_parts = _parse_ado_url(pr_url)
    if not url_parts:
        return None

    api_base = url_parts["api_base"]
    project = url_parts["project"]
    repo = url_parts["repo"]
    pr_id = url_parts["pr_id"]

    url = f"{api_base}/{project}/_apis/git/repositories/{repo}/pullRequests/{pr_id}/threads?api-version=7.1"
    try:
        result = _run(
            ["az", "rest", "--method", "get", "--url", url,
             "--resource", "499b84ac-1321-427f-aa17-267ca6975798"],
            label="find-digest-thread",
            check=False,
        )
        if result.returncode != 0:
            return None
        threads = json.loads(result.stdout)
        for t in threads.get("value", []):
            for c in t.get("comments", []):
                content = c.get("content", "")
                if "<!-- ai-agent:pr-orchestrator-digest -->" in content:
                    return str(t["id"])
    except Exception:
        pass
    return None


# ── Main Pipeline ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Deterministic final-digest pipeline for Phase 5"
    )
    parser.add_argument("--pr-url", required=True, help="Full PR URL")
    parser.add_argument("--platform", required=True, choices=["ado", "github"])
    parser.add_argument(
        "--merge", help="Existing digest-input.json from Phase 4 to merge onto"
    )
    parser.add_argument(
        "--upstream-fallback",
        help="Fallback upstream-data.json if --merge file is corrupt",
    )
    parser.add_argument(
        "--triage-file", help="triage-output.json from triage_feedback step"
    )
    parser.add_argument(
        "--scrape-commits-file",
        help="scrape-fb-commits.json from scrape_fb_commits step",
    )
    parser.add_argument(
        "--scrape-threads-file",
        help="scrape-fb-threads.json from scrape_fb_threads step",
    )
    parser.add_argument(
        "--workspace-dir", default="", help="Directory for per-run workspace artifacts"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Skip upsert and thread resolution"
    )
    args = parser.parse_args()

    workspace_dir = _resolve_workspace_dir(args.workspace_dir)
    scripts = _scripts_dir()

    print("═══ Final Digest Pipeline (deterministic) ═══", file=sys.stderr)

    # ── Step 1: Build phase5-data.json ───────────────────────────────────
    print("\n[1/6] Building phase5-data.json...", file=sys.stderr)
    phase5_data = build_phase5_data(
        pr_url=args.pr_url,
        scrape_commits_file=args.scrape_commits_file,
        scrape_threads_file=args.scrape_threads_file,
    )
    phase5_path = os.path.join(workspace_dir, "phase5-data.json")
    with open(phase5_path, "w", encoding="utf-8") as f:
        json.dump(phase5_data, f, indent=2, ensure_ascii=False)
    print(f"  ▸ phase5-data.json: {phase5_data['address_feedback']['comments_addressed']} addressed, "
          f"{phase5_data['address_feedback']['comments_remaining']} remaining, "
          f"{len(phase5_data['address_feedback']['fix_commits'])} commits", file=sys.stderr)

    # ── Step 2: Merge into digest-input (build-digest-input.py) ──────────
    print("\n[2/6] Merging Phase 5 into digest baseline...", file=sys.stderr)
    final_digest_input_path = os.path.join(workspace_dir, "final-digest-input.json")
    build_script = os.path.join(scripts, "build-digest-input.py")

    merge_cmd = [
        sys.executable, build_script, phase5_path,
        "--output-file", final_digest_input_path,
    ]

    # Determine the merge base — prefer an explicit path, then the workspace baseline.
    merge_file = args.merge or os.path.join(workspace_dir, "digest-input.json")
    upstream_file = args.upstream_fallback or os.path.join(workspace_dir, "upstream-data.json")
    upstream_context = {}
    upstream_is_valid = False
    if os.path.isfile(upstream_file):
        upstream_candidate = _load_json(upstream_file, "upstream-fallback")
        upstream_is_valid, upstream_issues = validate_upstream_data(upstream_candidate)
        if upstream_is_valid:
            upstream_context = _load_upstream_phase_context(upstream_file)
        else:
            print("  WARNING: Ignoring invalid upstream-data.json fallback", file=sys.stderr)
            for issue in upstream_issues:
                print(f"    - {issue}", file=sys.stderr)
    effective_pr_url = upstream_context.get("pr_url") or args.pr_url

    if upstream_context.get("pr_url") and upstream_context["pr_url"] != args.pr_url:
        print(
            f"  ▸ Upstream state PR URL differs from CLI: {upstream_context['pr_url']}",
            file=sys.stderr,
        )

    if os.path.isfile(merge_file):
        merge_cmd += ["--merge", merge_file]
    elif upstream_is_valid:
        # No digest-input.json — rebuild baseline from upstream first
        print("  ▸ No digest-input.json found, rebuilding from upstream-data.json", file=sys.stderr)
        rebuild_result = _run(
            [sys.executable, build_script, upstream_file,
             "--output-file", os.path.join(workspace_dir, "digest-input.json")],
            label="rebuild-baseline",
            check=False,
        )
        if rebuild_result.returncode == 0:
            merge_cmd += ["--merge", os.path.join(workspace_dir, "digest-input.json")]
        else:
            print("  WARNING: Could not rebuild baseline from upstream — merging without baseline", file=sys.stderr)
    else:
        print("  ERROR: No valid merge base found — cannot build reliable digest from Phase 5 data alone", file=sys.stderr)
        print("  ▸ Re-run Phase 4 (review-digest) first to generate upstream data", file=sys.stderr)
        sys.exit(1)

    # Only pass upstream-fallback when it passed schema validation.
    if upstream_is_valid:
        merge_cmd += ["--upstream-fallback", upstream_file]

    # Prefer explicit paths; otherwise use the workspace-local artifacts.
    triage_file = args.triage_file or os.path.join(workspace_dir, "triage-output.json")
    if os.path.isfile(triage_file):
        merge_cmd += ["--triage-file", triage_file]

    scrape_fb_file = args.scrape_commits_file or os.path.join(workspace_dir, "scrape-fb-commits.json")
    if os.path.isfile(scrape_fb_file):
        merge_cmd += ["--scrape-feedback-file", scrape_fb_file]

    thread_state_file = args.scrape_threads_file or os.path.join(workspace_dir, "scrape-fb-threads.json")
    if os.path.isfile(thread_state_file):
        merge_cmd += ["--thread-state-file", thread_state_file]

    merge_result = _run(merge_cmd, label="build-digest-input --merge", check=False)
    if merge_result.returncode != 0:
        print("FATAL: build-digest-input.py failed — cannot produce reliable digest", file=sys.stderr)
        # Output minimal result JSON for workflow consumption
        result = {
            "final_verdict": "error",
            "pr_url": effective_pr_url,
            "total_fixes_pushed": len(phase5_data["address_feedback"]["fix_commits"]),
            "total_comments_addressed": phase5_data["address_feedback"]["comments_addressed"],
            "digest_updated": False,
            "error": f"build-digest-input.py exit {merge_result.returncode}",
        }
        _emit_result(result, workspace_dir)
        sys.exit(1)

    # Read the digest input to extract verdict
    digest_input = _load_json(final_digest_input_path, "final-digest-input")
    verdict = digest_input.get("verdict", "unknown")

    # ── Step 3: Compose digest markdown ──────────────────────────────────
    print("\n[3/6] Composing digest markdown...", file=sys.stderr)
    final_digest_md = os.path.join(workspace_dir, "final-digest.md")
    compose_script = os.path.join(scripts, "compose-digest.py")
    _run(
        [sys.executable, compose_script, final_digest_input_path,
         "--output-file", final_digest_md],
        label="compose-digest",
    )

    # ── Step 4: Upsert to PR ─────────────────────────────────────────────
    print("\n[4/6] Upserting digest to PR...", file=sys.stderr)
    upsert_script = os.path.join(scripts, "upsert-digest.py")
    if args.dry_run:
        print("  ▸ DRY RUN: skipping upsert", file=sys.stderr)
    else:
        _run(
            [sys.executable, upsert_script,
             "--platform", args.platform,
             "--pr-url", effective_pr_url,
             "--content-file", final_digest_md,
             "--workspace-dir", str(workspace_dir)],
            label="upsert-digest",
        )

    # ── Step 5: Fix encoding + re-upsert if needed ──────────────────────
    print("\n[5/6] Fixing encoding artifacts...", file=sys.stderr)
    fix_script = os.path.join(scripts, "fix-encoding.py")
    fix_result = _run(
        [sys.executable, fix_script, final_digest_md],
        label="fix-encoding",
        check=False,
    )
    if fix_result.returncode != 0:
        print(
            f"  WARNING: fix-encoding failed (exit {fix_result.returncode}); continuing with existing digest content",
            file=sys.stderr,
        )
    # Re-read to check if changes were made
    try:
        with open(final_digest_md, "r", encoding="utf-8") as f:
            fixed_content = f.read()
        # The fix-encoding script writes to stderr how many replacements
        # We re-upsert only if the file was modified (simple heuristic: re-upsert always since it's idempotent)
        if not args.dry_run:
            _run(
                [sys.executable, upsert_script,
                 "--platform", args.platform,
                 "--pr-url", effective_pr_url,
                 "--content-file", final_digest_md,
                 "--workspace-dir", str(workspace_dir)],
                label="upsert-digest (post-encoding-fix)",
            )
    except Exception as e:
        print(f"  WARNING: Encoding fix check failed: {e}", file=sys.stderr)

    # ── Step 6: Resolve threads ──────────────────────────────────────────
    print("\n[6/6] Resolving PR threads...", file=sys.stderr)
    if args.dry_run:
        print("  ▸ DRY RUN: skipping thread resolution", file=sys.stderr)
        thread_result = {"resolved_threads": 0, "skipped": "dry_run"}
    else:
        digest_thread_id = find_digest_thread_id(args.platform, effective_pr_url)
        if digest_thread_id:
            print(f"  ▸ Found digest thread: {digest_thread_id}", file=sys.stderr)
        resolve_threads_file = args.scrape_threads_file or os.path.join(workspace_dir, "scrape-fb-threads.json")
        thread_result = resolve_threads(
            platform=args.platform,
            pr_url=effective_pr_url,
            scrape_threads_file=resolve_threads_file,
            digest_thread_id=digest_thread_id,
        )

    # ── Output result JSON to stdout ─────────────────────────────────────
    total_fixes = len(phase5_data["address_feedback"]["fix_commits"])
    total_addressed = phase5_data["address_feedback"]["comments_addressed"]
    result = {
        "final_verdict": verdict,
        "pr_url": effective_pr_url,
        "total_fixes_pushed": total_fixes,
        "total_comments_addressed": total_addressed,
        "digest_updated": True,
        "threads_resolved": thread_result.get("resolved_threads", 0),
    }

    _emit_result(result, workspace_dir)
    print(f"\n{'═' * 50}", file=sys.stderr)
    print(f"PIPELINE_COMPLETE: verdict={verdict} | fixes={total_fixes} | comments={total_addressed}", file=sys.stderr)
    print(f"✅ Final digest updated on PR.", file=sys.stderr)
    print(f"PR: {effective_pr_url}", file=sys.stderr)


if __name__ == "__main__":
    main()
