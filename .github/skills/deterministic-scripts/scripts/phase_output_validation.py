#!/usr/bin/env python3
"""Shared validation helpers for deterministic PR Orchestrator phase outputs."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

from encoding_utils import sanitize_llm_json
from phase_contracts import normalize_phase_output, read_phase_output, validate_phase_output


class ValidationError(ValueError):
    """Raised when a phase payload cannot be normalized deterministically."""


_SEVERITY_KEYS = (
    "critical",
    "Critical",
    "important",
    "Important",
    "high",
    "High",
    "suggestion",
    "Suggestion",
    "suggestions",
    "medium",
    "Medium",
    "low",
    "Low",
)


def _candidate_strings(raw: str) -> list[str]:
    stripped = raw.strip()
    if not stripped:
        return []

    sanitized = sanitize_llm_json(stripped)
    candidates = [stripped, sanitized, sanitized.replace("\\n", "\n")]
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            unique.append(candidate)
            seen.add(candidate)
    return unique


def parse_json_like(
    value: Any,
    label: str,
    *,
    expected_types: tuple[type, ...] = (dict,),
    allow_plain_string: bool = False,
) -> Any:
    """Parse LLM-emitted JSON-ish content using a deterministic fallback chain."""
    if isinstance(value, expected_types):
        return value

    if value is None:
        raise ValidationError(f"{label} is missing")

    if isinstance(value, str):
        last_error: Exception | None = None
        for candidate in _candidate_strings(value):
            parsed: Any = candidate
            unwrap_depth = 0
            while isinstance(parsed, str) and unwrap_depth < 3:
                try:
                    parsed = json.loads(parsed)
                except (json.JSONDecodeError, TypeError) as exc:
                    last_error = exc
                    break
                unwrap_depth += 1
            if isinstance(parsed, expected_types):
                return parsed
            if allow_plain_string and isinstance(parsed, str):
                return parsed.strip()

        try:
            parsed = ast.literal_eval(sanitize_llm_json(value))
        except (ValueError, SyntaxError) as exc:
            last_error = exc
        else:
            if isinstance(parsed, expected_types):
                return parsed
            if allow_plain_string and isinstance(parsed, str):
                return parsed.strip()

        detail = f": {last_error}" if last_error else ""
        raise ValidationError(f"{label} is not valid JSON{detail}")

    raise ValidationError(f"{label} is {type(value).__name__}, expected {'/'.join(t.__name__ for t in expected_types)}")


def coerce_int(value: Any, label: str, *, default: int = 0) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    raise ValidationError(f"{label} must be an integer")


def coerce_bool(value: Any, label: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n", ""}:
            return False
    raise ValidationError(f"{label} must be a boolean")


def ensure_str_list(value: Any, label: str) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = parse_json_like(stripped, label, expected_types=(list,))
        except ValidationError:
            return [stripped]
        return [str(item).strip() for item in parsed if str(item).strip()]
    raise ValidationError(f"{label} must be a list of strings")


def normalize_remaining_findings(value: Any) -> Any:
    if value in (None, ""):
        return []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("{") or stripped.startswith("[") or stripped.startswith('"'):
            try:
                return parse_json_like(stripped, "findings_remaining", expected_types=(list, dict), allow_plain_string=True)
            except ValidationError:
                return stripped
        return stripped
    return value


def canonical_empty_findings() -> dict[str, Any]:
    return {
        "findings": {
            "Critical": [],
            "Important": [],
            "Suggestion": [],
        }
    }


def has_findings_shape(payload: Any) -> bool:
    if isinstance(payload, list):
        return len(payload) == 0
    if not isinstance(payload, dict):
        return False
    if not payload:
        return True

    search_dicts = [payload]
    nested = payload.get("findings")
    if isinstance(nested, dict):
        search_dicts.append(nested)

    for search in search_dicts:
        for key in _SEVERITY_KEYS:
            if key in search and isinstance(search.get(key), list):
                return True
    return False


def count_findings(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0

    total = 0
    search_dicts = [payload]
    nested = payload.get("findings")
    if isinstance(nested, dict):
        search_dicts.append(nested)

    for search in search_dicts:
        for key in _SEVERITY_KEYS:
            items = search.get(key)
            if isinstance(items, list):
                total += len(items)
    return total


def normalize_phase1c_output(raw_output: Any) -> dict[str, Any]:
    outer = parse_json_like(raw_output, "phase1c output", expected_types=(dict,))
    findings_raw = outer.get("code_review_findings")
    if findings_raw is None:
        raise ValidationError("phase1c output is missing code_review_findings")

    if isinstance(findings_raw, list):
        if findings_raw:
            raise ValidationError("code_review_findings list output must be empty or bucketed by severity")
        findings = canonical_empty_findings()
    else:
        findings = parse_json_like(findings_raw, "code_review_findings", expected_types=(dict, list))
        if isinstance(findings, list):
            if findings:
                raise ValidationError("code_review_findings list output must be empty or bucketed by severity")
            findings = canonical_empty_findings()
        elif findings == {}:
            findings = canonical_empty_findings()

    if not has_findings_shape(findings):
        raise ValidationError("code_review_findings must contain severity buckets or an explicit empty payload")

    normalized = {
        "code_review_findings": findings,
        "done": coerce_bool(outer.get("done", True), "done", default=True),
    }

    tier = outer.get("tier")
    if tier is None and isinstance(findings, dict):
        tier = findings.get("tier")
    if tier not in (None, ""):
        normalized["tier"] = str(tier)

    review_engine = outer.get("review_engine")
    if review_engine is None and isinstance(findings, dict):
        review_engine = findings.get("review_engine")
    if review_engine not in (None, ""):
        normalized["review_engine"] = str(review_engine)

    hjf = outer.get("human_judgment_findings")
    if hjf is None and isinstance(findings, dict):
        hjf = findings.get("human_judgment_findings")
    if hjf not in (None, ""):
        normalized["human_judgment_findings"] = parse_json_like(
            hjf,
            "human_judgment_findings",
            expected_types=(list,),
        )

    normalized = normalize_phase_output("1c", normalized)
    valid, warnings = validate_phase_output("1c", normalized)
    if not valid:
        raise ValidationError("; ".join(warnings))
    return normalized


def normalize_phase1d_output(raw_output: Any) -> dict[str, Any]:
    outer = parse_json_like(raw_output, "phase1d output", expected_types=(dict,))
    nested_raw = outer.get("code_fix", {})
    if nested_raw in (None, ""):
        nested = {}
    elif isinstance(nested_raw, dict):
        nested = nested_raw
    elif isinstance(nested_raw, str):
        nested = parse_json_like(nested_raw, "code_fix", expected_types=(dict,))
    else:
        nested = {}

    fixes_applied = coerce_int(
        outer.get("fixes_applied", nested.get("fixes_applied", 0)),
        "fixes_applied",
        default=0,
    )
    fix_commits = ensure_str_list(
        outer.get("fix_commits", nested.get("fix_commits", [])),
        "fix_commits",
    )
    findings_remaining = normalize_remaining_findings(
        outer.get("findings_remaining", nested.get("findings_remaining", []))
    )
    done = coerce_bool(outer.get("done", True), "done", default=True)

    if not outer and not nested and fixes_applied == 0 and not fix_commits and findings_remaining == []:
        raise ValidationError("phase1d output is empty")

    normalized = {
        "code_fix": {
            "fixes_applied": fixes_applied,
            "fix_commits": fix_commits,
            "findings_remaining": findings_remaining,
        },
        "fixes_applied": fixes_applied,
        "fix_commits": fix_commits,
        "findings_remaining": findings_remaining,
        "done": done,
    }

    normalized = normalize_phase_output("1d", normalized)
    valid, warnings = validate_phase_output("1d", normalized)
    if not valid:
        raise ValidationError("; ".join(warnings))
    return normalized


def validate_upstream_data(data: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """Validate that upstream state can safely rebuild a digest baseline."""
    if not isinstance(data, dict):
        return False, ["upstream data is not a JSON object"]

    issues: list[str] = []

    phase_1c = read_phase_output(data, "1c") or {}
    findings_raw = phase_1c.get("code_review_findings")
    if findings_raw is None:
        issues.append("missing code_review_findings")
    else:
        try:
            normalized = normalize_phase1c_output({
                "code_review_findings": findings_raw,
                "tier": phase_1c.get("tier"),
                "human_judgment_findings": phase_1c.get("human_judgment_findings"),
                "review_engine": phase_1c.get("review_engine"),
                "done": True,
            })
            findings = normalized["code_review_findings"]
            if not has_findings_shape(findings):
                issues.append("code_review_findings is missing severity buckets or explicit empty arrays")
            elif count_findings(findings) < 0:
                issues.append("code_review_findings count is invalid")
        except ValidationError as exc:
            issues.append(f"code_review_findings: {exc}")

    return len(issues) == 0, issues


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
