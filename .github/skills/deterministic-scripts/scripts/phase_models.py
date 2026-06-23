#!/usr/bin/env python3
"""Typed dataclass models for PR Orchestrator phase outputs.

Replaces the raw-dict + PHASE_SCHEMAS + FIELD_TYPE_COERCIONS approach with
strongly-typed models that coerce on construction. Zero external dependencies.

Usage at write boundary (merge-state.py):
    model = PHASE_MODELS["1d"].from_raw(raw_output)
    clean = model.to_dict()

Usage at read boundary (build-digest-input.py):
    model = PHASE_MODELS["5"].from_raw(state["_phases"]["5"])
    commits = model.fix_commits  # guaranteed list
"""

from __future__ import annotations

import ast as _ast
import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, ClassVar

from encoding_utils import sanitize_llm_json


# ---------------------------------------------------------------------------
# Coercion helpers (standalone, reusable)
# ---------------------------------------------------------------------------

def to_list(val: Any) -> list:
    """Coerce *val* to a list. Handles string-repr like ``"['a','b']"``."""
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


def to_bool(val: Any) -> bool:
    """Coerce *val* to bool, handling common string representations."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "passed")
    return bool(val)


def to_int(val: Any, default: int = 0) -> int:
    """Coerce *val* to int safely."""
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val.strip())
        except (ValueError, AttributeError):
            return default
    return default


# Phase 5 status canonicalization
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


def canonicalize_status(val: Any) -> str | None:
    """Map a Phase 5 status/final_verdict value to canonical form."""
    if not val:
        return None
    s = str(val).strip().lower().replace(" ", "_")
    return _STATUS_ALIASES.get(s, s)


def parse_findings_dict(val: Any) -> tuple[dict, bool]:
    """Parse code_review_findings payloads into a dict.

    Returns ``(parsed_dict, parse_failed)``. ``parse_failed`` is only true when
    a string payload was provided but none of the supported parsing strategies
    produced a dict.
    """
    if isinstance(val, dict):
        return val, False
    if not isinstance(val, str):
        return {}, False

    sanitized = sanitize_llm_json(val)
    candidates = [val, sanitized, sanitized.replace("\\n", "\n")]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, str):
            try:
                parsed = json.loads(sanitize_llm_json(parsed))
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(parsed, dict):
            return parsed, False

    try:
        parsed = _ast.literal_eval(sanitized)
    except (ValueError, SyntaxError):
        parsed = None

    if isinstance(parsed, dict):
        return parsed, False

    return {}, True


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------

@dataclass
class PhaseModel:
    """Base for all phase output models.

    Subclasses declare typed fields and coerce in ``__post_init__``.
    ``ALIASES`` maps non-canonical keys to canonical field names.
    """

    ALIASES: ClassVar[dict[str, str]] = {}

    # Set of field names that were explicitly provided in from_raw().
    # Not a dataclass field — set as object attr after construction.

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "PhaseModel":
        """Construct from an untyped dict (LLM output, state file, etc.).

        Resolves aliases, drops unknown keys, and lets ``__post_init__``
        coerce types.  Never raises on missing optional fields (they get
        their dataclass defaults).
        """
        if not isinstance(raw, dict):
            inst = cls()
            object.__setattr__(inst, "_provided_fields", set())
            return inst

        # Resolve aliases first
        resolved: dict[str, Any] = {}
        for alias, canonical in cls.ALIASES.items():
            if alias in raw and canonical not in raw:
                resolved[canonical] = raw[alias]
        merged = {**raw, **resolved}

        # Keep only known fields
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in merged.items() if k in known}
        inst = cls(**filtered)
        object.__setattr__(inst, "_provided_fields", set(filtered.keys()))
        return inst

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a clean dict for the JSON state file.

        Only emits fields that were explicitly provided via ``from_raw()``,
        or all fields if constructed directly. Drops ``None`` values.
        """
        provided = getattr(self, "_provided_fields", None)
        result = {}
        for k, v in asdict(self).items():
            if v is None:
                continue
            # If we know which fields were provided, only emit those
            if provided is not None and k not in provided:
                continue
            result[k] = v
        return result


# ---------------------------------------------------------------------------
# Phase models
# ---------------------------------------------------------------------------

@dataclass
class Phase1aOutput(PhaseModel):
    """Change digest and test coverage analysis."""

    ALIASES: ClassVar[dict[str, str]] = {"test_count": "tests_run"}

    business_logic_digest: str = ""
    test_coverage_digest: str = ""
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0

    def __post_init__(self) -> None:
        self.tests_run = to_int(self.tests_run)
        self.tests_passed = to_int(self.tests_passed)
        self.tests_failed = to_int(self.tests_failed)


@dataclass
class Phase1bOutput(PhaseModel):
    """Test generation."""

    test_generation_result: str = ""


@dataclass
class Phase1cOutput(PhaseModel):
    """Code review findings."""

    code_review_findings: dict = field(default_factory=dict)
    tier: str = ""
    human_judgment_findings: list = field(default_factory=list)
    review_engine: str = ""

    def __post_init__(self) -> None:
        raw_findings = self.code_review_findings
        parsed_findings, parse_failed = parse_findings_dict(raw_findings)
        self.code_review_findings = parsed_findings
        self.human_judgment_findings = to_list(self.human_judgment_findings)
        object.__setattr__(self, "_code_review_findings_raw", raw_findings)
        object.__setattr__(self, "_code_review_findings_parse_failed", parse_failed)
        object.__setattr__(self, "_code_review_findings_raw_type", type(raw_findings).__name__)
        object.__setattr__(self, "_code_review_findings_raw_len", len(raw_findings) if isinstance(raw_findings, str) else 0)


