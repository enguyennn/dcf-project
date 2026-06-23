#!/usr/bin/env python3
"""Phase output contracts for PR Orchestrator deterministic scripts."""

from __future__ import annotations

import datetime
import json
import re
import subprocess
from typing import Any
from urllib.parse import urlparse

PHASE_ALIASES: dict[str, dict[str, str]] = {
    "1a": {"test_count": "tests_run"},
    "3": {"total_fixes_pushed": "fixes_pushed"},
}

PHASE_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "1a": {
        "required": [],
        "optional": [
            "business_logic_digest",
            "test_coverage_digest",
            "tests_run",
            "tests_passed",
            "tests_failed",
        ],
    },
    "1b": {"required": [], "optional": ["test_generation_result"]},
    "1c": {
        "required": ["code_review_findings"],
        "optional": ["tier", "human_judgment_findings", "review_engine"],
    },
    "1d": {
        "required": [],
        "optional": ["code_fix", "fixes_applied", "fix_commits", "findings_remaining"],
    },
    "2": {"required": ["pr_url"], "optional": ["pr_title", "work_items_linked"]},
    "3": {
        "required": ["build_status"],
        "optional": ["fixes_pushed", "fix_summaries", "fix_commits", "elapsed_minutes"],
    },
    "4": {"required": ["digest_comment_url"], "optional": ["digest_comment_id"]},
    "4b": {
        "required": ["walkthrough_posted"],
        "optional": [
            "pr_classification",
            "skip_reason",
            "diagram_count",
            "concepts_explained",
        ],
    },
    "5": {
        "required": [],
        "optional": [
            "address_feedback",
            "comments_addressed",
            "comments_remaining",
            "all_addressed",
            "addressed_details",
            "fix_commits",
            "status",
            "iteration",
        ],
    },
}

# Type coercion rules per field name.
# Keys that appear in ANY phase schema with these names get coerced.
# "list" fields: ensure_list (handles string-repr like "['a']")
# "bool" fields: truthy coercion
# "status_enum" fields: canonical status mapping
FIELD_TYPE_COERCIONS: dict[str, str] = {
    "fix_commits": "list",
    "fix_summaries": "list",
    "risk_signals": "list",
    "addressed_details": "list",
    "all_addressed": "bool",
    "walkthrough_posted": "bool",
}

# Canonical status values for Phase 5 address_feedback
_STATUS_ALIASES: dict[str, str] = {
    "completed": "no_feedback",
    "done": "no_feedback",
    "no feedback": "no_feedback",
    "no_feedback": "no_feedback",
    "addressed": "all_addressed",
    "all_addressed": "all_addressed",
    "partial": "partial",
    "remaining": "partial",
}


def _coerce_list(val: Any) -> list:
    """Coerce to list, handling string-repr like \"['a', 'b']\"."""
    import ast as _ast

    if isinstance(val, list):
        return val
    if not val:
        return []
    if isinstance(val, str):
        stripped = val.strip()
        if stripped.startswith("["):
            try:
                return json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                result = _ast.literal_eval(stripped)
                if isinstance(result, list):
                    return result
            except (ValueError, SyntaxError):
                pass
        return [stripped]
    return [val]


def _coerce_bool(val: Any) -> bool:
    """Coerce to bool, handling string representations."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "passed")
    return bool(val)


def canonicalize_status(val: Any) -> str | None:
    """Map a Phase 5 status/final_verdict value to canonical form, or None if empty."""
    if not val:
        return None
    s = str(val).strip().lower().replace(" ", "_")
    return _STATUS_ALIASES.get(s, s)


def coerce_phase_types(phase_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Apply type coercion to phase output fields based on FIELD_TYPE_COERCIONS.

    Called after normalize_phase_output to ensure downstream consumers
    always see correct types (lists are lists, bools are bools, etc.).
    This is the central defense-in-depth layer that prevents type confusion
    bugs like B1 (string-repr fix_commits) from propagating.
    """
    if not isinstance(data, dict):
        return data

    result = dict(data)
    for key, val in result.items():
        coercion = FIELD_TYPE_COERCIONS.get(key)
        if coercion == "list":
            result[key] = _coerce_list(val)
        elif coercion == "bool":
            result[key] = _coerce_bool(val)

    # Phase 5 special: canonicalize status from final_verdict if missing
    if phase_id == "5":
        af = result.get("address_feedback")
        if isinstance(af, dict):
            if not af.get("status") and af.get("final_verdict"):
                canonical = canonicalize_status(af["final_verdict"])
                if canonical:
                    af["status"] = canonical
            # Coerce nested fields too
            for key in ("fix_commits", "addressed_details"):
                if key in af:
                    af[key] = _coerce_list(af[key])

    return result


