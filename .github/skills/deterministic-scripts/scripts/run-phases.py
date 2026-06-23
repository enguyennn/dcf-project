#!/usr/bin/env python3
"""Deterministic phase driver for the PR Orchestrator pipeline.

Runs Conductor workflows in strict order, merging state after each phase.
Eliminates LLM-directed phase sequencing — the phase order is hardcoded
and forward-only.

Usage:
    # YOLO fast (skip Phase 3)
    python run-phases.py --mode yolo-fast --target-branch main

    # YOLO full
    python run-phases.py --mode yolo --target-branch main

    # With explicit output file
    python run-phases.py --mode yolo-fast --target-branch main --output-file result.json

    # Resume after interactive gate
    python run-phases.py --mode interactive --target-branch main --resume

    # Resume with explicit state file
    python run-phases.py --mode interactive --target-branch main --resume --state-file /path/to/state.json

Exit codes:
    0 = all phases completed successfully
    1 = one or more phases failed after retries
    10 = paused at interactive gate (interactive mode only)
    11 = checkpoint reached (live mode); re-run same command to auto-resume
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from encoding_utils import load_json_robust, validate_encoding
from retry_utils import run_with_retry

try:
    from phase_contracts import (
        build_phase_meta,
        compute_fingerprint,
        is_phase_fresh,
        read_phase_output,
        validate_phase_output,
    )
except ImportError:  # pragma: no cover - backward-compatible fallback
    _FALLBACK_PHASE_ALIASES = {
        "1c": {},
        "2": {},
    }
    _FALLBACK_PHASE_KEYS = {
        "1c": ["code_review_findings"],
        "2": ["pr_url"],
    }

    def read_phase_output(state: dict, phase_id: str) -> dict | None:
        if not isinstance(state, dict):
            return None
        phases = state.get("_phases", {})
        if isinstance(phases, dict) and isinstance(phases.get(phase_id), dict):
            return dict(phases[phase_id])
        raw = {}
        for key in _FALLBACK_PHASE_KEYS.get(phase_id, []):
            if key in state:
                raw[key] = state[key]
        return raw or None

    def validate_phase_output(phase_id: str, data: dict) -> tuple[bool, list[str]]:
        return True, []

    def build_phase_meta(phase_id: str, output: dict, duration_s: float, fingerprint: dict | None = None) -> dict:
        return {}

    def compute_fingerprint(pr_url: str | None = None) -> dict:
        return {}

    def is_phase_fresh(state: dict, phase_id: str, current_fingerprint: dict | None = None) -> bool:
        return True


# ---------------------------------------------------------------------------
# Phase specification
# ---------------------------------------------------------------------------

@dataclass
class PhaseSpec:
    """Specification for a single pipeline phase."""

    id: str
    workflow: str
    merge_phase: Optional[str] = None
    inputs: list[str] = field(default_factory=list)
    conductor_flags: list[str] = field(default_factory=list)
    merge_clear_keys: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    max_retries: int = 2
    timeout_s: int = 1800  # per-attempt subprocess timeout (seconds); default 30 min
    skip_when: Optional[str] = None  # callable name for conditional skip
    prerequisites: list[str] = field(default_factory=list)  # state keys required before run


PHASE_SEQUENCE = [
    PhaseSpec(
        id="1a",
        workflow="phase1a-digests.yaml",
        merge_phase="1a",
        inputs=["target_branch", "scripts_dir"],
        required_outputs=["business_logic_digest"],
    ),
    PhaseSpec(
        id="1b",
        workflow="phase1b-testgen.yaml",
        merge_phase="1b",
        inputs=["target_branch", "scripts_dir"],
    ),
    PhaseSpec(
        id="1c",
        workflow="phase1c-codereview.yaml",
        merge_phase="1c",
        inputs=["target_branch", "scripts_dir", "workspace_dir"],
        timeout_s=6000,  # 100 min — code review needs headroom over 90-min session
    ),
    PhaseSpec(
        id="1d",
        workflow="phase1d-codefix.yaml",
        merge_phase="1d",
        inputs=["target_branch", "findings_json_path", "scripts_dir", "workspace_dir"],
        merge_clear_keys=["code_fix"],
        skip_when="no_actionable_findings",
        prerequisites=["code_review_findings"],
        timeout_s=6000,  # 100 min — iterative fix-test loops need headroom over 90-min session
    ),
    PhaseSpec(
        id="2",
        workflow="phase2-create-pr.yaml",
        merge_phase="2",
        inputs=["target_branch", "state_file", "scripts_dir", "workspace_dir"],
        required_outputs=["pr_url"],
    ),
    PhaseSpec(
        id="3",
        workflow="phase3-watch-fix.yaml",
        merge_phase="3",
        inputs=["pr_url", "target_branch", "scripts_dir"],
        prerequisites=["pr_url"],
        timeout_s=7800,  # 130 min — CI watch + fix loop needs headroom over 2-hr session
    ),
    PhaseSpec(
        id="4",
        workflow="phase4-review-digest.yaml",
        merge_phase="4",
        inputs=["pr_url", "target_branch", "state_file", "scripts_dir", "workspace_dir"],
        prerequisites=["pr_url"],
    ),
    PhaseSpec(
        id="5",
        workflow="phase5-feedback.yaml",
        merge_phase="5",
        inputs=["pr_url", "target_branch", "scripts_dir", "workspace_dir"],
        conductor_flags=["--skip-gates"],
        prerequisites=["pr_url"],
        timeout_s=7800,  # 130 min — interactive feedback loop needs headroom over 2-hr session
    ),
]

# Lookup table: phase id → PhaseSpec
PHASE_BY_ID: dict[str, PhaseSpec] = {p.id: p for p in PHASE_SEQUENCE}
VALID_PHASE_IDS: list[str] = [p.id for p in PHASE_SEQUENCE]

# Phases to skip per mode
MODE_SKIP: dict[str, list[str]] = {
    "yolo": [],
    "yolo-fast": ["3"],
    "interactive": [],
    "live": [],
    "live-fast": ["3"],
}

# Interactive gates: pause AFTER these phases complete (interactive mode only).
# Gates fire after the phase is marked complete and state is saved,
# so --resume picks up at the next phase.
INTERACTIVE_GATES: dict[str, str] = {
    "1a": "Business logic and test coverage digests complete.",
    "1b": "Unit test generation complete. New tests have been written and committed.",
    "1c": "AI code review complete. Findings classified as mechanical (auto-fixable) or human-judgment.",
    "1d": "Auto-fix of mechanical findings complete.",
    "2": "PR created. Review the PR before CI monitoring begins.",
    "3": "CI build monitoring complete.",
    "4": "Review digest posted. Continue to address all PR feedback (bot and human).",
}

CHECKPOINT_EXIT_CODE = 11
CHECKPOINT_MODES = frozenset({"live", "live-fast"})
# Maximum number of phase result entries stored in state to prevent unbounded growth
# across long-running pipelines. Since the pipeline has ~12 phases, this is a soft cap.
_MAX_PHASE_RESULTS = 20


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state(state_file: Path) -> dict:
    """Load the cross-phase state file."""
    loaded = load_json_robust(state_file, label="state-file", default={})
    return loaded if isinstance(loaded, dict) else {}


def save_state(state_file: Path, state: dict) -> None:
    """Atomically save the cross-phase state file."""
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_file)


def get_completed_phases(state: dict) -> list[str]:
    """Get list of completed phase IDs from state."""
    return state.get("_completed_phases", [])


def mark_phase_completed(state: dict, phase_id: str) -> None:
    """Mark a phase as completed in state."""
    completed = state.get("_completed_phases", [])
    if phase_id not in completed:
        completed.append(phase_id)
    state["_completed_phases"] = completed


PHASE_OUTPUT_KEY_MAP: dict[str, str] = {
    "business_logic_digest": "1a",
    "test_coverage_digest": "1a",
    "tests_run": "1a",
    "tests_passed": "1a",
    "tests_failed": "1a",
    "code_review_findings": "1c",
    "human_judgment_findings": "1c",
    "pr_url": "2",
    "pr_title": "2",
    "work_items_linked": "2",
    "digest_comment_url": "4",
    "digest_comment_id": "4",
    "walkthrough_posted": "4b",
    "pr_classification": "4b",
    "skip_reason": "4b",
    "diagram_count": "4b",
    "concepts_explained": "4b",
}


def _state_value(state: dict, key: str):
    phase_id = PHASE_OUTPUT_KEY_MAP.get(key)
    if phase_id:
        phase_output = read_phase_output(state, phase_id) or {}
        if isinstance(phase_output, dict) and phase_output.get(key) is not None:
            return phase_output.get(key)
    return state.get(key)


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------

def create_workspace_dir(run_id: str, workspace_dir: Optional[Path] = None) -> Path:
    """Create and return the per-run workspace directory."""
    if workspace_dir:
        workspace = Path(workspace_dir)
    else:
        workspace = Path(tempfile.gettempdir()) / f"pr-orchestrator-{run_id}"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def cleanup_workspace_dir(workspace_dir: Optional[Path]) -> None:
    """Remove a per-run workspace directory if it exists."""
    if not workspace_dir:
        return
    try:
        shutil.rmtree(workspace_dir)
    except OSError as exc:
        print(f"WARNING: Failed to remove workspace {workspace_dir}: {exc}", flush=True)


def _resolve_plugins_dir() -> Path:
    return (
        Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
        / ".copilot"
        / "installed-plugins"
        / "octane"
        / "octane-pr-orchestrator"
    )


def _resolve_workflow_dir() -> Path:
    return _resolve_plugins_dir() / "workflows"


def _resolve_scripts_dir() -> Path:
    return _resolve_plugins_dir() / "skills" / "deterministic-scripts" / "scripts"


def _detect_platform_from_remote(work_dir: Optional[Path] = None) -> Optional[str]:
    """Detect platform (ado/github) directly from git remote URL. Fast, no external CLIs."""
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True, text=True, timeout=10,
            cwd=str(work_dir) if work_dir else None,
        )
        if result.returncode == 0:
            text = result.stdout.lower()
            if "dev.azure.com" in text or "visualstudio.com" in text:
                return "ado"
            if "github.com" in text:
                return "github"
    except Exception:
        pass
    return None


def _run_bootstrap(
    target_branch: str,
    existing_pr: str = "",
    work_dir: Optional[Path] = None,
) -> dict:
    """Run deterministic bootstrap script and return parsed JSON."""
    scripts_dir = _resolve_scripts_dir()
    bootstrap_script = scripts_dir / "bootstrap.py"
    cmd = [sys.executable, str(bootstrap_script), "--target-branch", target_branch]
    if existing_pr:
        cmd.extend(["--existing-pr", existing_pr])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(work_dir) if work_dir else None,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Bootstrap failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Bootstrap returned invalid JSON: {exc}") from exc


def resolve_inputs(
    phase: PhaseSpec,
    state: dict,
    state_file: Path,
    target_branch: str,
    scripts_dir: Path,
    workspace_dir: Path,
    existing_pr: Optional[str] = None,
    bootstrap: Optional[dict] = None,
) -> dict[str, str]:
    """Resolve phase inputs from state and CLI args.

    Returns a dict of input_name -> value for Conductor --input flags.
    Raises ValueError if a required input cannot be resolved.
    """
    resolved: dict[str, str] = {}

    for inp in phase.inputs:
        if inp == "target_branch":
            resolved[inp] = target_branch
        elif inp == "state_file":
            resolved[inp] = str(state_file)
        elif inp == "scripts_dir":
            resolved[inp] = str(scripts_dir)
        elif inp == "workspace_dir":
            resolved[inp] = str(workspace_dir)
        elif inp == "pr_url":
            pr_url = existing_pr or _state_value(state, "pr_url")
            if not pr_url:
                raise ValueError(
                    f"Phase {phase.id} requires pr_url but it's not in state "
                    f"and --existing-pr was not provided"
                )
            resolved[inp] = pr_url
        elif inp == "findings_json_path":
            # Extract code_review_findings from state and write to the per-run workspace.
            findings = _state_value(state, "code_review_findings") or {}
            if isinstance(findings, str):
                try:
                    findings = json.loads(findings)
                    if isinstance(findings, str):
                        findings = json.loads(findings)
                except (json.JSONDecodeError, TypeError):
                    try:
                        findings = json.loads(findings.replace("\\'", "'"))
                    except (json.JSONDecodeError, TypeError):
                        findings = {}
            if not isinstance(findings, (dict, list)):
                findings = {}
            workspace_dir.mkdir(parents=True, exist_ok=True)
            findings_path = workspace_dir / "pr-orchestrator-1c-findings.json"
            findings_path.write_text(
                json.dumps(findings, ensure_ascii=False), encoding="utf-8"
            )
            resolved[inp] = str(findings_path)
        else:
            # Try to resolve from state
            val = state.get(inp)
            if val is not None:
                resolved[inp] = str(val) if not isinstance(val, str) else val
            else:
                raise ValueError(
                    f"Phase {phase.id} requires input '{inp}' but it's not available"
                )

    if bootstrap:
        platform = bootstrap.get("platform")
        if platform is not None:
            resolved["platform"] = str(platform)

        pr_author = bootstrap.get("pr_author")
        if pr_author is not None:
            resolved["pr_author"] = str(pr_author)

        if "changed_files" in bootstrap:
            changed_files = bootstrap.get("changed_files", [])
            workspace_dir.mkdir(parents=True, exist_ok=True)
            changed_files_file = workspace_dir / "changed-files.json"
            changed_files_file.write_text(
                json.dumps(changed_files, ensure_ascii=False), encoding="utf-8"
            )
            resolved["changed_files_path"] = str(changed_files_file)

        source_branch = bootstrap.get("source_branch")
        if source_branch is not None:
            resolved["source_branch"] = str(source_branch)

        if phase.id == "2":
            resolved["existing_pr"] = str(bootstrap.get("existing_pr", ""))

    # Fall back to state values when bootstrap is absent/incomplete
    if "platform" not in resolved and state.get("platform"):
        resolved["platform"] = str(state["platform"])

    return resolved


def should_skip_phase(phase: PhaseSpec, state: dict) -> Optional[str]:
    """Check if a phase should be conditionally skipped.

    Returns a reason string if skipping, None if the phase should run.
    """
    if phase.skip_when == "no_actionable_findings":
        findings = _state_value(state, "code_review_findings") or {}
        # Findings may be a JSON string if state merge didn't parse it
        if isinstance(findings, str):
            try:
                findings = json.loads(findings)
            except (json.JSONDecodeError, TypeError):
                # LLM sometimes emits Python-style \' escapes — strip them
                try:
                    findings = json.loads(findings.replace("\\'", "'"))
                except (json.JSONDecodeError, TypeError):
                    findings = {}
        if not isinstance(findings, dict):
            findings = {}
        # Normalized Phase 1c output may nest severity buckets under a "findings" key
        if "findings" in findings and isinstance(findings["findings"], dict):
            findings = findings["findings"]
        # Findings may be bucketed by various severity names (high/medium/low, Critical/Important/Suggestion)
        mechanical = []
        for severity in ("critical", "Critical", "important", "Important", "high", "High", "medium", "Medium", "low", "Low", "suggestion", "Suggestion", "suggestions"):
            for f in findings.get(severity, []):
                if str(f.get("mechanical", "")).lower() == "true":
                    mechanical.append(f)
        if not mechanical:
            return "no mechanical findings from code review"
    return None


def _infer_prerequisite_phase(prerequisite: str, state: dict) -> Optional[str]:
    """Best-effort mapping from prerequisite state key to producing phase id."""
    explicit = {
        "code_review_findings": "1c",
        "pr_url": "2",
    }
    if prerequisite in explicit:
        return explicit[prerequisite]

    for candidate in PHASE_SEQUENCE:
        if prerequisite in candidate.required_outputs:
            return candidate.id
        candidate_output = read_phase_output(state, candidate.id) or {}
        if isinstance(candidate_output, dict) and prerequisite in candidate_output:
            return candidate.id
    return None


def validate_prerequisites(
    phase: PhaseSpec,
    state: dict,
    current_fingerprint: Optional[dict] = None,
) -> Optional[str]:
    """Check that required state keys exist before running a phase standalone.

    Returns an error message if prerequisites are missing, None if satisfied.
    """
    if not phase.prerequisites:
        return None
    missing = [k for k in phase.prerequisites if _state_value(state, k) is None]
    if missing:
        return (
            f"Phase {phase.id} requires state keys: {', '.join(missing)}. "
            f"Run earlier phases first or provide --state-file with the required data."
        )

    for prerequisite in phase.prerequisites:
        prerequisite_phase = _infer_prerequisite_phase(prerequisite, state)
        if prerequisite_phase and not is_phase_fresh(state, prerequisite_phase, current_fingerprint):
            print(
                f"WARNING: Phase {prerequisite_phase} output may be stale "
                f"(PR head changed since it ran)",
                flush=True,
            )
    return None


def _iter_existing_input_files(inputs: dict[str, str]) -> list[tuple[str, Path]]:
    """Return file-like phase inputs that already exist on disk."""
    file_inputs: list[tuple[str, Path]] = []
    for name, value in inputs.items():
        if not isinstance(value, str):
            continue
        looks_like_file = name in {"state_file", "findings_json_path"} or name.endswith("_file") or name.endswith("_path")
        if not looks_like_file:
            continue
        path = Path(value)
        if path.is_file():
            file_inputs.append((name, path))
    return file_inputs


def _preflight_validate_input_files(phase: PhaseSpec, inputs: dict[str, str]) -> list[str]:
    """Validate encodings for any existing file inputs before a phase runs."""
    errors: list[str] = []
    for name, path in _iter_existing_input_files(inputs):
        info = validate_encoding(path)
        if not info.get("readable") or info.get("encoding") == "unknown":
            errors.append(f"Phase {phase.id} input '{name}' is not readable with a known encoding: {path}")
            continue
        warnings = info.get("warnings") or []
        if warnings:
            print(
                f"WARNING: Phase {phase.id} input '{name}' may have encoding issues "
                f"({info.get('encoding')}, warnings={warnings}): {path}",
                flush=True,
            )
    return errors


# ---------------------------------------------------------------------------
# Conductor execution
# ---------------------------------------------------------------------------

def run_conductor(
    workflow_path: Path,
    inputs: dict[str, str],
    conductor_flags: list[str],
    run_id: str,
    phase_id: str,
    attempt: int,
    work_dir: Path,
    timeout_s: int = 1800,
) -> tuple[int, str]:
    """Run a Conductor workflow and return (exit_code, event_log_glob).

    Uses --log-file auto so Conductor writes structured JSONL events
    (workflow_completed with output dict). Explicit paths get plain text instead.
    The glob matches Conductor's auto-generated filename pattern:
      conductor-{workflow_stem}-{YYYYMMDD}-{HHMMSS}-{hex}.events.jsonl
    merge-state.py resolves the newest matching file by mtime.
    """
    log_dir = Path(tempfile.gettempdir()) / "conductor"
    log_dir.mkdir(exist_ok=True)

    cmd = ["conductor", "run", str(workflow_path)]
    for k, v in inputs.items():
        cmd.extend(["--input", f"{k}={v}"])
    # MUST use "auto" — explicit paths get plain text, not JSONL events
    cmd.extend(["--log-file", "auto"])
    cmd.append("--no-interactive")
    # Auto-discover the user's repo conventions (AGENTS.md,
    # .github/copilot-instructions.md, CLAUDE.md) and prepend them to every
    # phase agent's prompt. Requires conductor >= 0.1.11. Older conductor
    # rejects this flag; users see a clear error and can run `conductor update`.
    # CWD is the user's target repo (run-phases.py is invoked from there),
    # which is exactly what conductor's discovery walks from.
    cmd.append("--workspace-instructions")
    cmd.extend(conductor_flags)

    print(f"  ▸ conductor run {workflow_path.name} (attempt {attempt + 1}, timeout {timeout_s}s)", flush=True)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=False,
            shell=False,
            timeout=timeout_s,
        )
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        print(f"  ✖ Phase {phase_id} timed out after {timeout_s}s", flush=True)
        returncode = 124  # conventional timeout exit code

    # Glob matches Conductor's auto-generated JSONL event logs for this workflow
    event_log_glob = str(
        log_dir / f"conductor-{workflow_path.stem}-*.events.jsonl"
    )

    return returncode, event_log_glob


def run_merge_state(
    event_log_glob: str,
    state_file: Path,
    phase_id: str,
    clear_keys: list[str],
    merge_script: Path,
) -> int:
    """Run merge-state.py to merge phase output into state."""
    cmd = [
        sys.executable,
        str(merge_script),
        "--event-log", event_log_glob,
        "--state-file", str(state_file),
        "--phase", phase_id,
    ]
    if clear_keys:
        cmd.extend(["--clear-keys"] + clear_keys)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(f"  ▸ merge: {result.stdout.strip()}", flush=True)
    if result.returncode != 0 and result.stderr:
        print(f"  ▸ merge error: {result.stderr.strip()}", file=sys.stderr, flush=True)
    return result.returncode


# Known placeholder patterns that indicate a phase didn't actually produce output
_PLACEHOLDER_PATTERNS = (
    "<!-- pr-orchestrator -->",
)

# ⏳ is used as a sentinel prefix to mark in-progress or not-yet-produced values.
# A state value whose string form starts with ⏳ is treated as a placeholder (see _is_placeholder).
# This convention lets phases write a progress marker before producing real output.
_PENDING_SENTINEL = "⏳"


def _is_placeholder(value: Any) -> bool:
    """Check if a value is empty or a known placeholder."""
    if value is None:
        return True
    if value == "" or value == {} or value == []:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        # HTML comment-only (e.g. "<!-- pr-orchestrator -->")
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            return True
        # Placeholder markers — use the ⏳ sentinel constant (see _PENDING_SENTINEL above)
        if stripped.startswith(_PENDING_SENTINEL):
            return True
        for pattern in _PLACEHOLDER_PATTERNS:
            if stripped == pattern:
                return True
    return False


def validate_required_outputs(
    phase: PhaseSpec, state: dict
) -> Optional[str]:
    """Check that required outputs exist in state after a phase completes.

    Returns an error message if validation fails, None on success.
    Rejects None, empty values, and known placeholder/sentinel content.
    """
    for key in phase.required_outputs:
        val = _state_value(state, key)
        if _is_placeholder(val):
            return f"Phase {phase.id} did not produce required output: {key} (got placeholder or empty value)"
    return None


# ---------------------------------------------------------------------------
# Phase execution
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    """Result of executing a single phase."""
    phase_id: str
    status: str  # "completed", "failed", "skipped"
    duration_s: float = 0.0
    attempts: int = 0
    error: Optional[str] = None
    pr_url: Optional[str] = None  # populated after Phase 2


def execute_phase(
    phase: PhaseSpec,
    state: dict,
    state_file: Path,
    target_branch: str,
    scripts_dir: Path,
    workflow_dir: Path,
    merge_script: Path,
    run_id: str,
    work_dir: Path,
    workspace_dir: Optional[Path] = None,
    existing_pr: Optional[str] = None,
    current_fingerprint: Optional[dict] = None,
    bootstrap: Optional[dict] = None,
) -> PhaseResult:
    """Execute a single phase with retry logic."""
    start = time.monotonic()

    effective_workspace_dir = workspace_dir or work_dir

    # Resolve inputs
    try:
        inputs = resolve_inputs(
            phase,
            state,
            state_file,
            target_branch,
            scripts_dir,
            effective_workspace_dir,
            existing_pr,
            bootstrap=bootstrap,
        )
    except ValueError as e:
        return PhaseResult(
            phase_id=phase.id,
            status="failed",
            duration_s=time.monotonic() - start,
            error=str(e),
        )

    preflight_errors = _preflight_validate_input_files(phase, inputs)
    if preflight_errors:
        return PhaseResult(
            phase_id=phase.id,
            status="failed",
            duration_s=time.monotonic() - start,
            error="; ".join(preflight_errors),
        )

    workflow_path = workflow_dir / phase.workflow

    if not workflow_path.exists():
        return PhaseResult(
            phase_id=phase.id,
            status="failed",
            duration_s=time.monotonic() - start,
            error=f"Workflow file not found: {workflow_path}",
        )

    last_error: Optional[str] = None

    for attempt in range(phase.max_retries + 1):
        exit_code, event_log_glob = run_conductor(
            workflow_path=workflow_path,
            inputs=inputs,
            conductor_flags=phase.conductor_flags,
            run_id=run_id,
            phase_id=phase.id,
            attempt=attempt,
            work_dir=work_dir,
            timeout_s=phase.timeout_s,
        )

        # Always merge state, even on failure (partial output may exist)
        merge_rc = 0
        if phase.merge_phase:
            merge_rc = run_merge_state(
                event_log_glob=event_log_glob,
                state_file=state_file,
                phase_id=phase.merge_phase,
                clear_keys=phase.merge_clear_keys if attempt == 0 else [],
                merge_script=merge_script,
            )
            if merge_rc != 0:
                print(
                    f"  ⚠ merge-state failed (rc={merge_rc}) for phase {phase.id}",
                    flush=True,
                )
            # Reload state after merge — merge only known phase/tracking keys from disk
            # to avoid discarding unsaved in-memory updates
            _fresh = load_state(state_file)
            if isinstance(_fresh, dict):
                for _key in (
                    "_phases", "_completed_phases", "_last_merged_phase",
                    "_last_merged_at", "_merge_log", "_phase_validation_errors", "_phase_meta",
                ):
                    if _key in _fresh:
                        state[_key] = _fresh[_key]

        if exit_code == 0 and merge_rc != 0:
            # Conductor succeeded but merge failed — treat as phase failure
            last_error = f"merge-state failed (rc={merge_rc}) for phase {phase.id}"
            if attempt < phase.max_retries:
                print(f"  ↻ Retrying due to merge failure...", flush=True)
                continue

        if exit_code == 0:
            phase_output = read_phase_output(state, phase.id) or {}
            contracts_valid, contract_warnings = validate_phase_output(phase.id, phase_output)
            if not contracts_valid:
                for warning in contract_warnings:
                    print(
                        f"  ⚠ Phase {phase.id} contract warning: {warning}",
                        flush=True,
                    )

            # Check for suspiciously empty output (Conductor succeeded but agent produced nothing)
            if not phase_output and phase.required_outputs:
                last_error = f"Phase {phase.id} produced no output despite Conductor success (possible agent crash)"
                print(f"  ⚠ {last_error}", flush=True)
                if attempt < phase.max_retries:
                    print(f"  ↻ Retrying...", flush=True)
                    continue

            # Validate required outputs
            validation_error = validate_required_outputs(phase, state)
            if validation_error:
                last_error = validation_error
                print(
                    f"  ⚠ Output validation failed: {validation_error}",
                    flush=True,
                )
                if attempt < phase.max_retries:
                    print(f"  ↻ Retrying...", flush=True)
                    continue
            else:
                # Success
                duration = time.monotonic() - start
                phase_meta = state.get("_phase_meta", {})
                if not isinstance(phase_meta, dict):
                    phase_meta = {}
                meta_entry = build_phase_meta(
                    phase.id,
                    phase_output,
                    duration,
                    fingerprint=current_fingerprint,
                )
                if meta_entry:
                    phase_meta[phase.id] = meta_entry
                    state["_phase_meta"] = phase_meta
                    save_state(state_file, state)
                pr_url = _state_value(state, "pr_url") if phase.id == "2" else None
                return PhaseResult(
                    phase_id=phase.id,
                    status="completed",
                    duration_s=duration,
                    attempts=attempt + 1,
                    pr_url=pr_url,
                )
        else:
            last_error = f"Conductor exited with code {exit_code}"
            print(f"  ⚠ {last_error}", flush=True)
            if attempt < phase.max_retries:
                print(f"  ↻ Retrying...", flush=True)

    # All retries exhausted
    return PhaseResult(
        phase_id=phase.id,
        status="failed",
        duration_s=time.monotonic() - start,
        attempts=phase.max_retries + 1,
        error=last_error,
    )


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

STATUS_ICONS = {
    "completed": "✅",
    "failed": "🔴",
    "skipped": "⏭️",
}


def run_single_phase(
    phase_id: str,
    target_branch: str,
    work_dir: Path,
    output_file: Optional[Path] = None,
    existing_pr: Optional[str] = None,
    state_file_override: Optional[Path] = None,
) -> dict:
    """Run a single phase standalone.

    Loads existing state (preserving prior phase outputs), validates prerequisites,
    clears stale completion markers for this phase, and executes it.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    phase = PHASE_BY_ID.get(phase_id)
    if not phase:
        return {"status": "error", "error": f"Unknown phase: {phase_id}"}

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # Resolve paths
    workflow_dir = _resolve_workflow_dir()
    scripts_dir = _resolve_scripts_dir()
    merge_script = scripts_dir / "merge-state.py"

    if not workflow_dir.exists():
        print(f"🔴 Workflow directory not found: {workflow_dir}", flush=True)
        return {"status": "error", "error": f"Workflow directory not found: {workflow_dir}"}

    if not merge_script.exists():
        print(f"🔴 merge-state.py not found: {merge_script}", flush=True)
        return {"status": "error", "error": f"merge-state.py not found: {merge_script}"}

    # State file — load existing state (don't wipe it)
    branch_safe = target_branch.replace("/", "_").replace("\\", "_").replace(":", "_")
    try:
        git_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=str(work_dir),
        ).stdout.strip().replace("/", "_").replace("\\", "_").replace(":", "_")
    except (OSError, subprocess.SubprocessError):
        git_branch = branch_safe

    state_file = state_file_override or (
        Path(tempfile.gettempdir()) / f"pr-orchestrator-state-{git_branch}.json"
    )

    state = load_state(state_file)

    # Ensure state file exists on disk (load_state returns {} if missing)
    if not state_file.exists():
        save_state(state_file, state)

    # Inject existing PR into state if provided
    if existing_pr and not _state_value(state, "pr_url"):
        state["pr_url"] = existing_pr
        save_state(state_file, state)

    workspace_dir = create_workspace_dir(
        run_id,
        Path(state["_workspace_dir"]) if state.get("_workspace_dir") else None,
    )
    state["_workspace_dir"] = str(workspace_dir)
    save_state(state_file, state)
    os.environ["PR_ORCHESTRATOR_WORKSPACE_DIR"] = str(workspace_dir)

    # Resolve platform early from git remote — no external CLI dependency
    if not state.get("platform"):
        platform = _detect_platform_from_remote(work_dir)
        if platform:
            state["platform"] = platform
            save_state(state_file, state)

    bootstrap = None
    try:
        bootstrap = _run_bootstrap(target_branch, existing_pr or "", work_dir=work_dir)
    except Exception as exc:
        print(
            f"WARNING: Deterministic bootstrap failed ({exc}); falling back to workflow bootstrap",
            flush=True,
        )

    # Update platform from bootstrap if it succeeded (may confirm or correct)
    if bootstrap and bootstrap.get("platform") in ("ado", "github"):
        state["platform"] = bootstrap["platform"]
        save_state(state_file, state)

    current_fingerprint = compute_fingerprint(existing_pr or _state_value(state, "pr_url"))

    # Validate prerequisites
    prereq_error = validate_prerequisites(phase, state, current_fingerprint)
    if prereq_error:
        print(f"🔴 {prereq_error}", flush=True)
        return {"status": "error", "error": prereq_error}

    # Clear stale completion marker for this phase so we actually re-run it
    completed = state.get("_completed_phases", [])
    if phase_id in completed:
        completed.remove(phase_id)
        state["_completed_phases"] = completed
        save_state(state_file, state)

    os.environ["PYTHONIOENCODING"] = "utf-8"

    print(f"═══ PR Orchestrator — single phase: {phase_id} ═══", flush=True)
    print(f"  Branch: {git_branch}", flush=True)
    print(f"  Target: {target_branch}", flush=True)
    print(f"  State:  {state_file}", flush=True)
    print(f"  Workspace: {workspace_dir}", flush=True)
    print("", flush=True)

    phase_start = time.monotonic()

    # Check conditional skip
    skip_reason = should_skip_phase(phase, state)
    if skip_reason:
        icon = STATUS_ICONS["skipped"]
        print(f"{icon} Phase {phase_id}: skipped ({skip_reason})", flush=True)
        result_dict = {
            "status": "completed",
            "execution_scope": "single-phase",
            "requested_phase": phase_id,
            "phases": {phase_id: {"status": "skipped", "reason": skip_reason}},
            "state_file": str(state_file),
            "workspace_dir": str(workspace_dir),
            "total_duration_s": 0,
        }
        state.pop("_workspace_dir", None)
        save_state(state_file, state)
        cleanup_workspace_dir(workspace_dir)
        if output_file:
            output_file.write_text(
                json.dumps(result_dict, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return result_dict

    # Execute
    print(f"⏳ Phase {phase_id}: starting...", flush=True)
    result = execute_phase(
        phase=phase,
        state=state,
        state_file=state_file,
        target_branch=target_branch,
        scripts_dir=scripts_dir,
        workflow_dir=workflow_dir,
        merge_script=merge_script,
        run_id=run_id,
        work_dir=work_dir,
        workspace_dir=workspace_dir,
        existing_pr=existing_pr,
        current_fingerprint=current_fingerprint,
        bootstrap=bootstrap,
    )

    # Reload state after merge
    state = load_state(state_file)

    duration = time.monotonic() - phase_start
    icon = STATUS_ICONS.get(result.status, "❓")
    extra = ""
    if result.pr_url:
        extra = f" → PR: {result.pr_url}"
    if result.error:
        extra += f" — {result.error}"

    print(f"{icon} Phase {phase_id}: {result.status} ({duration:.0f}s){extra}", flush=True)

    if result.status == "completed":
        mark_phase_completed(state, phase_id)
        save_state(state_file, state)

        # Deterministic push: ensure any local commits reach the remote
        _push_local_commits(phase_id, work_dir)

        # PR body management — same as run_pipeline():
        # Phase 2: full template creation (only time fix-pr-body.py runs)
        # Phase 4/5: surgical updates only (validation refresh + digest link)
        if phase_id == "2":
            _create_pr_body(state, state_file, scripts_dir, work_dir)
            state = load_state(state_file)
            _validate_pr_exists(state, work_dir)
        elif phase_id in ("4", "5"):
            _update_pr_body(state, state_file, scripts_dir, work_dir, phase_id)
            state = load_state(state_file)

    phase_result = {
        "status": result.status,
        "duration_s": round(duration, 1),
        "attempts": result.attempts,
    }
    if result.error:
        phase_result["error"] = result.error

    result_dict = {
        "status": result.status,
        "execution_scope": "single-phase",
        "requested_phase": phase_id,
        "pr_url": result.pr_url or existing_pr or _state_value(state, "pr_url"),
        "target_branch": target_branch,
        "state_file": str(state_file),
        "workspace_dir": str(workspace_dir),
        "phases": {phase_id: phase_result},
        "total_duration_s": round(duration, 1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    if result.status == "completed":
        state.pop("_workspace_dir", None)
        save_state(state_file, state)
        cleanup_workspace_dir(workspace_dir)
    else:
        print(f"⚠ Preserving workspace for debugging: {workspace_dir}", flush=True)

    if output_file:
        output_file.write_text(
            json.dumps(result_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return result_dict


# Stale temp files to clean up at the start of each fresh pipeline run.
# These files are produced by Conductor agents during earlier runs and can
# cause data-bleeding between runs when Phase 5 reads a digest-input.json
# left over from the previous run.
_STALE_TEMP_FILES = [
    "digest-input.json",
    "final-digest-input.json",
    "upstream-data.json",
    "phase5-data.json",
    "digest-output.md",
    "final-digest.md",
    "triage-output.json",
    "triage-output-utf8.json",
    "scrape-fb-commits.json",
    "scrape-fb-threads.json",
    "scrape-waf-commits.json",
    "pr-body.txt",
    "run-phases-result.json",
    # Phase 1c/1d findings handoff
    "pr-orchestrator-1c-findings.json",
    # Phase 4 intermediates
    "pr-threads.json",
    "upsert-body.json",
    "pr-data.json",
    "pr-desc-validate.md",
    "pr-desc-body.json",
    "pr-desc-new.md",
    # Phase 4/5 code review + triage
    "code-review-findings.json",
    "triage-threads.json",
]


def _cleanup_stale_temp_files() -> None:
    """Remove stale temp artifacts from previous pipeline runs."""
    tmp = Path(tempfile.gettempdir())
    removed = []
    for name in _STALE_TEMP_FILES:
        p = tmp / name
        if p.exists():
            try:
                p.unlink()
                removed.append(name)
            except OSError:
                pass

    # Clean conductor event logs to prevent stale data bleeding between runs
    conductor_dir = tmp / "conductor"
    if conductor_dir.is_dir():
        for f in conductor_dir.glob("*.events.jsonl"):
            try:
                f.unlink()
                removed.append(f"conductor/{f.name}")
            except OSError:
                pass

    # Clean dynamic-name temp files from post-findings.py
    for pattern in ("finding-*.json", "gh-finding-*.json"):
        for f in tmp.glob(pattern):
            try:
                f.unlink()
                removed.append(f.name)
            except OSError:
                pass

    if removed:
        print(f"🧹 Cleaned {len(removed)} stale temp file(s): {', '.join(removed)}", flush=True)


# ---------------------------------------------------------------------------
# Deterministic git push — ensures local commits reach the remote
# ---------------------------------------------------------------------------

# Phases whose conductor workflows create local commits that must be pushed.
PHASES_THAT_COMMIT = {"1b", "1d", "3", "5"}


def _push_local_commits(phase_id: str, work_dir: Path) -> None:
    """Push any unpushed local commits to the remote after a phase completes.

    Called deterministically after each phase in PHASES_THAT_COMMIT.  This
    removes the dependency on LLM agents remembering to ``git push`` — the
    phase driver guarantees it.
    """
    if phase_id not in PHASES_THAT_COMMIT:
        return

    try:
        # Check if there are unpushed commits
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(work_dir), timeout=10,
        )
        branch = branch_result.stdout.strip()
        if not branch or branch_result.returncode != 0:
            return

        # Compare local HEAD vs remote tracking branch
        diff_result = subprocess.run(
            ["git", "rev-list", f"origin/{branch}..HEAD", "--count"],
            capture_output=True, text=True, cwd=str(work_dir), timeout=10,
        )
        unpushed = int(diff_result.stdout.strip()) if diff_result.returncode == 0 else 0

        if unpushed == 0:
            return

        print(f"  ▸ push-commits[{phase_id}]: {unpushed} unpushed commit(s), pushing...", flush=True)

        push_result = subprocess.run(
            ["git", "push", "origin", branch],
            capture_output=True, text=True, cwd=str(work_dir), timeout=60,
        )
        if push_result.returncode != 0:
            # Retry once with rebase — check rebase result before pushing
            print(f"  ▸ push-commits[{phase_id}]: push failed, trying rebase...", flush=True)
            rebase_result = subprocess.run(
                ["git", "pull", "--rebase", "origin", branch],
                capture_output=True, text=True, cwd=str(work_dir), timeout=60,
            )
            if rebase_result.returncode != 0:
                print(
                    f"  ⚠ push-commits[{phase_id}]: rebase failed — {rebase_result.stderr.strip()[:200]}",
                    flush=True,
                )
                return
            push_result = subprocess.run(
                ["git", "push", "origin", branch],
                capture_output=True, text=True, cwd=str(work_dir), timeout=60,
            )
            if push_result.returncode != 0:
                print(f"  ⚠ push-commits[{phase_id}]: push failed after rebase — {push_result.stderr.strip()}", flush=True)
                return

        print(f"  ✅ push-commits[{phase_id}]: {unpushed} commit(s) pushed", flush=True)
    except Exception as exc:
        print(f"  ⚠ push-commits[{phase_id}]: error — {exc}", flush=True)


# ---------------------------------------------------------------------------
# Deterministic PR validation — confirms PR exists after Phase 2
# ---------------------------------------------------------------------------


def _validate_pr_exists(state: dict, work_dir: Path) -> bool:
    """Validate that the PR URL stored in state actually resolves to a real PR.

    Called deterministically after Phase 2 to catch garbage URLs before they
    propagate through the rest of the pipeline.  Returns True if valid.
    """
    pr_url = _state_value(state, "pr_url")
    if not pr_url:
        print("  ⚠ validate-pr: no PR URL in state", flush=True)
        return False

    from pr_url_utils import parse_pr_url
    parsed = parse_pr_url(pr_url)
    if not parsed:
        print(f"  ⚠ validate-pr: cannot parse URL — {pr_url[:100]}", flush=True)
        return False

    platform = parsed.get("platform")
    try:
        if platform == "ado":
            api_base = parsed.get("api_base", f"https://dev.azure.com/{parsed['org']}")
            api_url = (
                f"{api_base}/{parsed['project']}/_apis/git/repositories/{parsed['repo']}"
                f"/pullRequests/{parsed['pr_id']}?api-version=7.1"
            )
            result = subprocess.run(
                [shutil.which("az") or "az", "rest", "--method", "get", "--url", api_url,
                 "--resource", "499b84ac-1321-427f-aa17-267ca6975798"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                title = data.get("title", "(untitled)")
                pr_status = data.get("status", "unknown")
                print(f"  ✅ validate-pr: PR #{parsed['pr_id']} exists — \"{title}\" ({pr_status})", flush=True)
                return True
            else:
                print(f"  ⚠ validate-pr: PR API returned error — {result.stderr.strip()[:200]}", flush=True)
                return False

        elif platform == "github":
            result = subprocess.run(
                ["gh", "pr", "view", parsed["pr_id"],
                 "--repo", f"{parsed['owner']}/{parsed['repo']}",
                 "--json", "title,state"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                print(f"  ✅ validate-pr: PR #{parsed['pr_id']} exists — \"{data.get('title')}\" ({data.get('state')})", flush=True)
                return True
            else:
                print(f"  ⚠ validate-pr: gh pr view failed — {result.stderr.strip()[:200]}", flush=True)
                return False

    except Exception as exc:
        print(f"  ⚠ validate-pr: error — {exc}", flush=True)

    return False


# ---------------------------------------------------------------------------
# Deterministic thread resolution — resolves threads after Phase 5
# ---------------------------------------------------------------------------


def _resolve_pr_threads(
    state: dict, scripts_dir: Path, workspace_dir: Path, pr_url: str,
) -> None:
    """Resolve addressed feedback threads and the digest thread after Phase 5.

    Calls resolve-pr-threads.py deterministically instead of relying on LLM
    agents to manually run ``az rest`` commands.
    """
    resolve_script = scripts_dir / "resolve-pr-threads.py"
    if not resolve_script.exists():
        print("  ⚠ resolve-threads: script not found", flush=True)
        return

    if not pr_url:
        print("  ⚠ resolve-threads: no PR URL available", flush=True)
        return

    tmp = Path(state.get("_workspace_dir") or workspace_dir)

    # 1. Resolve addressed feedback threads from scrape file
    scrape_file = tmp / "scrape-fb-threads.json"
    if scrape_file.exists():
        print("  ▸ resolve-threads: resolving addressed feedback threads...", flush=True)
        result = subprocess.run(
            [sys.executable, str(resolve_script),
             "--pr-url", pr_url,
             "--from-file", str(scrape_file)],
            capture_output=True, text=True, timeout=120,
        )
        # Print resolution results (script writes to stdout)
        for line in (result.stdout or "").strip().splitlines():
            if line.startswith("  "):
                print(line, flush=True)
        if result.returncode != 0:
            for line in (result.stderr or "").strip().splitlines()[-3:]:
                print(f"  ⚠ resolve-threads: {line}", flush=True)
    else:
        print("  ▸ resolve-threads: no scrape-fb-threads.json found, skipping feedback thread resolution", flush=True)

    # 2. Resolve the digest comment thread
    digest_meta = tmp / "digest-upsert-result.json"
    if digest_meta.exists():
        try:
            meta = json.loads(digest_meta.read_text(encoding="utf-8"))
            thread_id = meta.get("thread_id", "")
            if thread_id:
                print(f"  ▸ resolve-threads: resolving digest thread {thread_id}...", flush=True)
                result = subprocess.run(
                    [sys.executable, str(resolve_script),
                     "--pr-url", pr_url,
                     "--digest-thread-id", str(thread_id)],
                    capture_output=True, text=True, timeout=30,
                )
                for line in (result.stdout or "").strip().splitlines():
                    if line.startswith("  "):
                        print(line, flush=True)
        except Exception as exc:
            print(f"  ⚠ resolve-threads: error reading digest meta — {exc}", flush=True)


# ---------------------------------------------------------------------------
# PR Body Management — Split Design
# Phase 2: _create_pr_body() — full template construction (only time)
# Phase 4/5: _update_pr_body() — surgical section updates only
# ---------------------------------------------------------------------------


def _detect_platform_and_pr(state: dict, scripts_dir: Path, work_dir: Path):
    """Shared helper: detect platform, resolve PR ID and CLI tool.

    Returns (platform, platform_info, pr_id, cli_cmd) or None on failure.
    """
    pr_url = _state_value(state, "pr_url") or ""
    if not pr_url:
        print("  ▸ pr-body: no pr_url, skipping", flush=True)
        return None

    detect_script = scripts_dir / "detect-platform.py"
    try:
        det = subprocess.run(
            [sys.executable, str(detect_script)],
            capture_output=True, text=True, cwd=str(work_dir), timeout=10,
        )
        platform_info = json.loads(det.stdout.strip()) if det.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        platform_info = {}

    platform = platform_info.get("platform", "unknown")

    if platform == "ado":
        pr_id_match = re.search(r"/pullrequest/(\d+)", pr_url)
        if not pr_id_match:
            print(f"  ▸ pr-body: cannot extract PR ID from {pr_url}", flush=True)
            return None
        pr_id = pr_id_match.group(1)
        cli_cmd = shutil.which("az")
        if not cli_cmd:
            print("  ▸ pr-body: az CLI not found on PATH", flush=True)
            return None
    elif platform == "github":
        pr_id_match = re.search(r"/pull/(\d+)", pr_url)
        if not pr_id_match:
            print(f"  ▸ pr-body: cannot extract PR ID from {pr_url}", flush=True)
            return None
        pr_id = pr_id_match.group(1)
        cli_cmd = shutil.which("gh")
        if not cli_cmd:
            print("  ▸ pr-body: gh CLI not found on PATH", flush=True)
            return None
    else:
        print(f"  ▸ pr-body: unknown platform '{platform}', skipping", flush=True)
        return None

    return platform, platform_info, pr_id, cli_cmd


def _fetch_pr_body(state: dict, platform: str, platform_info: dict, pr_id: str, cli_cmd: str):
    """Fetch current PR body and title from API or workspace cache.

    Returns (body, title) or ("", "").
    """
    pr_url = _state_value(state, "pr_url") or ""
    tmp = Path(state.get("_workspace_dir") or tempfile.gettempdir())
    tmp.mkdir(parents=True, exist_ok=True)

    # Prefer the original body from Phase 2's temp file
    phase2_body_file = tmp / "pr-body.txt"
    pr_title = _state_value(state, "pr_title") or ""
    if phase2_body_file.exists():
        cached = phase2_body_file.read_text(encoding="utf-8")
        if cached.strip() and cached.strip() != "<!-- pr-orchestrator -->":
            print(f"  ▸ pr-body: using workspace-local body ({len(cached)} chars)", flush=True)
            return cached, pr_title

    # Fallback: fetch from API
    if platform == "ado":
        org = platform_info.get("org", "")
        result = run_with_retry(
            [cli_cmd, "repos", "pr", "show", "--id", pr_id,
             "--org", f"https://dev.azure.com/{org}",
             "--output", "json", "--detect", "false"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            print(f"  ▸ pr-body: az repos pr show failed: {result.stderr[:200]}", flush=True)
            return "", ""
        pr_data = json.loads(result.stdout)
        body = (pr_data.get("description", "") or "").replace("\r\n", "\n").replace("\r", "")
        return body, pr_title or pr_data.get("title", "") or ""
    else:
        owner = platform_info.get("owner", "")
        repo = platform_info.get("repo", "")
        result = run_with_retry(
            [cli_cmd, "pr", "view", pr_id, "--repo", f"{owner}/{repo}", "--json", "title,body"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"  ▸ pr-body: gh pr view failed: {result.stderr[:200]}", flush=True)
            return "", ""
        pr_data = json.loads(result.stdout)
        body = (pr_data.get("body", "") or "").replace("\r\n", "\n").replace("\r", "")
        return body, pr_title or pr_data.get("title", "") or ""


def _push_pr_body(body: str, platform: str, platform_info: dict, pr_id: str,
                  cli_cmd: str, state: dict) -> bool:
    """Push body to PR. Returns True on success."""
    tmp = Path(state.get("_workspace_dir") or tempfile.gettempdir())
    tmp.mkdir(parents=True, exist_ok=True)
    body_update_file = tmp / "pr-body-update.txt"
    body_update_file.write_text(body, encoding="utf-8")

    try:
        if platform == "ado":
            org = platform_info.get("org", "")
            update_result = run_with_retry(
                [cli_cmd, "repos", "pr", "update", "--id", pr_id,
                 "--description", f"@{body_update_file}",
                 "--org", f"https://dev.azure.com/{org}",
                 "--detect", "false", "--output", "json"],
                capture_output=True, text=True, timeout=30,
            )
            if update_result.returncode != 0:
                update_result = run_with_retry(
                    [cli_cmd, "repos", "pr", "update", "--id", pr_id,
                     "--description", body,
                     "--org", f"https://dev.azure.com/{org}",
                     "--detect", "false", "--output", "json"],
                    capture_output=True, text=True, timeout=60,
                )
                if update_result.returncode != 0:
                    print(f"  ▸ pr-body: PR update failed: {update_result.stderr[:200]}", flush=True)
                    return False
        else:
            owner = platform_info.get("owner", "")
            repo = platform_info.get("repo", "")
            update_result = run_with_retry(
                [cli_cmd, "pr", "edit", pr_id, "--repo", f"{owner}/{repo}",
                 "--body-file", str(body_update_file)],
                capture_output=True, text=True, timeout=30,
            )
            if update_result.returncode != 0:
                print(f"  ▸ pr-body: PR update failed: {update_result.stderr[:200]}", flush=True)
                return False
        return True
    finally:
        try:
            body_update_file.unlink(missing_ok=True)
        except OSError:
            pass


def _build_live_validation_block(state: dict) -> str:
    """Build the compact validation summary from test and code review signals."""
    # Tests from Phase 1a
    phase_1a = read_phase_output(state, "1a") or {}
    run_count = phase_1a.get("tests_run", "—")
    t_passed = phase_1a.get("tests_passed", "—")
    t_failed = phase_1a.get("tests_failed", "0")
    tests_line = f"{run_count} run, {t_passed} passed, {t_failed} failed"

    # Code review from Phase 1c
    phase_1c = read_phase_output(state, "1c") or {}
    cr = phase_1c.get("code_review_findings", {})
    if isinstance(cr, str):
        try:
            cr = json.loads(cr)
        except (json.JSONDecodeError, TypeError):
            cr = {}
    if not isinstance(cr, dict):
        cr = {}
    total_findings = 0
    for key in ("important", "Important", "critical", "Critical",
                "suggestion", "Suggestion", "suggestions", "medium",
                "Medium", "low", "Low", "high", "High"):
        items = cr.get(key, [])
        if isinstance(items, list):
            total_findings += len(items)
        nested = cr.get("findings", {})
        if isinstance(nested, dict):
            items2 = nested.get(key, [])
            if isinstance(items2, list):
                total_findings += len(items2)
    code_review_line = "✅ No issues" if total_findings == 0 else f"⚠️ {total_findings} finding(s)"

    return (
        f"**Tests**: {tests_line}\n"
        f"**Code Review**: {code_review_line}"
    )


def _is_canonical_pr_body(body: str) -> bool:
    """Return True when the PR body already matches the orchestrator template."""
    if not body or "<!-- pr-orchestrator -->" not in body:
        return False
    return all(re.search(pattern, body, re.IGNORECASE | re.MULTILINE) for pattern in (
        r"^#\s+.+$",
        r"^##\s+Intent\b",
        r"^##\s+Changes\b",
    ))



def _create_pr_body(
    state: dict,
    state_file: Path,
    scripts_dir: Path,
    work_dir: Path,
) -> None:
    """Phase 2 ONLY: create the canonical PR body via fix-pr-body.py.

    This is the ONLY place that runs full template reconstruction.
    Intent and Changes sections are extracted here and frozen.
    Skips when the Phase 2 workflow already applied the template.
    """
    ctx = _detect_platform_and_pr(state, scripts_dir, work_dir)
    if not ctx:
        return
    platform, platform_info, pr_id, cli_cmd = ctx

    fix_script = scripts_dir / "fix-pr-body.py"
    if not fix_script.exists():
        print(f"  ▸ create-pr-body: fix-pr-body.py not found at {fix_script}", flush=True)
        return

    tmp = Path(state.get("_workspace_dir") or tempfile.gettempdir())
    tmp.mkdir(parents=True, exist_ok=True)
    body_file = tmp / "pr-body-raw.txt"
    fixed_file = tmp / "pr-body-fixed.txt"

    try:
        current_body, pr_title = _fetch_pr_body(state, platform, platform_info, pr_id, cli_cmd)
        if not current_body:
            print("  ▸ create-pr-body: PR body is empty, skipping", flush=True)
            return

        if _state_value(state, "pr_body_applied") or _is_canonical_pr_body(current_body):
            print("  ▸ create-pr-body: body already templated (workflow step ran), skipping", flush=True)
            return

        print(f"  ▸ create-pr-body: fetched body ({len(current_body)} chars)", flush=True)

        # Full template construction via fix-pr-body.py
        body_file.write_text(current_body, encoding="utf-8")
        fix_result = subprocess.run(
            [sys.executable, str(fix_script),
             "--state-file", str(state_file),
             "--pr-body-file", str(body_file),
             "--pr-title", pr_title,
             "--output-file", str(fixed_file)],
            capture_output=True, text=True, timeout=30,
        )
        if fix_result.returncode != 0:
            print(f"  ▸ create-pr-body: fix-pr-body.py failed: {fix_result.stderr[:200]}", flush=True)
            return

        if not fixed_file.exists():
            print("  ▸ create-pr-body: fix script did not produce output", flush=True)
            return

        fixed_body = fixed_file.read_text(encoding="utf-8")

        # Replace DIGEST_LINK_PLACEHOLDER with actual digest URL if available
        digest_url = _state_value(state, "digest_comment_url") or ""
        if digest_url and "DIGEST_LINK_PLACEHOLDER" in fixed_body:
            fixed_body = fixed_body.replace("DIGEST_LINK_PLACEHOLDER", digest_url)
            print(f"  ▸ create-pr-body: replaced DIGEST_LINK_PLACEHOLDER", flush=True)

        if _push_pr_body(fixed_body, platform, platform_info, pr_id, cli_cmd, state):
            print("  ✅ create-pr-body: canonical PR body created", flush=True)

    except Exception as e:
        print(f"  ▸ create-pr-body: error: {e}", flush=True)
    finally:
        for f in (body_file, fixed_file):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass


def _update_pr_body(
    state: dict,
    state_file: Path,
    scripts_dir: Path,
    work_dir: Path,
    phase_id: str,
) -> None:
    """Phase 4/5 ONLY: surgical updates to existing canonical body.

    Allowed mutations:
    - Validation section (refreshed with live gate/test/review data)
    - Digest link (injected or updated)

    Forbidden mutations:
    - Intent section (frozen after Phase 2)
    - Changes section (frozen after Phase 2)
    - Full template rebuild (NEVER)
    """
    ctx = _detect_platform_and_pr(state, scripts_dir, work_dir)
    if not ctx:
        return
    platform, platform_info, pr_id, cli_cmd = ctx

    try:
        current_body, _ = _fetch_pr_body(state, platform, platform_info, pr_id, cli_cmd)
        if not current_body:
            print(f"  ▸ update-pr-body[{phase_id}]: PR body is empty, skipping", flush=True)
            return

        # Only do surgical updates if body is already canonical
        has_marker = "<!-- pr-orchestrator -->" in current_body
        has_intent = "## Intent" in current_body or "## intent" in current_body.lower()
        has_changes = "## Changes" in current_body or "## changes" in current_body.lower()

        if not (has_marker and has_intent and has_changes):
            print(f"  ▸ update-pr-body[{phase_id}]: body not canonical "
                  f"(marker={has_marker}, intent={has_intent}, changes={has_changes}), "
                  f"refusing surgical update", flush=True)
            return

        print(f"  ▸ update-pr-body[{phase_id}]: body is canonical ({len(current_body)} chars), "
              f"performing surgical update", flush=True)

        updated_body = current_body
        changed = False

        # 1. Refresh Validation section with live data
        validation_block = _build_live_validation_block(state)
        # Match from "## Validation" to next "##" heading or "### Related" or end
        val_pattern = re.compile(
            r"(## Validation\s*\r?\n+)"      # heading (capture to preserve)
            r"(.*?)"                          # content to replace
            r"(?=\r?\n##\s|\r?\n### Related|\Z)",  # lookahead: next heading or end
            re.DOTALL,
        )
        val_match = val_pattern.search(updated_body)
        if val_match:
            replacement = val_match.group(1) + validation_block + "\n\n"
            updated_body = updated_body[:val_match.start()] + replacement + updated_body[val_match.end():]
            changed = True
            print(f"  ▸ update-pr-body[{phase_id}]: refreshed Validation section", flush=True)
        else:
            print(f"  ▸ update-pr-body[{phase_id}]: Validation heading not found, skipping refresh", flush=True)

        # 2. Digest link injection/update
        digest_url = _state_value(state, "digest_comment_url") or ""
        if digest_url:
            if "DIGEST_LINK_PLACEHOLDER" in updated_body:
                updated_body = updated_body.replace("DIGEST_LINK_PLACEHOLDER", digest_url)
                changed = True
                print(f"  ▸ update-pr-body[{phase_id}]: replaced DIGEST_LINK_PLACEHOLDER", flush=True)
            elif digest_url not in updated_body:
                # Try to update existing [Review Digest](...) link
                link_pattern = re.compile(r"\[Review Digest\]\([^)]*\)", re.IGNORECASE)
                new_body, count = link_pattern.subn(f"[Review Digest]({digest_url})", updated_body, count=1)
                if count:
                    updated_body = new_body
                    changed = True
                    print(f"  ▸ update-pr-body[{phase_id}]: updated Review Digest link", flush=True)

        if not changed or updated_body == current_body:
            print(f"  ▸ update-pr-body[{phase_id}]: no changes needed", flush=True)
            return

        if _push_pr_body(updated_body, platform, platform_info, pr_id, cli_cmd, state):
            print(f"  ✅ update-pr-body[{phase_id}]: PR body updated surgically", flush=True)

    except Exception as e:
        print(f"  ▸ update-pr-body[{phase_id}]: error: {e}", flush=True)


def run_pipeline(
    mode: str,
    target_branch: str,
    work_dir: Path,
    output_file: Optional[Path] = None,
    existing_pr: Optional[str] = None,
    resume: bool = False,
    state_file_override: Optional[Path] = None,
    skip_next: bool = False,
) -> dict:
    """Run the full pipeline in the specified mode.

    Returns a result dict with phase statuses and overall outcome.
    Exit code 10 indicates an interactive gate pause (result["status"] == "paused").
    """
    # Force UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    skip_phases = MODE_SKIP.get(mode, [])

    # Resolve paths
    workflow_dir = _resolve_workflow_dir()
    scripts_dir = _resolve_scripts_dir()
    merge_script = scripts_dir / "merge-state.py"

    if not workflow_dir.exists():
        print(f"🔴 Workflow directory not found: {workflow_dir}", flush=True)
        print("   Run: octane install pr-orchestrator", flush=True)
        return {"status": "error", "error": f"Workflow directory not found: {workflow_dir}"}

    if not merge_script.exists():
        print(f"🔴 merge-state.py not found: {merge_script}", flush=True)
        return {"status": "error", "error": f"merge-state.py not found: {merge_script}"}

    # State file
    branch_safe = target_branch.replace("/", "_").replace("\\", "_").replace(":", "_")
    # Use git to get current branch name for state file naming
    try:
        git_branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=str(work_dir),
        ).stdout.strip().replace("/", "_").replace("\\", "_").replace(":", "_")
    except (OSError, subprocess.SubprocessError):
        git_branch = branch_safe

    state_file = state_file_override or (
        Path(tempfile.gettempdir()) / f"pr-orchestrator-state-{git_branch}.json"
    )

    if resume:
        # Resume: load existing state and validate
        state = load_state(state_file)
        if not state:
            print(f"🔴 Cannot resume: state file empty or missing: {state_file}", flush=True)
            return {"status": "error", "error": "No state to resume from"}
        if "_pending_gate" not in state:
            print("🔴 Cannot resume: no pending interactive gate in state", flush=True)
            return {"status": "error", "error": "No pending gate to resume from"}
        # Restore run context
        run_id = state.get("_run_id", run_id)
        # Clear the gate
        gate_phase = state.pop("_pending_gate", None)
        state.pop("_gate_message", None)
        save_state(state_file, state)
        print(f"⏩ Resuming after Phase {gate_phase} gate", flush=True)
        # Restore accumulated phase results
        results = state.get("_phase_results", {})

        # --skip-next: mark the next unfinished phase as skipped
        if skip_next:
            completed = get_completed_phases(state)
            for phase in PHASE_SEQUENCE:
                if phase.id not in completed and phase.id not in skip_phases:
                    print(f"⏭️ Phase {phase.id}: skipped (user requested skip)", flush=True)
                    results[phase.id] = {"status": "skipped", "reason": "user skip"}
                    mark_phase_completed(state, phase.id)
                    save_state(state_file, state)
                    break
    else:
        # Check for pending gate in existing state — auto-resume to prevent
        # accidental state wipe when the agent forgets --resume
        existing_state = load_state(state_file)
        if existing_state and "_pending_gate" in existing_state:
            gate_phase = existing_state.pop("_pending_gate", None)
            existing_state.pop("_gate_message", None)
            state = existing_state
            run_id = state.get("_run_id", run_id)
            save_state(state_file, state)
            print(f"⏩ Auto-resuming after Phase {gate_phase} gate (pending gate detected)", flush=True)
            results = state.get("_phase_results", {})
        else:
            # Fresh run: wipe state
            state_file.write_text("{}", encoding="utf-8")
            state = {}
            results = {}

            # Clean up stale temp files from previous runs to prevent
            # data bleeding between runs (e.g. stale digest-input.json
            # from run N being read by Phase 5 in run N+1).
            _cleanup_stale_temp_files()

    workspace_dir = create_workspace_dir(
        run_id,
        Path(state["_workspace_dir"]) if state.get("_workspace_dir") else None,
    )
    state["_workspace_dir"] = str(workspace_dir)

    # Persist run metadata in state
    if "_run_id" not in state:
        state["_run_id"] = run_id
        state["_started_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state_file, state)
    else:
        save_state(state_file, state)

    os.environ["PR_ORCHESTRATOR_WORKSPACE_DIR"] = str(workspace_dir)
    current_fingerprint = compute_fingerprint(existing_pr or _state_value(state, "pr_url"))

    # Set encoding env vars
    os.environ["PYTHONIOENCODING"] = "utf-8"

    print(f"═══ PR Orchestrator — mode: {mode} ═══", flush=True)
    print(f"  Branch: {git_branch}", flush=True)
    print(f"  Target: {target_branch}", flush=True)
    print(f"  State:  {state_file}", flush=True)
    print(f"  Run ID: {run_id}", flush=True)
    print(f"  Workspace: {workspace_dir}", flush=True)
    print("", flush=True)

    # Resolve platform early from git remote — no external CLI dependency
    if not state.get("platform"):
        platform = _detect_platform_from_remote(work_dir)
        if platform:
            state["platform"] = platform
            save_state(state_file, state)

    bootstrap = None
    try:
        bootstrap = _run_bootstrap(target_branch, existing_pr or "", work_dir=work_dir)
    except Exception as exc:
        print(
            f"WARNING: Deterministic bootstrap failed ({exc}); falling back to workflow bootstrap",
            flush=True,
        )

    # Update platform from bootstrap if it succeeded (may confirm or correct)
    if bootstrap and bootstrap.get("platform") in ("ado", "github"):
        state["platform"] = bootstrap["platform"]
        save_state(state_file, state)

    pipeline_start = time.monotonic()
    overall_status = "completed"
    final_pr_url: Optional[str] = None

    for phase in PHASE_SEQUENCE:
        # Skip if mode says so
        if phase.id in skip_phases:
            icon = STATUS_ICONS["skipped"]
            print(f"{icon} Phase {phase.id}: skipped ({mode} mode)", flush=True)
            results[phase.id] = {"status": "skipped", "reason": f"{mode} mode"}
            continue

        # Skip if already completed (resume scenario)
        completed = get_completed_phases(state)
        if phase.id in completed:
            if phase.id not in results:
                results[phase.id] = {"status": "completed", "reason": "resumed"}
            print(f"⏩ Phase {phase.id}: already completed (resuming)", flush=True)
            continue

        prereq_error = validate_prerequisites(phase, state, current_fingerprint)
        if prereq_error:
            print(f"🔴 {prereq_error}", flush=True)
            overall_status = "failed"
            results[phase.id] = {"status": "failed", "error": prereq_error}
            break

        # Conditional skip
        skip_reason = should_skip_phase(phase, state)
        if skip_reason:
            icon = STATUS_ICONS["skipped"]
            print(f"{icon} Phase {phase.id}: skipped ({skip_reason})", flush=True)
            results[phase.id] = {"status": "skipped", "reason": skip_reason}
            mark_phase_completed(state, phase.id)
            save_state(state_file, state)
            continue

        # Execute
        print(f"⏳ Phase {phase.id}: starting...", flush=True)
        result = execute_phase(
            phase=phase,
            state=state,
            state_file=state_file,
            target_branch=target_branch,
            scripts_dir=scripts_dir,
            workflow_dir=workflow_dir,
            merge_script=merge_script,
            run_id=run_id,
            work_dir=work_dir,
            workspace_dir=workspace_dir,
            existing_pr=existing_pr,
            current_fingerprint=current_fingerprint,
            bootstrap=bootstrap,
        )

        # Reload state (merge may have updated it)
        state = load_state(state_file)

        icon = STATUS_ICONS.get(result.status, "❓")
        duration_str = f"{result.duration_s:.0f}s"
        extra = ""
        if result.pr_url:
            final_pr_url = result.pr_url
            extra = f" → PR: {result.pr_url}"
        if result.error:
            extra += f" — {result.error}"

        print(f"{icon} Phase {phase.id}: {result.status} ({duration_str}){extra}", flush=True)

        results[phase.id] = {
            "status": result.status,
            "duration_s": round(result.duration_s, 1),
            "attempts": result.attempts,
        }
        if result.error:
            results[phase.id]["error"] = result.error

        if result.status == "completed":
            mark_phase_completed(state, phase.id)
            save_state(state_file, state)

            # Deterministic push: ensure any local commits reach the remote
            _push_local_commits(phase.id, work_dir)

            # PR body management — split by phase:
            # Phase 2: full template creation (only time fix-pr-body.py runs)
            # Phase 4/5: surgical updates only (validation refresh + digest link)
            if phase.id == "2":
                _create_pr_body(state, state_file, scripts_dir, work_dir)
                state = load_state(state_file)
                # Validate PR actually exists before continuing pipeline
                _validate_pr_exists(state, work_dir)
            elif phase.id in ("4", "5"):
                _update_pr_body(state, state_file, scripts_dir, work_dir, phase.id)
                state = load_state(state_file)

            # Interactive gate: pause after this phase for user confirmation
            if mode == "interactive" and phase.id in INTERACTIVE_GATES:
                gate_msg = INTERACTIVE_GATES[phase.id]
                state["_pending_gate"] = phase.id
                state["_gate_message"] = gate_msg
                state["_phase_results"] = dict(list(results.items())[-_MAX_PHASE_RESULTS:])
                save_state(state_file, state)

                elapsed = time.monotonic() - pipeline_start
                pr_url_now = final_pr_url or existing_pr or _state_value(state, "pr_url")
                gate_result = {
                    "status": "paused",
                    "mode": mode,
                    "run_id": run_id,
                    "pending_gate": phase.id,
                    "gate_message": gate_msg,
                    "pr_url": pr_url_now,
                    "target_branch": target_branch,
                    "state_file": str(state_file),
                    "workspace_dir": str(workspace_dir),
                    "phases": results,
                    "elapsed_s": round(elapsed, 1),
                }
                if output_file:
                    output_file.write_text(
                        json.dumps(gate_result, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                print(f"\n🔵 PAUSED after Phase {phase.id}: {gate_msg}", flush=True)
                print(f"   Resume with: python run-phases.py --mode interactive --resume", flush=True)
                sys.exit(10)

            # Live checkpoint: exit after each phase for VS Code notification
            if mode in CHECKPOINT_MODES and phase.id in INTERACTIVE_GATES:
                gate_msg = INTERACTIVE_GATES[phase.id]
                state["_pending_gate"] = phase.id
                state["_gate_message"] = gate_msg
                state["_phase_results"] = dict(list(results.items())[-_MAX_PHASE_RESULTS:])
                save_state(state_file, state)

                elapsed = time.monotonic() - pipeline_start
                pr_url_now = final_pr_url or existing_pr or _state_value(state, "pr_url")
                checkpoint_result = {
                    "status": "checkpoint",
                    "auto_resume": True,
                    "mode": mode,
                    "run_id": run_id,
                    "completed_phase": phase.id,
                    "next_phase": None,
                    "pending_gate": phase.id,
                    "gate_message": gate_msg,
                    "pr_url": pr_url_now,
                    "target_branch": target_branch,
                    "state_file": str(state_file),
                    "workspace_dir": str(workspace_dir),
                    "phases": results,
                    "elapsed_s": round(elapsed, 1),
                }
                # Determine next phase
                completed_ids = get_completed_phases(state)
                for next_p in PHASE_SEQUENCE:
                    if next_p.id not in completed_ids and next_p.id not in skip_phases:
                        checkpoint_result["next_phase"] = next_p.id
                        break
                if output_file:
                    output_file.write_text(
                        json.dumps(checkpoint_result, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                print(f"\n🔵 CHECKPOINT after Phase {phase.id}: {gate_msg}", flush=True)
                print(f"   Re-run same command to continue.", flush=True)
                sys.exit(CHECKPOINT_EXIT_CODE)
        elif result.status == "failed":
            overall_status = "failed"
            # On failure, try to continue to next phase if it doesn't depend on this one
            # Phase 2 failure is fatal (everything after needs pr_url)
            if phase.id == "2":
                print("🔴 Phase 2 failed — cannot continue without PR URL", flush=True)
                break
            # Other failures: continue (best effort)

    # ── Deterministic digest finalization ──────────────────────────
    # Always run after Phase 5, regardless of success/failure.
    # The LLM agent may or may not have updated the digest —
    # this ensures a correct, deterministic digest is always posted.
    # Keep this before workspace cleanup so Phase 5 artifacts still exist.
    if "5" in results:
        print("\n  ▸ Running deterministic digest finalization...", flush=True)
        _finalize_digest(
            state, state_file, scripts_dir, existing_pr, run_id,
            repo_root=work_dir,
        )

        # Deterministic thread resolution — resolve addressed feedback threads
        # and the digest comment thread.  Replaces manual `az rest` calls in
        # the FinalDigest prompt with a reliable script invocation.
        final_pr = existing_pr or _state_value(state, "pr_url")
        if final_pr:
            print("  ▸ Running deterministic thread resolution...", flush=True)
            _resolve_pr_threads(state, scripts_dir, workspace_dir, final_pr)

    total_duration = time.monotonic() - pipeline_start
    # For resumed runs, compute total from per-phase durations
    active_duration = sum(
        r.get("duration_s", 0) for r in results.values()
        if r.get("status") not in ("skipped", None) and r.get("reason") != "resumed"
    )

    # Use pr_url from state if we didn't capture it from Phase 2 result
    if not final_pr_url:
        final_pr_url = existing_pr or _state_value(state, "pr_url")

    # Build result
    pipeline_result = {
        "status": overall_status,
        "mode": mode,
        "run_id": run_id,
        "pr_url": final_pr_url,
        "target_branch": target_branch,
        "state_file": str(state_file),
        "workspace_dir": str(workspace_dir),
        "phases": results,
        "total_duration_s": round(active_duration, 1),
        "session_duration_s": round(total_duration, 1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    if overall_status == "completed":
        state.pop("_workspace_dir", None)
        save_state(state_file, state)
        cleanup_workspace_dir(workspace_dir)
    else:
        print(f"⚠ Preserving workspace for debugging: {workspace_dir}", flush=True)

    print("", flush=True)
    print(f"{'═' * 40}", flush=True)
    print(f"Pipeline: {overall_status.upper()} in {total_duration:.0f}s", flush=True)
    if final_pr_url:
        print(f"PR: {final_pr_url}", flush=True)

    # Write result file
    if output_file:
        output_file.write_text(
            json.dumps(pipeline_result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Result: {output_file}", flush=True)

    return pipeline_result


def _finalize_digest(
    state: dict,
    state_file: Path,
    scripts_dir: Path,
    existing_pr: Optional[str],
    run_id: str,
    repo_root: Optional[Path] = None,
) -> None:
    """Deterministic digest finalization — runs after Phase 5 regardless of outcome.
    Merges Phase 5 data, composes markdown, and upserts the PR digest comment.
    """
    pr_url = existing_pr or _state_value(state, "pr_url")
    if not pr_url:
        print("  ▸ Finalization skipped: no PR URL available", file=sys.stderr, flush=True)
        return

    tmp = Path(state.get("_workspace_dir") or tempfile.gettempdir())
    tmp.mkdir(parents=True, exist_ok=True)
    build_script = scripts_dir / "build-digest-input.py"
    compose_script = scripts_dir / "compose-digest.py"
    upsert_script = scripts_dir / "upsert-digest.py"

    # Check if we have the pieces to build a digest
    upstream = tmp / "upstream-data.json"
    digest_input = tmp / "digest-input.json"
    final_digest_input = tmp / "final-digest-input.json"
    phase5_data = tmp / "phase5-data.json"

    # If final-digest-input already exists, compose from it unless we re-merge.
    source = final_digest_input if final_digest_input.exists() else digest_input

    if not source.exists() and upstream.exists():
        # Rebuild digest-input from upstream
        cmd = [sys.executable, str(build_script), str(upstream),
             "--output-file", str(digest_input)]
        if repo_root:
            cmd.extend(["--repo-root", str(repo_root)])
        subprocess.run(cmd, check=False)
        source = digest_input

    if not source.exists():
        print("  ▸ Finalization skipped: no digest input available", flush=True)
        return

    # Always re-merge phase5-data when it exists so final-digest-input is authoritative.
    if phase5_data.exists():
        merge_source = digest_input if digest_input.exists() else source
        if not merge_source.exists():
            print("  ▸ Finalization: phase5-data exists but no base digest to merge into — skipping merge", flush=True)
        else:
            merge_args = [
                sys.executable, str(build_script), str(phase5_data),
                "--merge", str(merge_source),
                "--output-file", str(final_digest_input),
            ]
            if repo_root:
                merge_args.extend(["--repo-root", str(repo_root)])
            triage = tmp / "triage-output.json"
            if triage.exists():
                merge_args.extend(["--triage-file", str(triage)])
            subprocess.run(merge_args, check=False)
            source = final_digest_input

    # Compose
    digest_md = tmp / "final-digest.md"
    subprocess.run(
        [sys.executable, str(compose_script), str(source),
         "--output-file", str(digest_md)],
        check=False,
    )

    if digest_md.exists():
        # Detect platform
        platform = "ado" if ("dev.azure.com" in pr_url or "visualstudio.com" in pr_url) else "github"
        upsert_result = subprocess.run(
            [sys.executable, str(upsert_script),
             "--platform", platform,
             "--pr-url", pr_url,
             "--content-file", str(digest_md),
             "--workspace-dir", str(tmp)],
            capture_output=True, text=True,
        )
        # Save upsert result for downstream thread resolution
        upsert_meta = tmp / "digest-upsert-result.json"
        if upsert_result.returncode == 0 and upsert_result.stdout:
            # upsert-digest.py outputs JSON with thread_id, comment_id
            for line in upsert_result.stdout.strip().splitlines():
                if line.strip().startswith("{"):
                    try:
                        meta = json.loads(line)
                        upsert_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                    except json.JSONDecodeError:
                        pass
                    break
        print("  ▸ Finalization: digest posted from existing data", flush=True)
    else:
        print("  ▸ Finalization: compose failed, no digest posted", flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Deterministic phase driver for PR Orchestrator pipeline."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--mode",
        choices=["yolo", "yolo-fast", "interactive", "live", "live-fast"],
        default=None,
        help="Execution mode for full pipeline (default: yolo)",
    )
    group.add_argument(
        "--phase",
        choices=VALID_PHASE_IDS,
        default=None,
        help="Run a single phase standalone (e.g. --phase 1c)",
    )
    parser.add_argument(
        "--target-branch",
        default="main",
        help="Target branch for the PR (default: main)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path.cwd(),
        help="Working directory (git repo root)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="Path to write JSON result file",
    )
    parser.add_argument(
        "--existing-pr",
        default=None,
        help="Existing PR URL (skips Phase 2 PR creation check)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume from an interactive gate pause (loads existing state)",
    )
    parser.add_argument(
        "--skip-next",
        action="store_true",
        default=False,
        help="When resuming, skip the next phase instead of running it",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="Explicit state file path (useful for resume with non-default state)",
    )
    args = parser.parse_args()

    if args.resume and args.phase:
        parser.error("--resume and --phase cannot be used together")
    if args.skip_next and not args.resume:
        parser.error("--skip-next requires --resume")

    os.chdir(args.work_dir)

    # Default to yolo mode when neither --mode nor --phase is specified
    mode = args.mode or "yolo"

    if args.phase:
        result = run_single_phase(
            phase_id=args.phase,
            target_branch=args.target_branch,
            work_dir=args.work_dir,
            output_file=args.output_file,
            existing_pr=args.existing_pr,
            state_file_override=args.state_file,
        )
    else:
        result = run_pipeline(
            mode=mode,
            target_branch=args.target_branch,
            work_dir=args.work_dir,
            output_file=args.output_file,
            existing_pr=args.existing_pr,
            resume=args.resume,
            state_file_override=args.state_file,
            skip_next=args.skip_next,
        )

    if result["status"] == "paused":
        sys.exit(10)
    sys.exit(0 if result["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