@dataclass
class Phase1dOutput(PhaseModel):
    """Code fix results."""

    code_fix: dict = field(default_factory=dict)
    fixes_applied: int = 0
    fix_commits: list = field(default_factory=list)
    findings_remaining: int = 0

    def __post_init__(self) -> None:
        self.fixes_applied = to_int(self.fixes_applied)
        self.fix_commits = to_list(self.fix_commits)
        self.findings_remaining = to_int(self.findings_remaining)
        # Coerce nested fix_commits inside code_fix dict
        if isinstance(self.code_fix, dict) and "fix_commits" in self.code_fix:
            self.code_fix["fix_commits"] = to_list(self.code_fix["fix_commits"])


@dataclass
class Phase2Output(PhaseModel):
    """PR creation results."""

    pr_url: str = ""
    pr_title: str = ""
    work_items_linked: int = 0

    def __post_init__(self) -> None:
        self.work_items_linked = to_int(self.work_items_linked)
        if self.pr_url and not self.pr_url.startswith("http"):
            raise ValueError(f"pr_url must be a URL, got: {self.pr_url[:100]}")


@dataclass
class Phase3Output(PhaseModel):
    """Watch-and-fix loop results."""

    ALIASES: ClassVar[dict[str, str]] = {"total_fixes_pushed": "fixes_pushed"}

    build_status: str = ""
    fixes_pushed: int = 0
    fix_summaries: list = field(default_factory=list)
    fix_commits: list = field(default_factory=list)
    elapsed_minutes: int = 0

    def __post_init__(self) -> None:
        self.fixes_pushed = to_int(self.fixes_pushed)
        self.fix_summaries = to_list(self.fix_summaries)
        self.fix_commits = to_list(self.fix_commits)
        self.elapsed_minutes = to_int(self.elapsed_minutes)


@dataclass
class Phase4Output(PhaseModel):
    """Digest posting results."""

    digest_comment_url: str = ""
    digest_comment_id: str = ""


@dataclass
class Phase4bOutput(PhaseModel):
    """PR walkthrough results."""

    walkthrough_posted: bool = False
    pr_classification: str = ""
    skip_reason: str = ""
    diagram_count: int = 0
    concepts_explained: int = 0

    def __post_init__(self) -> None:
        self.walkthrough_posted = to_bool(self.walkthrough_posted)
        self.diagram_count = to_int(self.diagram_count)
        self.concepts_explained = to_int(self.concepts_explained)


@dataclass
class AddressedDetail(PhaseModel):
    """Validated Phase 5 addressed_details entry."""

    ALIASES: ClassVar[dict[str, str]] = {
        "file": "file_path",
        "finding_summary": "comment",
        "resolution": "status",
    }

    thread_id: str = ""
    status: str = ""
    comment: str = ""
    file_path: str = ""


@dataclass
class Phase5Output(PhaseModel):
    """Address review feedback results."""

    address_feedback: dict = field(default_factory=dict)
    comments_addressed: int = 0
    comments_remaining: int = 0
    total_comments_addressed: int = 0
    total_fixes_pushed: int = 0
    all_addressed: bool = False
    addressed_details: list = field(default_factory=list)
    fix_commits: list = field(default_factory=list)
    status: str = ""
    iteration: int = 0
    final_verdict: str = ""
    digest_updated: bool = False
    pr_url: str = ""

    def __post_init__(self) -> None:
        self.comments_addressed = to_int(self.comments_addressed)
        self.comments_remaining = to_int(self.comments_remaining)
        self.total_comments_addressed = to_int(self.total_comments_addressed)
        self.total_fixes_pushed = to_int(self.total_fixes_pushed)
        self.all_addressed = to_bool(self.all_addressed)
        self.addressed_details = self._coerce_addressed_details(self.addressed_details)
        self.fix_commits = to_list(self.fix_commits)
        self.iteration = to_int(self.iteration)
        self.digest_updated = to_bool(self.digest_updated)

        if self.total_comments_addressed and not self.comments_addressed:
            self.comments_addressed = self.total_comments_addressed
        elif self.comments_addressed and not self.total_comments_addressed:
            self.total_comments_addressed = self.comments_addressed

        if self.fix_commits and not self.total_fixes_pushed:
            self.total_fixes_pushed = len(self.fix_commits)

        # Canonicalize status from address_feedback if not set directly
        if not self.status and isinstance(self.address_feedback, dict):
            verdict = self.address_feedback.get("final_verdict", "")
            canonical = canonicalize_status(verdict)
            if canonical:
                self.status = canonical
                # Mark derived field as provided for to_dict()
                pf = getattr(self, "_provided_fields", None)
                if pf is not None:
                    pf.add("status")

        # Coerce nested list fields inside address_feedback
        if isinstance(self.address_feedback, dict):
            if "fix_commits" in self.address_feedback:
                self.address_feedback["fix_commits"] = to_list(self.address_feedback["fix_commits"])
            if "addressed_details" in self.address_feedback:
                self.address_feedback["addressed_details"] = self._coerce_addressed_details(self.address_feedback["addressed_details"])

    @staticmethod
    def _coerce_addressed_details(value: Any) -> list:
        coerced = []
        for detail in to_list(value):
            if isinstance(detail, dict):
                normalized = dict(detail)
                normalized.update(AddressedDetail.from_raw(detail).to_dict())
                coerced.append(normalized)
            else:
                coerced.append(detail)
        return coerced


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PHASE_MODELS: dict[str, type[PhaseModel]] = {
    "1a": Phase1aOutput,
    "1b": Phase1bOutput,
    "1c": Phase1cOutput,
    "1d": Phase1dOutput,
    "2": Phase2Output,
    "3": Phase3Output,
    "4": Phase4Output,
    "4b": Phase4bOutput,
    "5": Phase5Output,
}
