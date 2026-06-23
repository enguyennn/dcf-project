#!/usr/bin/env python3
"""Extract filter specs from guideline SKILL.md frontmatter.

Deterministic replacement for the LLM-based GatekeeperFilter agent's
frontmatter extraction.  Reads every guideline skill directory under
``--skills-dir``, parses its SKILL.md YAML frontmatter, and outputs a
JSON object mapping guideline names to ``{glob_patterns, content_regex}``.

Usage:
    python extract_filters.py --skills-dir <path> [--output <path>]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YAML frontmatter parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> Optional[Dict[str, Any]]:
    """Extract YAML frontmatter from a SKILL.md file.

    Tries PyYAML first, falls back to a narrow hand-rolled parser that
    only extracts the fields we care about (name, metadata.type,
    metadata.scope, metadata.content_regex, metadata.severity,
    metadata.category).
    """
    lines = text.splitlines()

    # Find frontmatter delimiters
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None

    fm_text = "\n".join(lines[1:end])

    # Try PyYAML
    try:
        import yaml  # noqa: F811

        return yaml.safe_load(fm_text) or {}
    except ImportError:
        pass

    # Narrow fallback parser
    return _parse_frontmatter_narrow(fm_text)


def _parse_frontmatter_narrow(text: str) -> Dict[str, Any]:
    """Minimal parser for the specific SKILL.md frontmatter structure.

    Handles the nested ``metadata:`` block with ``type``, ``severity``,
    ``category``, ``scope`` (list), and ``content_regex`` (list).
    Also extracts top-level ``name`` and ``description``.
    """
    result: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    current_list_key: Optional[str] = None
    current_list: List[str] = []
    in_metadata = False
    in_description = False
    description_lines: List[str] = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())

        # Detect end of multiline description
        if in_description and indent <= 0 and ":" in stripped:
            in_description = False
            result["description"] = " ".join(description_lines).strip()

        if in_description:
            description_lines.append(stripped)
            continue

        # Flush any pending list when we leave its indentation level
        if current_list_key and not stripped.startswith("- "):
            target = metadata if in_metadata else result
            target[current_list_key] = current_list
            current_list_key = None
            current_list = []

        # List items
        if stripped.startswith("- "):
            value = stripped[2:].strip().strip("'\"")
            current_list.append(value)
            continue

        # Key-value pairs
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()

            if key == "metadata":
                in_metadata = True
                continue

            if key == "description" and val in (">", "|", ""):
                in_description = True
                description_lines = []
                if val and val not in (">", "|"):
                    description_lines.append(val)
                continue

            # Detect start of a list on the next line
            if not val:
                current_list_key = key
                current_list = []
                continue

            val = val.strip("'\"")
            if in_metadata and indent >= 2:
                metadata[key] = val
            else:
                if in_metadata and indent < 2:
                    in_metadata = False
                result[key] = val

    # Flush trailing state
    if current_list_key:
        target = metadata if in_metadata else result
        target[current_list_key] = current_list
    if in_description:
        result["description"] = " ".join(description_lines).strip()

    if metadata:
        result["metadata"] = metadata
    return result


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_regex_list(patterns: List[str], guideline: str) -> List[str]:
    """Validate and return compilable regex patterns. Log errors for bad ones."""
    valid: List[str] = []
    for pattern in patterns:
        if not isinstance(pattern, str):
            logger.warning(
                "Guideline '%s': content_regex entry is not a string: %r — skipping",
                guideline, pattern,
            )
            continue
        try:
            re.compile(pattern)
            valid.append(pattern)
        except re.error as exc:
            logger.error(
                "Guideline '%s': invalid content_regex pattern '%s' — %s",
                guideline, pattern, exc,
            )
    return valid


def _dedupe_and_sort(items: List[str]) -> List[str]:
    """Deduplicate and sort a list of strings."""
    return sorted(set(items))


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _extract_one(skill_dir: Path) -> Optional[Dict[str, Any]]:
    """Extract filter spec from a single SKILL.md file.

    Returns a dict with ``glob_patterns`` and ``content_regex``, or
    ``None`` if the file is not a valid guideline skill.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None

    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read %s: %s", skill_md, exc)
        return None

    fm = _parse_frontmatter(text)
    if fm is None:
        logger.warning("No YAML frontmatter in %s — skipping", skill_md)
        return None

    metadata = fm.get("metadata", {})
    if not isinstance(metadata, dict):
        logger.warning("Invalid metadata in %s — skipping", skill_md)
        return None

    # Only process guideline skills
    skill_type = metadata.get("type", "")
    if skill_type != "guideline":
        logger.debug("Skipping non-guideline skill '%s' (type=%s)", skill_dir.name, skill_type)
        return None

    # Extract scope → glob_patterns
    scope = metadata.get("scope", [])
    if not isinstance(scope, list):
        logger.error("Guideline '%s': metadata.scope is not a list", skill_dir.name)
        return None
    glob_patterns = [s for s in scope if isinstance(s, str) and s]
    if not glob_patterns:
        logger.error("Guideline '%s': metadata.scope is empty", skill_dir.name)
        return None

    # Extract content_regex (optional)
    raw_regex = metadata.get("content_regex", [])
    if not isinstance(raw_regex, list):
        logger.warning(
            "Guideline '%s': metadata.content_regex is not a list — ignoring",
            skill_dir.name,
        )
        raw_regex = []
    content_regex = _validate_regex_list(raw_regex, skill_dir.name)

    # Validate frontmatter name matches directory name
    fm_name = fm.get("name", "")
    if fm_name and fm_name != skill_dir.name:
        logger.warning(
            "Guideline '%s': frontmatter name '%s' does not match directory name",
            skill_dir.name, fm_name,
        )

    return {
        "glob_patterns": _dedupe_and_sort(glob_patterns),
        "content_regex": _dedupe_and_sort(content_regex),
    }


def extract_all(skills_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Extract filter specs from all guideline skills in a directory.

    Returns a dict keyed by guideline directory name.
    """
    if not skills_dir.is_dir():
        raise FileNotFoundError(f"Skills directory not found: {skills_dir}")

    results: Dict[str, Dict[str, Any]] = {}
    errors = 0

    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        spec = _extract_one(child)
        if spec is not None:
            results[child.name] = spec
        elif (child / "SKILL.md").is_file():
            # SKILL.md exists but was skipped (non-guideline or error)
            pass

    logger.info(
        "Extracted filters for %d guidelines from %s",
        len(results), skills_dir,
    )
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract filter specs from guideline SKILL.md frontmatter.",
    )
    parser.add_argument(
        "--skills-dir",
        required=True,
        help="Directory containing guideline skill subdirectories with SKILL.md files.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path. If omitted, prints to stdout.",
    )
    args = parser.parse_args()

    try:
        results = extract_all(Path(args.skills_dir))
    except (FileNotFoundError, OSError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    output_json = json.dumps(results, indent=2, sort_keys=True)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json + "\n", encoding="utf-8")
        logger.info("Wrote filter output to %s", out_path)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