def normalize_phase_output(phase_id: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    """Apply phase alias resolution, type coercion, and return canonical keys."""
    if not isinstance(raw, dict):
        return {}

    aliases = PHASE_ALIASES.get(phase_id, {})
    normalized = dict(raw)
    for alias_key, canonical_key in aliases.items():
        if alias_key not in raw:
            continue
        if canonical_key not in normalized or normalized.get(canonical_key) is None:
            normalized[canonical_key] = raw[alias_key]
        normalized.pop(alias_key, None)
    return coerce_phase_types(phase_id, normalized)


def validate_phase_output(phase_id: str, data: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Validate required keys for a phase output."""
    schema = PHASE_SCHEMAS.get(phase_id)
    if not schema:
        return True, []

    normalized = normalize_phase_output(phase_id, data)
    warnings = [
        f"missing key: {key}"
        for key in schema.get("required", [])
        if normalized.get(key) is None
    ]
    return len(warnings) == 0, warnings


def read_phase_output(state: dict[str, Any] | None, phase_id: str) -> dict[str, Any] | None:
    """Read phase output from canonical _phases first, then flat legacy keys."""
    if not isinstance(state, dict):
        return None

    phases = state.get("_phases", {})
    if isinstance(phases, dict):
        canonical = phases.get(phase_id)
        if isinstance(canonical, dict):
            result = normalize_phase_output(phase_id, canonical)
            if not isinstance(result, dict):
                return None
            return result

    schema = PHASE_SCHEMAS.get(phase_id)
    aliases = PHASE_ALIASES.get(phase_id, {})
    if not schema and not aliases:
        return None

    candidate_keys = []
    if schema:
        candidate_keys.extend(schema.get("required", []))
        candidate_keys.extend(schema.get("optional", []))
    candidate_keys.extend(aliases.keys())

    flat: dict[str, Any] = {}
    for key in candidate_keys:
        if key in state:
            flat[key] = state[key]

    if not flat:
        return None

    result = normalize_phase_output(phase_id, flat)
    if not isinstance(result, dict):
        return None
    return result


def build_phase_meta(
    phase_id: str,
    output: dict[str, Any] | None,
    duration_s: float,
    fingerprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a _phase_meta entry for a completed phase."""
    del phase_id  # Reserved for future schema expansion.
    return {
        "completed_at": datetime.datetime.utcnow().isoformat() + "Z",
        "duration_s": round(duration_s, 1),
        "output_keys": sorted(
            k for k in (output or {}).keys() if not str(k).startswith("_")
        ),
        "fingerprint": fingerprint or {},
    }


def _normalize_fingerprint(raw: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    pr_head = raw.get("pr_head") or raw.get("head") or raw.get("headRefOid")
    base_sha = raw.get("base_sha") or raw.get("base") or raw.get("baseRefOid")
    normalized = {}
    if pr_head:
        normalized["pr_head"] = str(pr_head)
    if base_sha:
        normalized["base_sha"] = str(base_sha)
    return normalized


def compute_fingerprint(pr_url: str | None = None) -> dict[str, str]:
    """Compute current PR fingerprint (head SHA + base SHA)."""
    if not pr_url:
        return {}

    try:
        parsed = urlparse(pr_url)
        host = (parsed.netloc or "").lower()

        if "github.com" in host:
            result = subprocess.run(
                ["gh", "pr", "view", pr_url, "--json", "headRefOid,baseRefOid"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return {}
            return _normalize_fingerprint(json.loads(result.stdout or "{}"))

        if "dev.azure.com" in host or "visualstudio.com" in host:
            match = re.search(r"/pullrequest/(\d+)", parsed.path or "")
            if not match:
                return {}
            pr_id = match.group(1)
            if "dev.azure.com" in host:
                org_name = (parsed.path or "").strip("/").split("/")[0]
                if not org_name:
                    return {}
                org_url = f"https://dev.azure.com/{org_name}"
            else:
                org_name = host.split(".", 1)[0]
                if not org_name:
                    return {}
                org_url = f"https://{org_name}.visualstudio.com"

            result = subprocess.run(
                [
                    "az",
                    "repos",
                    "pr",
                    "show",
                    "--id",
                    pr_id,
                    "--org",
                    org_url,
                    "--query",
                    "{pr_head:lastMergeSourceCommit.commitId,base_sha:lastMergeTargetCommit.commitId}",
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return {}
            return _normalize_fingerprint(json.loads(result.stdout or "{}"))
    except Exception:
        return {}

    return {}


def is_phase_fresh(
    state: dict[str, Any] | None,
    phase_id: str,
    current_fingerprint: dict[str, Any] | None = None,
) -> bool:
    """Check whether a phase output still matches the current PR fingerprint."""
    meta = (state or {}).get("_phase_meta", {})
    if not isinstance(meta, dict):
        return True
    entry = meta.get(phase_id)
    if not isinstance(entry, dict):
        return True
    stored_fp = entry.get("fingerprint", {})
    if not stored_fp or not current_fingerprint:
        return True
    return stored_fp.get("pr_head") == current_fingerprint.get("pr_head")
