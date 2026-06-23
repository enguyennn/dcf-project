#!/usr/bin/env python3
"""
resolve_knowledge_docs.py — Deterministic resolver for knowledge-context skill documents.

Parses SKILL.md routing tables, matches changed files against path patterns,
and outputs pre-resolved child document paths for the Gatekeeper reviewer.

Usage:
    python resolve_knowledge_docs.py --skills-dir <path> --changed-files '<json_array>'
    python resolve_knowledge_docs.py --skills-dir <path> --changed-files-file <path_to_json_file>

Output (JSON to stdout):
    {
      "skill_name": {
        "type": "knowledge-context" | "knowledge-context-routed",
        "skill_dir": "/abs/path/to/skill",
        "resolved_docs": ["/abs/path/to/SKILL.md", ...],
        "matches": [
          {"changed_file": "src/Foo.cs", "pattern": "Foo", "area_code": "[EXT]", "doc": "domain/vm-extensions.md"}
        ]
      }
    }
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


KNOWN_FORMATS = {"knowledge-context", "knowledge-context-routed"}


def _parse_frontmatter(skill_md_path: Path) -> dict[str, Any]:
    """Parse YAML frontmatter from a SKILL.md file. Returns empty dict on failure."""
    text = skill_md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm_text = text[3:end].strip()

    # Lightweight YAML parser for the fields we need (avoids PyYAML dependency)
    result: dict[str, Any] = {}
    current_key = ""
    for line in fm_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level key
        top_match = re.match(r'^(\w[\w-]*):\s*(.*)', line)
        if top_match and not line.startswith(" "):
            current_key = top_match.group(1)
            val = top_match.group(2).strip().strip('"').strip("'")
            result[current_key] = val if val else {}
            continue

        # Nested key under metadata
        nested_match = re.match(r'^\s+(\w[\w-]*):\s*(.*)', line)
        if nested_match and current_key == "metadata":
            if not isinstance(result.get("metadata"), dict):
                result["metadata"] = {}
            k = nested_match.group(1)
            v = nested_match.group(2).strip().strip('"').strip("'")
            result["metadata"][k] = v
            continue

        # List item under metadata key
        list_match = re.match(r'^\s+-\s+"?([^"]*)"?\s*$', line)
        if list_match and current_key == "metadata":
            pass  # We don't need list values for our purposes

    return result


def _parse_markdown_table(text: str, header_pattern: list[str]) -> list[dict[str, str]]:
    """
    Parse a markdown pipe table whose column headers match the given patterns.
    Returns list of dicts keyed by header name.

    Uses column header matching (not section titles) for robustness.
    header_pattern: list of regex patterns to match column headers (case-insensitive).
    """
    lines = text.split("\n")
    rows: list[dict[str, str]] = []
    headers: list[str] = []
    in_table = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Look for header row matching our pattern
        if not in_table and stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) >= len(header_pattern):
                matched = all(
                    re.search(pat, cells[j], re.IGNORECASE)
                    for j, pat in enumerate(header_pattern)
                )
                if matched:
                    # Check next line is separator
                    if i + 1 < len(lines) and re.match(r'^\s*\|[\s\-:|]+\|', lines[i + 1]):
                        headers = cells
                        in_table = True
                        continue

        # Skip separator row
        if in_table and re.match(r'^\s*\|[\s\-:|]+\|', stripped):
            continue

        # Parse data rows
        if in_table:
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                if len(cells) >= len(headers):
                    row = {headers[j]: cells[j] for j in range(len(headers))}
                    rows.append(row)
            elif stripped == "":
                # Blank line — could be a gap in the table, keep looking for more rows
                continue
            else:
                # Non-table content — table ended
                in_table = False

    return rows


def _extract_path_patterns(cell: str) -> list[str]:
    """Extract path pattern substrings from a table cell like '`VMExt/`, `ExtensionBuilder`'."""
    patterns = re.findall(r'`([^`]+)`', cell)
    if not patterns:
        # Fallback: split on comma
        patterns = [p.strip() for p in cell.split(",") if p.strip()]
    return patterns


def _extract_area_codes(cell: str) -> list[str]:
    """Extract area codes like [EXT], [PATCH] from a table cell."""
    return re.findall(r'\[([A-Z0-9]+)\]', cell)


def _normalize_path(p: str) -> str:
    """Normalize a file path to POSIX-style lowercase for matching."""
    return p.replace("\\", "/").lower()


def _file_matches_pattern(file_path_normalized: str, pattern: str) -> bool:
    """
    Check if a normalized file path matches a pattern using segment-aware substring matching.
    Pattern is normalized to lowercase POSIX.
    """
    pat = _normalize_path(pattern)
    # Remove backticks if present
    pat = pat.strip("`")
    # If pattern ends with /, it's a directory prefix — match as path segment
    if pat.endswith("/"):
        return pat in file_path_normalized
    # Otherwise match as a path segment boundary or substring within a segment
    return pat in file_path_normalized


def _resolve_child_doc_path(ref_path: str, skill_dir: Path) -> Path | None:
    """
    Resolve a child doc reference to an actual file path.
    References in SKILL.md may use .github/skills/<skill>/ prefixes — strip those.
    Only allow paths that resolve within the skill directory.
    """
    ref = ref_path.strip().strip("`")
    posix_ref = ref.replace("\\", "/")

    # Strip common installation-target prefixes
    prefixes_to_strip = [
        ".github/skills/",
        ".github/copilot/skills/",
    ]
    for prefix in prefixes_to_strip:
        idx = posix_ref.find(prefix)
        if idx != -1:
            # Extract the part after the prefix and skill name
            after_prefix = posix_ref[idx + len(prefix):]
            # Skip the skill directory name (first segment)
            parts = after_prefix.split("/", 1)
            if len(parts) > 1:
                posix_ref = parts[1]
            break

    candidate = (skill_dir / posix_ref).resolve()

    # Confinement check: must be within skill_dir
    try:
        candidate.relative_to(skill_dir.resolve())
    except ValueError:
        print(f"WARNING: Child doc path escapes skill directory: {ref_path} -> {candidate}", file=sys.stderr)
        return None

    if not candidate.is_file():
        # Try case-insensitive fallback
        parent = candidate.parent
        if parent.is_dir():
            target_name = candidate.name.lower()
            for f in parent.iterdir():
                if f.name.lower() == target_name and f.is_file():
                    return f
        print(f"WARNING: Child doc not found: {candidate}", file=sys.stderr)
        return None

    return candidate


def _resolve_feature_areas(skill_md_text: str, skill_dir: Path, changed_files: list[str]) -> dict:
    """Resolve crp-feature-areas style routing (two-step: path→area→doc)."""
    # Step 1: Parse Feature Area Detection table (Path Pattern → Area Code)
    area_table = _parse_markdown_table(
        skill_md_text,
        [r"path\s*pattern", r"feature\s*area", r"domain\s*section"]
    )

    # Build pattern → area_codes mapping
    pattern_to_areas: list[tuple[str, list[str]]] = []
    for row in area_table:
        col_pattern = list(row.values())[0]
        col_area_code = list(row.values())[2]
        patterns = _extract_path_patterns(col_pattern)
        area_codes = _extract_area_codes(col_area_code)
        if area_codes:
            for pat in patterns:
                pattern_to_areas.append((pat, area_codes))

    # Step 2: Parse Per-Area Domain Knowledge table (Area Code → Doc File)
    doc_table = _parse_markdown_table(
        skill_md_text,
        [r"domain\s*file", r"areas?\s*covered"]
    )

    # Build area_code → doc_path mapping
    area_to_doc: dict[str, str] = {}
    for row in doc_table:
        doc_ref = list(row.values())[0]
        areas_cell = list(row.values())[1]
        for code in _extract_area_codes(areas_cell):
            area_to_doc[code] = doc_ref

    # Step 3: Match changed files
    matched_areas: set[str] = set()
    matches: list[dict] = []
    for cf in changed_files:
        cf_norm = _normalize_path(cf)
        for pat, area_codes in pattern_to_areas:
            if _file_matches_pattern(cf_norm, pat):
                for code in area_codes:
                    if code not in matched_areas:
                        matched_areas.add(code)
                    doc_ref = area_to_doc.get(code, "")
                    if doc_ref:
                        matches.append({
                            "changed_file": cf,
                            "pattern": pat,
                            "area_code": f"[{code}]",
                            "doc": doc_ref
                        })

    # Step 4: Resolve unique child doc paths
    resolved_docs: list[str] = [str(skill_dir / "SKILL.md")]
    seen_docs: set[str] = set()
    for code in sorted(matched_areas):
        doc_ref = area_to_doc.get(code)
        if doc_ref:
            resolved = _resolve_child_doc_path(doc_ref, skill_dir)
            if resolved and str(resolved) not in seen_docs:
                seen_docs.add(str(resolved))
                resolved_docs.append(str(resolved))

    return {"resolved_docs": resolved_docs, "matches": matches}


def _resolve_component_profiles(skill_md_text: str, skill_dir: Path, changed_files: list[str]) -> dict:
    """Resolve crp-system-knowledge style routing (one-step: component→doc)."""
    # Parse Component Profiles table
    comp_table = _parse_markdown_table(
        skill_md_text,
        [r"profile\s*file", r"components?"]
    )

    # Build component_name → doc_path mapping
    component_to_doc: list[tuple[str, str]] = []
    for row in comp_table:
        doc_ref = list(row.values())[0]
        components_cell = list(row.values())[1]
        components = [c.strip() for c in components_cell.split(",") if c.strip()]
        for comp in components:
            component_to_doc.append((comp, doc_ref))

    # Match changed files against component names
    matches: list[dict] = []
    matched_docs: set[str] = set()
    for cf in changed_files:
        cf_norm = _normalize_path(cf)
        for comp, doc_ref in component_to_doc:
            if _file_matches_pattern(cf_norm, comp):
                matched_docs.add(doc_ref)
                matches.append({
                    "changed_file": cf,
                    "pattern": comp,
                    "area_code": "",
                    "doc": doc_ref
                })

    # Resolve unique child doc paths
    resolved_docs: list[str] = [str(skill_dir / "SKILL.md")]
    seen: set[str] = set()
    for doc_ref in sorted(matched_docs):
        resolved = _resolve_child_doc_path(doc_ref, skill_dir)
        if resolved and str(resolved) not in seen:
            seen.add(str(resolved))
            resolved_docs.append(str(resolved))

    return {"resolved_docs": resolved_docs, "matches": matches}


def _resolve_generic_routed(skill_md_text: str, skill_dir: Path, changed_files: list[str]) -> dict:
    """
    Generic fallback for knowledge-context-routed skills that don't match known patterns.
    Tries feature-area-style first, then component-profile-style.
    If neither works, loads all child .md files.
    """
    # Try feature-area style
    result = _resolve_feature_areas(skill_md_text, skill_dir, changed_files)
    if len(result["resolved_docs"]) > 1:
        return result

    # Try component-profile style
    result = _resolve_component_profiles(skill_md_text, skill_dir, changed_files)
    if len(result["resolved_docs"]) > 1:
        return result

    # Fallback: load all .md files in subdirectories
    resolved_docs = [str(skill_dir / "SKILL.md")]
    for md_file in sorted(skill_dir.rglob("*.md")):
        if md_file.name != "SKILL.md":
            resolved_docs.append(str(md_file))
    return {"resolved_docs": resolved_docs, "matches": []}


def resolve_skills(skills_dir: Path, changed_files: list[str]) -> dict[str, Any]:
    """
    Resolve knowledge-context skills in the given directory.
    Returns a mapping of skill_name → resolution info.
    """
    results: dict[str, Any] = {}

    if not skills_dir.is_dir():
        print(f"ERROR: Skills directory not found: {skills_dir}", file=sys.stderr)
        return results

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue

        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            continue

        fm = _parse_frontmatter(skill_md)
        metadata = fm.get("metadata", {})

        # Determine format — check metadata.format first, then infer from structure
        fmt = ""
        if isinstance(metadata, dict):
            fmt = metadata.get("format", "")

        # If no format field but no metadata block at all, treat as knowledge-context
        if not fmt and not metadata:
            if fm.get("name") and fm.get("description"):
                fmt = "knowledge-context"

        # Skip if not a knowledge-context format
        if fmt not in KNOWN_FORMATS:
            continue

        skill_name = entry.name
        skill_text = skill_md.read_text(encoding="utf-8")

        if fmt == "knowledge-context":
            results[skill_name] = {
                "type": fmt,
                "skill_dir": str(entry),
                "resolved_docs": [str(skill_md)],
                "matches": []
            }
        elif fmt == "knowledge-context-routed":
            resolution = _resolve_generic_routed(skill_text, entry, changed_files)
            results[skill_name] = {
                "type": fmt,
                "skill_dir": str(entry),
                "resolved_docs": resolution["resolved_docs"],
                "matches": resolution["matches"]
            }

    return results


def main():
    parser = argparse.ArgumentParser(description="Resolve knowledge-context skill documents")
    parser.add_argument("--skills-dir", required=True, help="Path to skills directory")
    parser.add_argument("--changed-files", help="JSON array of changed file paths")
    parser.add_argument("--changed-files-file", help="Path to JSON file containing changed file paths")
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir).resolve()

    if args.changed_files_file:
        changed_files = json.loads(Path(args.changed_files_file).read_text(encoding="utf-8"))
    elif args.changed_files:
        changed_files = json.loads(args.changed_files)
    else:
        changed_files = []

    if not isinstance(changed_files, list):
        print("ERROR: changed-files must be a JSON array", file=sys.stderr)
        sys.exit(1)

    results = resolve_skills(skills_dir, changed_files)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
