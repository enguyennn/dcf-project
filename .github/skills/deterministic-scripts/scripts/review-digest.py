#!/usr/bin/env python3
"""Deterministic review-digest pipeline for Phase 4.

Replaces the review_digest + validate_digest + review_digest_retry LLM agents
with a single script that orchestrates:
  1. Load state file → save as upstream-data.json
  2. Run build-digest-input.py → digest-input.json
  3. Run compose-digest.py → digest-output.md
  4. Run validate-digest-format.py (retry once if invalid)
  5. Run post-findings.py (inline PR comments, if findings exist)
  6. Run upsert-digest.py (post digest to PR)

All steps are deterministic — no LLM judgment, no improvisation.

Usage:
    python review-digest.py --pr-url "https://..." --platform ado --state-file state.json
    python review-digest.py --pr-url "https://..." --platform ado --state-file state.json --dry-run
"""

import argparse
import importlib.util
import json
import logging
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


logger = logging.getLogger(__name__)


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

    fallback = Path(tempfile.gettempdir())
    print(
        "WARNING: --workspace-dir not provided; falling back to the shared temp directory",
        file=sys.stderr,
    )
    return fallback


def _run(cmd: list[str], label: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a subprocess with UTF-8 encoding, timeout, and error handling."""
    import platform
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
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
    except subprocess.TimeoutExpired as exc:
        logger.error("%s timed out after %ss", label, timeout, exc_info=exc)
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


def _parse_ado_url(pr_url: str) -> dict:
    """Extract org, project, repo, PR ID from ADO PR URL."""
    return parse_ado_pr_url(pr_url)


# ── Step 1: Build upstream-data.json ─────────────────────────────────────────

_REAL_RISK_LEVELS = {"low", "medium", "high"}


def _has_real_risk_level(data: dict) -> bool:
    """Return True when upstream data already carries an authoritative risk level."""
    return str(data.get("risk_level", "")).lower() in _REAL_RISK_LEVELS


def _load_classify_risk():
    """Load classify-risk.py, whose hyphenated filename cannot be imported normally."""
    module_path = Path(_scripts_dir()) / "classify-risk.py"
    spec = importlib.util.spec_from_file_location("classify_risk", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.classify


def _normalise_changed_files(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _load_changed_files_artifact(path: Path) -> list[str]:
    if not path.is_file():
        return []
    loaded = load_json_robust(path, label="changed-files", default=[])
    return _normalise_changed_files(loaded)


def _artifact_candidates(data: dict, state_file: str, workspace_dir: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    if workspace_dir:
        candidates.append(Path(workspace_dir) / "changed-files.json")
    if data.get("_workspace_dir"):
        candidates.append(Path(str(data["_workspace_dir"])) / "changed-files.json")
    if data.get("changed_files_path"):
        candidates.append(Path(str(data["changed_files_path"])))
    if state_file:
        candidates.append(Path(state_file).resolve().parent / "changed-files.json")

    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _derive_default_target(repo_dir: str) -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _get_changed_files_from_git(data: dict, state_file: str) -> list[str]:
    if not state_file:
        return []
    repo_dir = os.path.dirname(os.path.abspath(state_file))
    if not os.path.isdir(repo_dir):
        return []

    target_branch = str(data.get("target_branch") or "").strip()
    candidates: list[str] = []
    if target_branch:
        candidates.append(target_branch)
        if not target_branch.startswith("origin/"):
            candidates.append(f"origin/{target_branch}")
    else:
        default_target = _derive_default_target(repo_dir)
        if default_target:
            candidates.append(default_target)

    last_error = ""
    for candidate in candidates:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{candidate}...HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        last_error = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        print(f"WARNING: git diff against {candidate} failed: {last_error}", file=sys.stderr)
    return []


def _source_changed_files(data: dict, state_file: str, workspace_dir: str | Path | None) -> list[str]:
    changed_files = _normalise_changed_files(data.get("changed_files"))
    if changed_files:
        return changed_files

    for candidate in _artifact_candidates(data, state_file, workspace_dir):
        changed_files = _load_changed_files_artifact(candidate)
        if changed_files:
            return changed_files

    return _get_changed_files_from_git(data, state_file)


def _populate_risk_from_changed_files(data: dict, state_file: str, workspace_dir: str | Path | None = None) -> None:
    """Populate risk fields when missing; never raise into the digest pipeline."""
    try:
        if _has_real_risk_level(data):
            return
        changed_files = _source_changed_files(data, state_file, workspace_dir)
        if not changed_files:
            return
        classify = _load_classify_risk()
        result = classify(changed_files)
        risk_level = str(result.get("risk_level", "")).lower()
        if risk_level in _REAL_RISK_LEVELS:
            data["risk_level"] = risk_level
            data["risk_signals"] = _normalise_changed_files(result.get("signals", []))
    except Exception as exc:  # pragma: no cover - defensive pipeline guard
        logger.warning("Risk classification failed; continuing without risk", exc_info=exc)
        print(f"WARNING: Risk classification failed; continuing without risk: {exc}", file=sys.stderr)


def build_upstream_data(state_file: str, pr_url: str, platform: str, workspace_dir: str | Path | None = None) -> dict:
    """Load state file and produce upstream-data.json."""
    if state_file and os.path.isfile(state_file):
        data = _load_json(state_file, "state-file")
        if not data:
            print(f"WARNING: State file empty or corrupt: {state_file}", file=sys.stderr)
            data = {}
    else:
        print(f"WARNING: State file not found: {state_file}", file=sys.stderr)
        data = {}

    phase_2 = read_phase_output(data, "2") or {}
    phase_4 = read_phase_output(data, "4") or {}
    phase_4b = read_phase_output(data, "4b") or {}

    for key in ("pr_url", "pr_title", "work_items_linked"):
        if phase_2.get(key) is not None:
            data[key] = phase_2[key]
    for key in ("digest_comment_url", "digest_comment_id"):
        if phase_4.get(key) is not None:
            data[key] = phase_4[key]
    for key in (
        "walkthrough_posted",
        "pr_classification",
        "skip_reason",
        "diagram_count",
        "concepts_explained",
    ):
        if phase_4b.get(key) is not None:
            data[key] = phase_4b[key]

    # Add workflow inputs if missing
    if not data.get("pr_url"):
        data["pr_url"] = pr_url
    if not data.get("platform"):
        data["platform"] = platform

    _populate_risk_from_changed_files(data, state_file, workspace_dir)

    return data


# ── Step 4: Validate digest ──────────────────────────────────────────────────

def validate_digest(digest_path: str) -> dict:
    """Run validate-digest-format.py and return result."""
    validate_script = os.path.join(_scripts_dir(), "validate-digest-format.py")
    result = _run(
        [sys.executable, validate_script, digest_path],
        label="validate-digest-format",
        check=False,
    )
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("validate-digest-format returned invalid JSON; treating digest as invalid", exc_info=exc)
        return {"valid": False, "violations": [f"Validator output not valid JSON: {result.stdout[:200]}"]}


def _resolve_platform(raw_platform: str, pr_url: str, state_file: str) -> str:
    """Resolve platform with fallback: argument → state file → detect-platform.py."""
    if raw_platform in ("ado", "github"):
        return raw_platform

    if state_file and os.path.isfile(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            state_platform = state_data.get("platform", "")
            if state_platform in ("ado", "github"):
                print(f"  ▸ platform: resolved from state file ({state_platform})", flush=True)
                return state_platform
        except (json.JSONDecodeError, OSError):
            pass

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    detect_script = os.path.join(scripts_dir, "detect-platform.py")
    if os.path.isfile(detect_script):
        # Run detect-platform.py from the repo directory so git config lookup finds the right remote.
        repo_cwd = os.path.dirname(os.path.abspath(state_file)) if state_file else None
        try:
            result = subprocess.run(
                [sys.executable, detect_script],
                capture_output=True, text=True, timeout=10,
                cwd=repo_cwd,
            )
            if result.returncode == 0:
                detected = json.loads(result.stdout.strip()).get("platform", "")
                if detected in ("ado", "github"):
                    print(f"  ▸ platform: resolved via detect-platform.py ({detected})", flush=True)
                    return detected
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            pass

    if pr_url:
        if "dev.azure.com" in pr_url or "visualstudio.com" in pr_url:
            print("  ▸ platform: inferred from PR URL (ado)", flush=True)
            return "ado"
        if "github.com" in pr_url:
            print("  ▸ platform: inferred from PR URL (github)", flush=True)
            return "github"

    print("ERROR: Unable to determine platform", file=sys.stderr, flush=True)
    sys.exit(1)


# ── Main Pipeline ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Deterministic review-digest pipeline for Phase 4"
    )
    parser.add_argument("--pr-url", required=True, help="Full PR URL")
    parser.add_argument("--platform", default="", help="ado|github; auto-detected if empty")
    parser.add_argument("--state-file", default="", help="Path to cross-phase state JSON file")
    parser.add_argument("--findings-file", default="", help="Path to code-review-findings.json")
    parser.add_argument("--workspace-dir", default="", help="Directory for per-run workspace artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Skip upsert and findings posting")
    args = parser.parse_args()

    workspace_dir = _resolve_workspace_dir(args.workspace_dir)
    scripts = _scripts_dir()
    platform = _resolve_platform(args.platform, args.pr_url, args.state_file)

    print("═══ Review Digest Pipeline (deterministic) ═══", file=sys.stderr)

    # ── Step 1: Build upstream-data.json ─────────────────────────────────
    print("\n[1/6] Building upstream-data.json from state file...", file=sys.stderr)
    upstream_data = build_upstream_data(args.state_file, args.pr_url, platform, workspace_dir)
    upstream_valid, upstream_issues = validate_upstream_data(upstream_data)
    if not upstream_valid:
        print("FATAL: upstream-data.json validation failed", file=sys.stderr)
        for issue in upstream_issues:
            print(f"  - {issue}", file=sys.stderr)
        print(json.dumps({
            "digest_comment_id": "",
            "overall_verdict": "error",
            "risk_level_displayed": "unknown",
            "bot_threads_found": 0,
            "digest_posted": False,
            "pr_url": args.pr_url,
            "validation_passed": False,
            "error": "invalid upstream-data.json",
        }))
        sys.exit(1)

    upstream_path = os.path.join(workspace_dir, "upstream-data.json")
    with open(upstream_path, "w", encoding="utf-8") as f:
        json.dump(upstream_data, f, indent=2, ensure_ascii=False)
    key_count = len(upstream_data)
    print(f"  ▸ upstream-data.json saved: {key_count} keys", file=sys.stderr)

    # ── Step 2: Build digest-input.json (deterministic script) ───────────
    print("\n[2/6] Building digest-input.json...", file=sys.stderr)
    digest_input_path = os.path.join(workspace_dir, "digest-input.json")
    build_script = os.path.join(scripts, "build-digest-input.py")
    build_result = _run(
        [sys.executable, build_script, upstream_path, "--output-file", digest_input_path],
        label="build-digest-input",
        check=False,
    )
    if build_result.returncode != 0:
        print("FATAL: build-digest-input.py failed", file=sys.stderr)
        print(json.dumps({
            "digest_comment_id": "",
            "overall_verdict": "error",
            "risk_level_displayed": "unknown",
            "bot_threads_found": 0,
            "digest_posted": False,
            "error": f"build-digest-input.py exit {build_result.returncode}",
        }))
        sys.exit(1)

    # Read digest input to extract metadata
    digest_input = _load_json(digest_input_path, "digest-input")
    verdict = digest_input.get("verdict", "unknown")
    risk_level = digest_input.get("risk_level", "unknown")

    # ── Step 3: Compose digest markdown (deterministic script) ───────────
    print("\n[3/6] Composing digest markdown...", file=sys.stderr)
    digest_md_path = os.path.join(workspace_dir, "digest-output.md")
    compose_script = os.path.join(scripts, "compose-digest.py")
    _run(
        [sys.executable, compose_script, digest_input_path, "--output-file", digest_md_path],
        label="compose-digest",
    )

    # ── Step 4: Validate digest format ───────────────────────────────────
    print("\n[4/6] Validating digest format...", file=sys.stderr)
    validation = validate_digest(digest_md_path)
    if not validation.get("valid", False):
        violations = validation.get("violations", [])
        print(f"  ▸ Validation failed ({len(violations)} violations), retrying...", file=sys.stderr)
        for v in violations[:5]:
            print(f"    - {v}", file=sys.stderr)

        # Retry: re-run build + compose
        _run(
            [sys.executable, build_script, upstream_path, "--output-file", digest_input_path],
            label="build-digest-input (retry)",
        )
        _run(
            [sys.executable, compose_script, digest_input_path, "--output-file", digest_md_path],
            label="compose-digest (retry)",
        )

        # Re-validate
        validation = validate_digest(digest_md_path)
        if not validation.get("valid", False):
            retry_violations = validation.get("violations", [])
            print(f"  ▸ Validation still failed after retry ({len(retry_violations)} violations)", file=sys.stderr)
            for v in retry_violations[:5]:
                print(f"    - {v}", file=sys.stderr)
            # Continue anyway — posting an imperfect digest is better than no digest
            print("  ▸ Proceeding with imperfect digest", file=sys.stderr)
        else:
            print("  ▸ Validation passed on retry ✅", file=sys.stderr)
    else:
        print("  ▸ Validation passed ✅", file=sys.stderr)

    # ── Step 5: Post inline findings (if available) ──────────────────────
    print("\n[5/6] Posting inline findings...", file=sys.stderr)
    findings_file = args.findings_file or os.path.join(workspace_dir, "code-review-findings.json")
    findings_posted = 0
    if os.path.isfile(findings_file):
        post_script = os.path.join(scripts, "post-findings.py")
        post_cmd = [
            sys.executable, post_script,
            "--platform", platform,
            "--pr-url", args.pr_url,
            "--findings-file", findings_file,
        ]
        if args.dry_run:
            post_cmd.append("--dry-run")
        post_result = _run(post_cmd, label="post-findings", check=False)
        if post_result.returncode == 0:
            try:
                post_output = json.loads(post_result.stdout)
                findings_posted = post_output.get("posted", 0)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("post-findings returned invalid JSON; defaulting posted count to 0", exc_info=exc)
        else:
            print(
                f"  WARNING: post-findings failed (exit {post_result.returncode}); continuing without inline comment count",
                file=sys.stderr,
            )
    else:
        print("  ▸ No findings file found — skipping inline comments", file=sys.stderr)

    # ── Step 6: Upsert digest to PR ──────────────────────────────────────
    print("\n[6/6] Upserting digest to PR...", file=sys.stderr)
    upsert_script = os.path.join(scripts, "upsert-digest.py")
    digest_comment_id = ""
    digest_posted = False
    upsert_exit_code = 0
    if args.dry_run:
        print("  ▸ DRY RUN: skipping upsert", file=sys.stderr)
    else:
        upsert_result = _run(
            [sys.executable, upsert_script,
             "--platform", platform,
             "--pr-url", args.pr_url,
             "--content-file", digest_md_path,
             "--workspace-dir", str(workspace_dir)],
            label="upsert-digest",
            check=False,
        )
        upsert_exit_code = upsert_result.returncode
        digest_posted = upsert_result.returncode == 0
        if digest_posted:
            # Extract comment/thread ID from upsert output
            try:
                upsert_output = json.loads(upsert_result.stdout)
                digest_comment_id = str(upsert_output.get("thread_id", upsert_output.get("comment_id", "")))
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("upsert-digest returned invalid JSON; digest comment id will be left blank", exc_info=exc)
        else:
            print(
                f"  WARNING: upsert-digest failed (exit {upsert_result.returncode}); digest_posted=False",
                file=sys.stderr,
            )

    # Build digest comment URL
    digest_comment_url = ""
    if digest_posted and digest_comment_id:
        if "dev.azure.com" in args.pr_url or "visualstudio.com" in args.pr_url:
            digest_comment_url = f"{args.pr_url}?discussionId={digest_comment_id}"
        elif "github.com" in args.pr_url:
            digest_comment_url = f"{args.pr_url}#issuecomment-{digest_comment_id}"

    # ── Output result JSON to stdout ─────────────────────────────────────
    result = {
        "digest_comment_id": digest_comment_id,
        "digest_comment_url": digest_comment_url,
        "overall_verdict": verdict,
        "risk_level_displayed": risk_level,
        "bot_threads_found": findings_posted,
        "digest_posted": digest_posted,
        "pr_url": args.pr_url,
        "validation_passed": validation.get("valid", False),
    }

    if upsert_exit_code != 0:
        result["error"] = f"upsert-digest.py exit {upsert_exit_code}"

    print(json.dumps(result))
    print(f"\n{'═' * 50}", file=sys.stderr)
    print(f"PIPELINE_COMPLETE: verdict={verdict} | risk={risk_level} | findings_posted={findings_posted}", file=sys.stderr)
    if digest_posted:
        print("✅ Review digest posted to PR.", file=sys.stderr)
    elif args.dry_run:
        print("ℹ️ Review digest not posted (dry run).", file=sys.stderr)
    else:
        print("⚠️ Review digest was not posted to PR.", file=sys.stderr)
    print(f"PR: {args.pr_url}", file=sys.stderr)

    if upsert_exit_code != 0:
        sys.exit(upsert_exit_code)


if __name__ == "__main__":
    main()
