#!/usr/bin/env python3
"""Merge Conductor phase output into the cross-phase state file.

Deterministic script that replaces fragile inline PowerShell JSON merging.
Handles all the edge cases that break ConvertFrom-Json: unescaped backslashes,
mixed stdout (non-JSON preamble/postamble), cp1252 encoding garbling, etc.

Usage:
    # From a captured output file
    python merge-state.py --output-file phase1a-output.json --state-file state.json --phase 1a

    # From stdin (piped from Conductor)
    conductor run ... -s 2>$null | python merge-state.py --state-file state.json --phase 1c

    # Dry-run: show what would be merged without writing
    python merge-state.py --output-file out.json --state-file state.json --phase 1a --dry-run

Output: One-line summary to stdout. Detailed errors to stderr.
Exit code: 0 = success, 1 = failure (no state file modification on failure).
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from phase_contracts import (
        PHASE_ALIASES,
        PHASE_SCHEMAS,
        normalize_phase_output,
        read_phase_output,
        validate_phase_output,
    )
except ImportError:  # pragma: no cover - backward-compatible fallback
    PHASE_SCHEMAS = {}
    PHASE_ALIASES = {}

    def normalize_phase_output(phase_id: str, raw: dict) -> dict:
        return raw if isinstance(raw, dict) else {}

    def read_phase_output(state: dict, phase_id: str) -> dict | None:
        return None

    def validate_phase_output(phase_id: str, data: dict) -> tuple[bool, list[str]]:
        return True, []

try:
    from phase_models import PHASE_MODELS
except ImportError:  # pragma: no cover
    PHASE_MODELS = {}


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def fix_backslashes(text: str) -> str:
    r"""Fix unescaped backslashes in JSON strings (common in Windows paths).

    Targets backslashes inside quoted strings that aren't already part of
    a valid escape sequence (\\, \", \n, \r, \t, \b, \f, \/, \uXXXX).
    """
    def _fix_in_string(match: re.Match) -> str:
        s = match.group(0)
        # Replace backslashes not followed by valid escape chars
        return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", s)

    # Match JSON string literals (handling escaped quotes inside)
    return re.sub(r'"(?:[^"\\]|\\.)*"', _fix_in_string, text)


def fix_backslashes_aggressive(text: str) -> str:
    r"""Aggressively double ALL single backslashes in JSON strings.

    Used as a last resort when conservative fix_backslashes still fails
    (e.g., \f in '\file.cs' is a valid JSON escape but wrong in context).
    """
    def _fix_in_string(match: re.Match) -> str:
        s = match.group(0)
        # Double every single backslash (but not already-doubled ones)
        return re.sub(r'(?<!\\)\\(?!\\)', r"\\\\", s)

    return re.sub(r'"(?:[^"\\]|\\.)*"', _fix_in_string, text)


def extract_json_object(text: str, search_start: int = 0) -> str | None:
    """Extract the outermost JSON object from mixed text via brace-matching.

    Conductor output often has non-JSON preamble (banners, logs) and
    sometimes postamble. This finds the first '{' at or after search_start
    and its matching '}'.
    """
    start = text.find("{", search_start)
    if start == -1:
        return None

    # Track brace depth to find matching '}'
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        c = text[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            if in_string:
                escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def parse_phase_output(raw: str) -> dict:
    """Parse Conductor phase output into a dict, handling edge cases.

    Tries multiple strategies:
    1. Direct JSON parse (clean output)
    2. Strip ANSI codes, then parse
    3. Extract JSON object from mixed output
    4. Aggressively fix backslashes (doubles ALL), then parse
    """
    if not raw or not raw.strip():
        raise ValueError("Empty input — no phase output to merge")

    text = raw.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip ANSI codes
    cleaned = strip_ansi(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 3: Extract JSON object from mixed output.
    # Conductor TUI adds box-drawing around workflow inputs ({...│...│}),
    # so the first brace-matched block may not be valid JSON. Loop through
    # candidates until one parses.
    search_start = 0
    last_extracted = None
    while True:
        extracted = extract_json_object(cleaned, search_start)
        if not extracted:
            break
        last_extracted = extracted
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

        # Strategy 4a: Conservative backslash fix (preserves valid JSON escapes).
        fixed_conservative = fix_backslashes(extracted)
        try:
            return json.loads(fixed_conservative)
        except json.JSONDecodeError:
            pass

        # Strategy 4b: Aggressive backslash fix (last resort — may alter valid escapes).
        fixed = fix_backslashes_aggressive(extracted)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # Move past this candidate's opening brace
        search_start = cleaned.index(extracted, search_start) + 1

    if last_extracted:
        raise ValueError(
            f"Found JSON-like block(s) but none parsed successfully. "
            f"Last candidate ({len(last_extracted)} chars).\n"
            f"First 200 chars: {last_extracted[:200]}"
        )

    raise ValueError(
        f"No JSON object found in input ({len(text)} chars).\n"
        f"First 200 chars: {text[:200]}"
    )


def deep_merge(base: dict, updates: dict) -> dict:
    """Deep-merge updates into base. Updates overwrite base for scalar values.
    Nested dicts are merged recursively. Lists are replaced (not appended).
    """
    result = base.copy()
    for key, value in updates.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def read_state_file(path: Path) -> dict:
    """Read existing state file, returning {} if missing or corrupt."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {}
        return json.loads(text)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: corrupt state file, starting fresh: {e}", file=sys.stderr)
        return {}


def write_state_file(path: Path, state: dict) -> None:
    """Write state file atomically (write to .tmp, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
    except OSError:
        # Fallback: direct write if rename fails
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def _known_phase_ids() -> list[str]:
    phase_ids: list[str] = []
    for source in (PHASE_SCHEMAS, PHASE_ALIASES):
        for phase_id in source:
            if phase_id not in phase_ids:
                phase_ids.append(phase_id)
    return phase_ids


def _phase_candidate_keys(phase_id: str) -> list[str]:
    schema = PHASE_SCHEMAS.get(phase_id, {})
    aliases = PHASE_ALIASES.get(phase_id, {})
    keys: list[str] = []
    for key in schema.get("required", []):
        if key not in keys:
            keys.append(key)
    for key in schema.get("optional", []):
        if key not in keys:
            keys.append(key)
    for key in aliases:
        if key not in keys:
            keys.append(key)
    return keys


def migrate_flat_state_to_phase_namespace(state: dict) -> tuple[dict, list[str]]:
    """Project legacy flat state keys into _phases on first load."""
    if not isinstance(state, dict):
        return {}, []

    phases = state.get("_phases")
    existing_phases = dict(phases) if isinstance(phases, dict) else {}
    migrated_phases = dict(existing_phases)
    touched_phase_ids: set[str] = set()

    for phase_id in _known_phase_ids():
        flat_phase = normalize_phase_output(
            phase_id,
            {key: state[key] for key in _phase_candidate_keys(phase_id) if key in state},
        )
        existing_phase = existing_phases.get(phase_id)
        if not isinstance(existing_phase, dict):
            existing_phase = {}

        if existing_phase and not flat_phase:
            continue
        if flat_phase:
            touched_phase_ids.add(phase_id)
            migrated_phases[phase_id] = deep_merge(existing_phase, flat_phase)
        elif existing_phase:
            migrated_phases[phase_id] = normalize_phase_output(phase_id, existing_phase)

    if not touched_phase_ids and existing_phases:
        return state, []
    if not migrated_phases:
        return state, []

    migrated_state = dict(state)
    for phase_id in touched_phase_ids:
        for key in _phase_candidate_keys(phase_id):
            migrated_state.pop(key, None)
    migrated_state["_phases"] = migrated_phases
    return migrated_state, sorted(touched_phase_ids or migrated_phases)


def extract_from_event_log(glob_pattern: str) -> dict:
    """Extract workflow output from Conductor event log (most reliable method).

    Conductor writes structured JSONL events to $TEMP/conductor/*.events.jsonl
    when run with --log-file auto. The workflow_completed event contains the
    clean output dict — no TUI decoration, no encoding issues.
    """
    import glob as globmod

    files = sorted(globmod.glob(glob_pattern), key=os.path.getmtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No event log matches: {glob_pattern}")

    log_path = files[0]  # Most recent match
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "workflow_completed":
                output = ev.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    return output
                raise ValueError(
                    f"workflow_completed output is {type(output).__name__}, expected dict"
                )

    raise ValueError(f"No workflow_completed event in {log_path}")


def main():
    # Force UTF-8 for stdout/stderr on Windows (default cp1252 crashes on Unicode)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Merge Conductor phase output into cross-phase state file."
    )
    parser.add_argument(
        "--output-file",
        help="Path to file containing Conductor stdout (legacy). Prefer --event-log.",
    )
    parser.add_argument(
        "--event-log",
        help="Glob pattern to find Conductor event log (e.g., "
        "'$TEMP/conductor/conductor-phase1a-*.events.jsonl'). "
        "Extracts output from the workflow_completed event — most reliable.",
    )
    parser.add_argument(
        "--state-file",
        required=True,
        help="Path to the cross-phase state file.",
    )
    parser.add_argument(
        "--phase",
        default="unknown",
        help="Phase name for logging (e.g., '1a', '3', '5').",
    )
    parser.add_argument(
        "--clear-keys",
        nargs="*",
        default=[],
        help="State keys to delete before merging (removes stale entries from prior runs).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be merged without writing.",
    )
    args = parser.parse_args()

    # Read phase output — prefer event log (clean), fall back to output file / stdin
    try:
        if args.event_log:
            phase_data = extract_from_event_log(args.event_log)
        elif args.output_file:
            raw = Path(args.output_file).read_text(encoding="utf-8", errors="replace")
            phase_data = parse_phase_output(raw)
        else:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
            raw = sys.stdin.read()
            phase_data = parse_phase_output(raw)
    except (OSError, FileNotFoundError) as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error parsing phase {args.phase} output: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(phase_data, dict):
        print(
            f"Error: phase {args.phase} output is {type(phase_data).__name__}, expected dict",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read existing state
    state_path = Path(args.state_file)
    existing_state = read_state_file(state_path)
    existing_state, migrated_phase_ids = migrate_flat_state_to_phase_namespace(existing_state)

    normalized_phase_data = normalize_phase_output(args.phase, phase_data)

    # Apply typed model coercion if available (defense-in-depth over normalize).
    # Merge coerced fields back into normalized data so unknown keys survive.
    model_cls = PHASE_MODELS.get(args.phase)
    if model_cls:
        try:
            model = model_cls.from_raw(normalized_phase_data)
            normalized_phase_data.update(model.to_dict())
        except (ValueError, TypeError) as exc:
            print(f"WARNING: model coercion failed for phase {args.phase}: {exc}", file=sys.stderr)

    merged = deep_merge(existing_state, {})

    phases = merged.get("_phases", {})
    if not isinstance(phases, dict):
        phases = {}
    existing_phase = phases.get(args.phase, {}) if isinstance(phases.get(args.phase), dict) else {}

    new_keys = [k for k in normalized_phase_data if k not in existing_phase and not k.startswith("_")]
    updated_keys = [k for k in normalized_phase_data if k in existing_phase and not k.startswith("_")]
    phases[args.phase] = deep_merge(existing_phase, normalized_phase_data)
    merged["_phases"] = phases

    # Clear stale keys only after successful merge (prevents data loss on merge failure)
    cleared_keys = []
    merged_phase = phases[args.phase]
    for key in args.clear_keys:
        cleared = False
        if isinstance(merged_phase, dict) and key in merged_phase:
            del merged_phase[key]
            cleared = True
        if key in merged:
            del merged[key]
            cleared = True
        if cleared:
            cleared_keys.append(key)

    merged_phase_data = phases.get(args.phase, {})
    is_valid, validation_warnings = validate_phase_output(args.phase, merged_phase_data)
    if validation_warnings:
        for warning in validation_warnings:
            print(
                f"Warning: phase {args.phase} validation: {warning}",
                file=sys.stderr,
            )

    phase_validation_errors = merged.get("_phase_validation_errors", {})
    if not isinstance(phase_validation_errors, dict):
        phase_validation_errors = {}
    if is_valid:
        phase_validation_errors.pop(args.phase, None)
    else:
        phase_validation_errors[args.phase] = validation_warnings
    if phase_validation_errors:
        merged["_phase_validation_errors"] = phase_validation_errors
    else:
        merged.pop("_phase_validation_errors", None)

    # Add merge metadata
    merged["_last_merged_phase"] = args.phase
    merged["_last_merged_at"] = datetime.now(timezone.utc).isoformat()
    merge_log = merged.get("_merge_log", [])
    merge_log.append({
        "phase": args.phase,
        "keys_added": new_keys,
        "keys_updated": updated_keys,
        "keys_cleared": cleared_keys,
        "migrated_phases": migrated_phase_ids,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    merged["_merge_log"] = merge_log

    phase_key_total = len([k for k in merged_phase_data if not str(k).startswith("_")])

    if args.dry_run:
        migration_msg = f", migrated {len(migrated_phase_ids)} phase(s)" if migrated_phase_ids else ""
        print(
            f"[dry-run] Phase {args.phase}: would add {len(new_keys)} keys, "
            f"update {len(updated_keys)} keys{migration_msg} (phase keys: {phase_key_total})"
        )
        print(json.dumps(merged, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Write merged state
    write_state_file(state_path, merged)

    cleared_msg = f", -{len(cleared_keys)} cleared" if cleared_keys else ""
    migrated_msg = f", migrated {len(migrated_phase_ids)} phase(s)" if migrated_phase_ids else ""
    summary = (
        f"Merged phase {args.phase}: "
        f"+{len(new_keys)} new, ~{len(updated_keys)} updated{cleared_msg}{migrated_msg} "
        f"(phase: {phase_key_total} keys)"
    )
    print(summary)


if __name__ == "__main__":
    main()
