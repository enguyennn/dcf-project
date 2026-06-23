#!/usr/bin/env python3
"""Validate and normalize raw Phase 1c output before downstream use."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from phase_output_validation import (
    ValidationError,
    normalize_phase1c_output,
    parse_json_like,
    write_json,
)

_SEVERITY_KEYS = {
    "critical",
    "Critical",
    "important",
    "Important",
    "high",
    "High",
    "medium",
    "Medium",
    "low",
    "Low",
    "suggestion",
    "Suggestion",
    "suggestions",
}

_COUNT_CONTAINER_KEYS = {"summary", "counts"}
_COUNT_FIELD_KEYS = {
    "count",
    "counts",
    "total",
    "total_findings",
    "findings_count",
    "critical",
    "important",
    "suggestion",
    "suggestions",
    "high",
    "medium",
    "low",
}


def _resolve_output_path(workspace_dir: str | None, output_file: str | None) -> Path:
    if output_file:
        return Path(output_file)
    base = Path(workspace_dir) if workspace_dir else Path.cwd()
    base.mkdir(parents=True, exist_ok=True)
    return base / "phase1c-output.json"


def _resolve_findings_path(workspace_dir: str | None, findings_file: str | None) -> Path:
    if findings_file:
        return Path(findings_file)
    base = Path(workspace_dir) if workspace_dir else Path.cwd()
    base.mkdir(parents=True, exist_ok=True)
    return base / "code-review-findings.json"


def _looks_like_findings_alias(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) == 0
    if not isinstance(value, dict):
        return False
    if any(key in value for key in _SEVERITY_KEYS):
        return True
    nested = value.get("findings")
    return isinstance(nested, dict) and (not nested or any(key in nested for key in _SEVERITY_KEYS))


def _extract_findings_alias(outer: dict[str, Any]) -> Any:
    findings_alias = outer.get("findings")
    if findings_alias is not None:
        if isinstance(findings_alias, str):
            return findings_alias
        if isinstance(findings_alias, list):
            return findings_alias
        if _looks_like_findings_alias({"findings": findings_alias}):
            return findings_alias

    candidate = {
        key: value
        for key, value in outer.items()
        if key not in {"done", "tier", "review_engine", "human_judgment_findings"}
    }
    if _looks_like_findings_alias(candidate):
        return candidate
    return None


def _coerce_findings_count_fields(value: Any, *, key_name: str | None = None, parent_key: str | None = None) -> Any:
    lowered_key = (key_name or "").strip().lower()
    lowered_parent = (parent_key or "").strip().lower()

    if isinstance(value, dict):
        return {
            key: _coerce_findings_count_fields(val, key_name=str(key), parent_key=lowered_key)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [
            _coerce_findings_count_fields(item, key_name=key_name, parent_key=lowered_parent)
            for item in value
        ]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lstrip("+-").isdigit():
            if lowered_key.endswith("_count") or lowered_key in _COUNT_FIELD_KEYS:
                return int(stripped)
            if lowered_parent in _COUNT_CONTAINER_KEYS and lowered_key in _COUNT_FIELD_KEYS:
                return int(stripped)
    return value


def _prepare_phase1c_output(raw_output: Any) -> dict[str, Any]:
    outer = parse_json_like(raw_output, "phase1c output", expected_types=(dict,))
    prepared = dict(outer)

    if prepared.get("code_review_findings") is None:
        alias_payload = _extract_findings_alias(prepared)
        if alias_payload is not None:
            prepared["code_review_findings"] = alias_payload

    return prepared


def _describe_payload_keys(raw_output: Any) -> str:
    try:
        outer = parse_json_like(raw_output, "phase1c output", expected_types=(dict,))
    except ValidationError as exc:
        return str(exc)

    keys = ", ".join(sorted(str(key) for key in outer.keys())) or "<none>"
    return f"top-level keys: {keys}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and normalize Phase 1c output")
    parser.add_argument("--raw-output", required=True, help="Raw Phase 1c JSON output")
    parser.add_argument("--workspace-dir", default="", help="Directory for per-run artifacts")
    parser.add_argument("--output-file", default="", help="Path for normalized Phase 1c output")
    parser.add_argument("--findings-file", default="", help="Path for normalized code_review_findings payload")
    args = parser.parse_args()

    try:
        prepared = _prepare_phase1c_output(args.raw_output)
        normalized = normalize_phase1c_output(prepared)
        normalized["code_review_findings"] = _coerce_findings_count_fields(normalized["code_review_findings"])
    except ValidationError as exc:
        hint = _describe_payload_keys(args.raw_output)
        print(
            f"ERROR: {exc}. Accepted shapes: code_review_findings=<dict/list/json-string> or findings=<alias>. {hint}",
            file=sys.stderr,
        )
        return 1

    output_path = _resolve_output_path(args.workspace_dir, args.output_file)
    findings_path = _resolve_findings_path(args.workspace_dir, args.findings_file)
    write_json(output_path, normalized)
    write_json(findings_path, normalized["code_review_findings"])
    print(json.dumps(normalized, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
