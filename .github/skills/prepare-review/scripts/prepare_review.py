#!/usr/bin/env python3
"""Prepare review items for the Gatekeeper code review pipeline.

Consolidates config parsing, guideline discovery, change discovery,
filter extraction, and file-to-guideline matching into a single
deterministic script.  Outputs a JSON object that the orchestrator
inserts directly into the session SQL database.

Usage:
    python prepare_review.py --output-dir <dir> --mode file|diff \
        [--config <gkpconfig.yml>] [--commit-range <range>] \
        [--staged] [--untracked] [--repo-path .] [--output <path>]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YAML frontmatter parsing  (from extract_filters.py)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> Optional[Dict[str, Any]]:
    """Extract YAML frontmatter from a SKILL.md file.

    Tries PyYAML first, falls back to a narrow hand-rolled parser that
    only extracts the fields we care about.
    """
    lines = text.splitlines()

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

    try:
        import yaml  # noqa: F811
        return yaml.safe_load(fm_text) or {}
    except ImportError:
        pass

    return _parse_frontmatter_narrow(fm_text)


def _parse_frontmatter_narrow(text: str) -> Dict[str, Any]:
    """Minimal parser for the specific SKILL.md frontmatter structure."""
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

        if in_description and indent <= 0 and ":" in stripped:
            in_description = False
            result["description"] = " ".join(description_lines).strip()

        if in_description:
            description_lines.append(stripped)
            continue

        if current_list_key and not stripped.startswith("- "):
            target = metadata if in_metadata else result
            target[current_list_key] = current_list
            current_list_key = None
            current_list = []

        if stripped.startswith("- "):
            value = stripped[2:].strip().strip("'\"")
            current_list.append(value)
            continue

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

    if current_list_key:
        target = metadata if in_metadata else result
        target[current_list_key] = current_list
    if in_description:
        result["description"] = " ".join(description_lines).strip()

    if metadata:
        result["metadata"] = metadata
    return result


# ---------------------------------------------------------------------------
# Config auto-discovery and parsing  (adapted from parse_config.py)
# ---------------------------------------------------------------------------

def _parse_yaml(text: str) -> dict:
    """Parse YAML text using PyYAML or fallback."""
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        pass

    # Minimal fallback for gkpconfig.yml structure
    result: dict = {}
    current_key = None
    current_list_key: Optional[str] = None
    indent_stack: list = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        while indent_stack and indent <= indent_stack[-1][0]:
            indent_stack.pop()

        if stripped.startswith("- "):
            value = stripped[2:].strip().strip("'\"")
            if current_list_key:
                target = indent_stack[-1][1] if indent_stack else result
                if current_list_key not in target:
                    target[current_list_key] = []
                target[current_list_key].append(value)
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip().strip("'\"")
            val = val.strip().strip("'\"")

            if val:
                target = indent_stack[-1][1] if indent_stack else result
                target[key] = val
                current_list_key = None
            else:
                target = indent_stack[-1][1] if indent_stack else result
                nested: dict = {}
                target[key] = nested
                indent_stack.append((indent, nested))
                current_key = key
                current_list_key = None

        if stripped.endswith(":") and not stripped.startswith("- "):
            key = stripped[:-1].strip().strip("'\"")
            current_list_key = key

    return result


def _discover_config(start_path: Path) -> Optional[Path]:
    """Walk up from *start_path* looking for ``.github/gatekeeper/gkpconfig.yml``
    (preferred) or ``.github/gkpconfig.yml`` (legacy fallback)."""
    current = start_path.resolve()
    while True:
        # Preferred: .github/gatekeeper/gkpconfig.yml
        candidate = current / ".github" / "gatekeeper" / "gkpconfig.yml"
        if candidate.is_file():
            return candidate
        # Legacy fallback: .github/gkpconfig.yml
        legacy = current / ".github" / "gkpconfig.yml"
        if legacy.is_file():
            return legacy
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _parse_config(config_path: Path) -> dict:
    """Parse gkpconfig.yml and return raw config dict."""
    text = config_path.read_text(encoding="utf-8")
    return _parse_yaml(text)


def _resolve_config(config: dict, config_path: Path, repo_path_override: Optional[str]) -> dict:
    """Resolve paths in config relative to config file directory.

    Returns an enriched dict with resolved ``repo_root``, ``reviewers``,
    and validation results.
    """
    config_dir = config_path.parent
    errors: List[str] = []
    warnings: List[str] = []

    repo_root = repo_path_override or config.get("repo_root", ".")

    # Resolve repo_root relative to config directory
    if repo_root and not os.path.isabs(repo_root):
        repo_root = str((config_dir / repo_root).resolve())

    if repo_root and not os.path.isdir(repo_root):
        warnings.append(f"repo_root directory not found: {repo_root}")

    # Parse reviewers config (canonical) or normalize from legacy fields
    raw_reviewers = config.get("reviewers", {})

    # Legacy normalization: top-level skills_root → guidelines_reviewer
    if not raw_reviewers:
        legacy_skills_root = config.get("skills_root")
        if legacy_skills_root:
            legacy_folder_rules = config.get("folder_rules", {})
            # Legacy skills_root is relative to repo_root, not config dir.
            # Resolve it to absolute so the canonical resolver doesn't
            # re-resolve it relative to config_dir.
            if not os.path.isabs(legacy_skills_root) and repo_root:
                legacy_skills_root = str(
                    (Path(repo_root) / legacy_skills_root).resolve()
                )
            raw_reviewers = {
                "guidelines_reviewer": {
                    "guidelines_root": legacy_skills_root,
                    "folder_rules": legacy_folder_rules,
                },
            }
            warnings.append(
                "Using legacy top-level skills_root/folder_rules config. "
                "Migrate to canonical reviewers.guidelines_reviewer format."
            )
        else:
            errors.append("reviewers section is required in config")

    resolved_reviewers: Dict[str, Dict[str, Any]] = {}
    has_guidelines_reviewer = False

    for reviewer_name, reviewer_cfg in raw_reviewers.items():
        if not isinstance(reviewer_cfg, dict):
            reviewer_cfg = {}

        entry: Dict[str, Any] = {
            "model": reviewer_cfg.get("model", "default"),
        }

        if reviewer_name == "guidelines_reviewer":
            has_guidelines_reviewer = True
            guidelines_root = reviewer_cfg.get("guidelines_root")
            if not guidelines_root:
                errors.append(
                    "guidelines_reviewer requires guidelines_root"
                )
            else:
                if not os.path.isabs(guidelines_root):
                    guidelines_root = str(
                        (config_dir / guidelines_root).resolve()
                    )
                if not os.path.isdir(guidelines_root):
                    errors.append(
                        f"guidelines_root directory not found: "
                        f"{guidelines_root}"
                    )
            entry["guidelines_root"] = guidelines_root
            entry["folder_rules"] = reviewer_cfg.get("folder_rules", {})
            entry["type"] = "guidelines"
        else:
            entry["type"] = "specialist"

        resolved_reviewers[reviewer_name] = entry

    return {
        "config_path": str(config_path.resolve()),
        "repo_root": repo_root,
        "reviewers": resolved_reviewers,
        "errors": errors,
        "warnings": warnings,
        "valid": len(errors) == 0,
    }


# ---------------------------------------------------------------------------
# Regex and pattern helpers  (from extract_filters.py)
# ---------------------------------------------------------------------------

def _validate_regex_list(patterns: List[str], guideline: str) -> List[str]:
    """Validate and return compilable regex patterns."""
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
# Guideline discovery  (adapted from extract_filters.py)
# ---------------------------------------------------------------------------

def _extract_guideline(skill_dir: Path) -> Optional[Dict[str, Any]]:
    """Extract guideline metadata from a single SKILL.md file.

    Returns a dict with ``rel_path``, ``glob_patterns``, and
    ``content_regex``, or ``None`` if not a valid guideline skill.
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

    if metadata.get("type", "") != "guideline":
        logger.debug("Skipping non-guideline skill '%s' (type=%s)",
                      skill_dir.name, metadata.get("type", ""))
        return None

    scope = metadata.get("scope", [])
    if not isinstance(scope, list):
        logger.error("Guideline '%s': metadata.scope is not a list", skill_dir.name)
        return None
    glob_patterns = [s for s in scope if isinstance(s, str) and s]
    if not glob_patterns:
        logger.error("Guideline '%s': metadata.scope is empty", skill_dir.name)
        return None

    raw_regex = metadata.get("content_regex", [])
    if not isinstance(raw_regex, list):
        logger.warning(
            "Guideline '%s': metadata.content_regex is not a list — ignoring",
            skill_dir.name,
        )
        raw_regex = []
    content_regex = _validate_regex_list(raw_regex, skill_dir.name)

    fm_name = fm.get("name", "")
    if fm_name and fm_name != skill_dir.name:
        logger.warning(
            "Guideline '%s': frontmatter name '%s' does not match directory name",
            skill_dir.name, fm_name,
        )

    return {
        "name": skill_dir.name,
        "rel_path": f"{skill_dir.name}/SKILL.md",
        "glob_patterns": _dedupe_and_sort(glob_patterns),
        "content_regex": _dedupe_and_sort(content_regex),
    }


def _discover_guidelines(skills_dir: Path) -> List[Dict[str, Any]]:
    """Discover all guideline skills in a directory.

    Returns a list of guideline dicts, sorted by name for determinism.
    """
    if not skills_dir.is_dir():
        raise FileNotFoundError(f"Skills directory not found: {skills_dir}")

    guidelines: List[Dict[str, Any]] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        spec = _extract_guideline(child)
        if spec is not None:
            guidelines.append(spec)

    logger.info("Discovered %d guidelines from %s", len(guidelines), skills_dir)
    return guidelines


# ---------------------------------------------------------------------------
# Folder rules  (new code)
# ---------------------------------------------------------------------------

def _apply_folder_rules(
    filename: str,
    guideline_names: List[str],
    folder_rules: dict,
) -> List[str]:
    """Filter guideline names based on folder_rules for a given filename.

    Folder rules map file glob patterns to guideline selectors.
    For each file, find the most specific matching folder pattern and
    restrict guidelines to those matching the selectors.

    If no folder_rules are configured, all guidelines pass through.
    """
    if not folder_rules:
        return guideline_names

    normalized = filename.replace("\\", "/")

    # Collect all matching folder rules (most specific = longest pattern)
    matching_rules: List[tuple] = []
    for folder_pattern, rule in folder_rules.items():
        if fnmatch(normalized, folder_pattern) or PurePosixPath(normalized).match(folder_pattern):
            matching_rules.append((len(folder_pattern), folder_pattern, rule))

    if not matching_rules:
        return guideline_names

    # Use the most specific (longest) matching rule
    matching_rules.sort(key=lambda x: x[0], reverse=True)
    _, _, rule = matching_rules[0]

    guideline_selectors = rule.get("guidelines", ["**"])
    exclude_patterns = rule.get("exclude", [])

    # Check if the file is excluded
    for exc_pattern in exclude_patterns:
        if fnmatch(normalized, exc_pattern) or PurePosixPath(normalized).match(exc_pattern):
            return []

    # Filter guidelines by selectors
    allowed: List[str] = []
    for gname in guideline_names:
        for selector in guideline_selectors:
            if fnmatch(gname, selector):
                allowed.append(gname)
                break

    return allowed


def _prefilter_guidelines_by_folder_rules(
    guidelines: List[Dict[str, Any]],
    folder_rules: dict,
) -> Dict[str, List[str]]:
    """Pre-compute which guideline names are allowed by each folder rule.

    Returns a mapping: folder_pattern -> list of allowed guideline names.
    Used to narrow the guideline set before file matching.
    """
    if not folder_rules:
        return {}

    all_names = [g["name"] for g in guidelines]
    result: Dict[str, List[str]] = {}

    for folder_pattern, rule in folder_rules.items():
        guideline_selectors = rule.get("guidelines", ["**"])
        allowed: List[str] = []
        for gname in all_names:
            for selector in guideline_selectors:
                if fnmatch(gname, selector):
                    allowed.append(gname)
                    break
        result[folder_pattern] = allowed

    return result


# ---------------------------------------------------------------------------
# Git diff parsing  (new code)
# ---------------------------------------------------------------------------

def _run_git_diff_name_status(
    repo_path: Path,
    commit_range: Optional[str] = None,
    staged: bool = False,
) -> List[Dict[str, str]]:
    """Run ``git diff --name-status`` and return list of changed files.

    Each entry has ``path`` and ``change_type`` (M, A, D, R, etc.).
    """
    cmd = ["git", "diff", "--name-status"]
    if staged:
        cmd.append("--cached")
    if commit_range:
        cmd.append(commit_range)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=60,
        )
        if result.returncode != 0:
            logger.error("git diff --name-status failed: %s", result.stderr.strip())
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.error("git diff --name-status error: %s", exc)
        return []

    changes: List[Dict[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            change_type = parts[0].strip()
            filepath = parts[1].strip()
            # Handle rename: R100\told\tnew — take the new path
            if "\t" in filepath:
                filepath = filepath.split("\t")[-1]
            changes.append({"path": filepath, "change_type": change_type[0]})
        else:
            # Handle single-field lines (shouldn't happen normally)
            logger.warning("Unexpected git diff line: %s", line)

    return changes


def _run_git_diff_unified(
    repo_path: Path,
    commit_range: Optional[str] = None,
    staged: bool = False,
) -> str:
    """Run ``git diff`` and return the full unified diff output."""
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--cached")
    if commit_range:
        cmd.append(commit_range)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("git diff failed: %s", result.stderr.strip())
            return ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.error("git diff error: %s", exc)
        return ""

    return result.stdout


def _split_diff_by_file(diff_text: str) -> Dict[str, str]:
    """Split unified diff output into per-file diff hunks.

    Returns a dict mapping file paths to their diff content.
    Splits on ``diff --git a/... b/...`` headers.
    """
    if not diff_text:
        return {}

    file_diffs: Dict[str, str] = {}
    current_file: Optional[str] = None
    current_lines: List[str] = []
    diff_header_re = re.compile(r"^diff --git a/(.*?) b/(.*?)$")

    for line in diff_text.splitlines(keepends=True):
        match = diff_header_re.match(line.rstrip("\n\r"))
        if match:
            # Save previous file's diff
            if current_file is not None:
                file_diffs[current_file] = "".join(current_lines)
            current_file = match.group(2)  # Use the b/ path (new path)
            current_lines = [line]
        else:
            current_lines.append(line)

    # Save last file
    if current_file is not None:
        file_diffs[current_file] = "".join(current_lines)

    return file_diffs


# ---------------------------------------------------------------------------
# File matching  (adapted from batch_files.py)
# ---------------------------------------------------------------------------

def _find_git_root(start_path: Path) -> Optional[Path]:
    """Detect the git repository root from *start_path*."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=str(start_path),
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    current = start_path.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def _list_repo_files(
    repo_path: Path,
    git_root: Optional[Path] = None,
    repo_root_rel: Optional[str] = None,
) -> Optional[List[str]]:
    """List all tracked files via ``git ls-files``.

    Returns repo-root-relative paths (posix-style), or ``None`` if git
    is not available.  When *repo_path* is a subdirectory of *git_root*,
    only files under *repo_path* are returned and paths are made
    relative to *repo_path*.
    """
    git_cwd = git_root if git_root else repo_path
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            cwd=str(git_cwd),
            timeout=30,
        )
        if result.returncode != 0:
            logger.debug("git ls-files failed: %s", result.stderr.strip())
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("git ls-files error: %s", exc)
        return None

    files: List[str] = []
    prefix = (repo_root_rel.replace("\\", "/").rstrip("/") + "/") if repo_root_rel else ""

    for line in result.stdout.splitlines():
        fp = line.strip().replace("\\", "/")
        if not fp:
            continue
        if prefix:
            if fp.startswith(prefix):
                files.append(fp[len(prefix):])
        else:
            files.append(fp)

    logger.info("git ls-files: %d files in repo scope", len(files))
    return files


def _normalize_pattern(pattern: str, repo_root_rel: Optional[str]) -> str:
    """Strip a redundant repo-root prefix from a glob pattern."""
    if not repo_root_rel:
        return pattern
    prefix = repo_root_rel.replace("\\", "/").rstrip("/") + "/"
    normalized = pattern.replace("\\", "/")
    if normalized.startswith(prefix):
        return normalized[len(prefix):]
    return pattern


def _glob_match_files(repo_path: Path, pattern: str) -> List[str]:
    """Return repo-relative paths matching *pattern* under *repo_path*.

    Fallback for when ``git ls-files`` is unavailable.
    """
    matched: List[str] = []
    try:
        for p in repo_path.glob(pattern):
            if p.is_file():
                try:
                    matched.append(p.relative_to(repo_path).as_posix())
                except ValueError:
                    continue
    except OSError as exc:
        logger.warning("Glob pattern '%s' failed: %s", pattern, exc)
    return matched


def _fnmatch_files(file_list: List[str], pattern: str) -> List[str]:
    """Match *pattern* against a pre-collected *file_list* using fnmatch.

    This is O(N) in the file list per pattern, but avoids the much
    more expensive per-pattern directory walk that ``pathlib.glob`` does.
    """
    matched: List[str] = []
    for fp in file_list:
        if fnmatch(fp, pattern):
            matched.append(fp)
        elif PurePosixPath(fp).match(pattern):
            matched.append(fp)
    return matched


def _content_matches_regex(
    content: str, compiled_regexes: List[re.Pattern[str]]
) -> bool:
    """Return True if *content* matches at least one compiled regex."""
    return any(rx.search(content) for rx in compiled_regexes)


def _file_matches_content_regex(
    file_path: Path, compiled_regexes: List[re.Pattern[str]]
) -> bool:
    """Return True if file content matches at least one compiled regex."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("Cannot read %s for regex matching: %s", file_path, exc)
        return False
    return _content_matches_regex(content, compiled_regexes)


# ---------------------------------------------------------------------------
# Core matching logic
# ---------------------------------------------------------------------------

def _match_files_to_guidelines(
    guidelines: List[Dict[str, Any]],
    repo_path: Path,
    folder_rules: dict,
    mode: str,
    changed_files: Optional[List[Dict[str, str]]] = None,
    file_diffs: Optional[Dict[str, str]] = None,
    repo_root_rel: Optional[str] = None,
    git_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Match files to guidelines and return the items list.

    In file mode: enumerate files once (via ``git ls-files`` or fallback
    glob), then fnmatch each pattern against the list.
    In diff mode: match against changed file list, apply content_regex on
    diff contents only.

    Optimization: all glob/fnmatch matching is done first, then
    content_regex checks are batched so each file is read at most once.
    """
    change_type_map: Dict[str, str] = {}

    # -- Build the file list to match against ------------------------------
    if changed_files is not None:
        # Diff mode: use only the changed files
        file_list: Optional[List[str]] = [
            cf["path"].replace("\\", "/") for cf in changed_files
        ]
        change_type_map = {
            cf["path"].replace("\\", "/"): cf["change_type"]
            for cf in changed_files
        }
    else:
        # File mode: enumerate all tracked files once
        file_list = _list_repo_files(repo_path, git_root, repo_root_rel)
        if file_list is None:
            logger.warning(
                "git ls-files unavailable — falling back to per-pattern glob"
            )

    # -- Phase 1: glob/fnmatch matching (no file reads) --------------------
    # For each guideline, find candidate files via pattern matching only.
    # Track which guidelines need content_regex post-filtering.
    file_to_guidelines: Dict[str, Set[str]] = defaultdict(set)

    # Guidelines that need content_regex: gname -> (compiled_regexes, candidate_files)
    pending_regex: Dict[str, tuple] = {}

    if file_list is not None:
        # Fast path: iterate files once, match all patterns per file.
        # Build pattern -> guideline name mapping.
        # Split guidelines into simple-pattern (no AND) and compound (AND).
        simple_patterns: Dict[str, List[str]] = defaultdict(list)  # pattern -> [gnames]
        compound_guidelines: List[Dict[str, Any]] = []

        for guideline in guidelines:
            gname = guideline["name"]
            has_compound = False
            for pattern in guideline["glob_patterns"]:
                if not pattern:
                    continue
                pattern = _normalize_pattern(pattern, repo_root_rel)
                if " AND " in pattern:
                    has_compound = True
                else:
                    simple_patterns[pattern].append(gname)
            if has_compound:
                compound_guidelines.append(guideline)

        # Deduplicate patterns — cache which unique patterns each file matches
        unique_patterns = list(simple_patterns.keys())
        logger.info(
            "Phase 1: matching %d files against %d unique patterns "
            "(%d guidelines)",
            len(file_list), len(unique_patterns), len(guidelines),
        )

        # Match: for each file, check each unique pattern once
        for fp in file_list:
            for pattern in unique_patterns:
                if fnmatch(fp, pattern) or PurePosixPath(fp).match(pattern):
                    for gname in simple_patterns[pattern]:
                        file_to_guidelines[fp].add(gname)

        # Handle compound " AND " patterns (rare, process per-guideline)
        for guideline in compound_guidelines:
            gname = guideline["name"]
            for pattern in guideline["glob_patterns"]:
                if not pattern:
                    continue
                pattern = _normalize_pattern(pattern, repo_root_rel)
                if " AND " not in pattern:
                    continue
                sub_patterns = [p.strip() for p in pattern.split(" AND ") if p.strip()]
                if not sub_patterns:
                    continue
                sub_result: Optional[Set[str]] = None
                for sp in sub_patterns:
                    sp = _normalize_pattern(sp, repo_root_rel)
                    matches = set(_fnmatch_files(file_list, sp))
                    sub_result = matches if sub_result is None else sub_result & matches
                if sub_result:
                    for fp in sub_result:
                        file_to_guidelines[fp].add(gname)

        # Now split: guidelines with content_regex need Phase 2 filtering
        for guideline in guidelines:
            gname = guideline["name"]
            content_regex = guideline["content_regex"]
            if not content_regex:
                continue

            compiled_regexes: List[re.Pattern[str]] = []
            for rx_str in content_regex:
                try:
                    compiled_regexes.append(re.compile(rx_str))
                except re.error:
                    pass
            if not compiled_regexes:
                continue

            # Collect files matched by glob for this guideline
            candidate_files = {
                fp for fp, gnames in file_to_guidelines.items()
                if gname in gnames
            }
            if candidate_files:
                # Remove from file_to_guidelines (will be re-added in Phase 2
                # if content matches)
                for fp in candidate_files:
                    file_to_guidelines[fp].discard(gname)
                pending_regex[gname] = (compiled_regexes, candidate_files)

        # Clean up empty entries (keep as defaultdict for Phase 2)
        file_to_guidelines = defaultdict(
            set,
            {fp: gnames for fp, gnames in file_to_guidelines.items() if gnames},
        )

    else:
        # Slow fallback: per-guideline glob (no git ls-files)
        for guideline in guidelines:
            gname = guideline["name"]
            glob_patterns = guideline["glob_patterns"]
            content_regex = guideline["content_regex"]

            matched_files: Set[str] = set()

            for pattern in glob_patterns:
                if not pattern:
                    continue
                pattern = _normalize_pattern(pattern, repo_root_rel)

                if " AND " in pattern:
                    sub_patterns = [p.strip() for p in pattern.split(" AND ") if p.strip()]
                    if not sub_patterns:
                        continue
                    sub_result = None
                    for sp in sub_patterns:
                        sp = _normalize_pattern(sp, repo_root_rel)
                        matches = set(_glob_match_files(repo_path, sp))
                        sub_result = matches if sub_result is None else sub_result & matches
                    if sub_result:
                        matched_files.update(sub_result)
                else:
                    matched_files.update(_glob_match_files(repo_path, pattern))

            if not matched_files:
                continue

            if content_regex:
                compiled_regexes_fb: List[re.Pattern[str]] = []
                for rx_str in content_regex:
                    try:
                        compiled_regexes_fb.append(re.compile(rx_str))
                    except re.error:
                        pass
                if compiled_regexes_fb:
                    pending_regex[gname] = (compiled_regexes_fb, matched_files)
                    continue

            for fp in matched_files:
                file_to_guidelines[fp].add(gname)

    # -- Phase 2: batched content_regex (each file read at most once) ------
    if pending_regex:
        if mode == "diff" and file_diffs is not None:
            # Diff mode: match regex against diff contents (no file I/O)
            for gname, (compiled_regexes, candidates) in pending_regex.items():
                for fp in candidates:
                    diff_text = file_diffs.get(fp, "")
                    if diff_text and _content_matches_regex(diff_text, compiled_regexes):
                        file_to_guidelines[fp].add(gname)
        else:
            # File mode: read each candidate file at most once, check
            # all pending guidelines' regexes against its content.
            #
            # Build: file -> list of (gname, compiled_regexes) to check.
            file_to_checks: Dict[str, List[tuple]] = defaultdict(list)
            for gname, (compiled_regexes, candidates) in pending_regex.items():
                for fp in candidates:
                    file_to_checks[fp].append((gname, compiled_regexes))

            checked = 0
            for fp, checks in file_to_checks.items():
                try:
                    content = (repo_path / fp).read_text(
                        encoding="utf-8", errors="replace"
                    )
                except OSError as exc:
                    logger.debug("Cannot read %s for regex matching: %s", fp, exc)
                    continue
                checked += 1

                for gname, compiled_regexes in checks:
                    if _content_matches_regex(content, compiled_regexes):
                        file_to_guidelines[fp].add(gname)

            logger.info(
                "Content-regex phase: read %d files for %d guidelines",
                checked, len(pending_regex),
            )

    # Apply folder rules and build items
    items: List[Dict[str, Any]] = []
    guideline_rel_paths = {g["name"]: g["rel_path"] for g in guidelines}

    for filename in sorted(file_to_guidelines.keys()):
        gnames = sorted(file_to_guidelines[filename])

        # Apply folder rules to restrict guidelines
        gnames = _apply_folder_rules(filename, gnames, folder_rules)
        if not gnames:
            continue

        # Convert names to relative paths
        guideline_paths = sorted(
            guideline_rel_paths[n] for n in gnames if n in guideline_rel_paths
        )

        item: Dict[str, Any] = {
            "filename": filename,
            "guidelines": guideline_paths,
        }

        if mode == "diff":
            item["change_type"] = change_type_map.get(filename)
            item["diff_contents"] = (file_diffs or {}).get(filename, "")

        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Specialist reviewer discovery
# ---------------------------------------------------------------------------

def _discover_specialist_reviewers(
    agents_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    """Discover specialist reviewer agent files in the agents directory.

    Looks for ``Octane.*Reviewer.agent.md`` files that contain
    ``scope_globs`` in their frontmatter (indicating a specialist
    reviewer, as opposed to orchestrator or sub-agents).

    Returns a dict mapping reviewer short name to metadata.
    The short name is derived by stripping the ``Octane.`` prefix,
    ``Reviewer.agent.md`` suffix, and lowercasing.
    E.g. ``Octane.SecurityReviewer.agent.md`` → ``security``.
    """
    result: Dict[str, Dict[str, Any]] = {}
    if not agents_dir.is_dir():
        logger.warning("Agents directory not found: %s", agents_dir)
        return result

    for child in sorted(agents_dir.iterdir()):
        if not child.name.endswith("Reviewer.agent.md"):
            continue
        if not child.name.startswith("Octane."):
            continue

        try:
            text = child.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Cannot read %s: %s", child, exc)
            continue

        fm = _parse_frontmatter(text)
        if fm is None:
            continue

        scope_globs = fm.get("scope_globs")
        if not scope_globs:
            # Not a specialist reviewer (e.g. orchestrator, sub-agent)
            continue
        if not isinstance(scope_globs, list):
            scope_globs = ["**/*"]

        # Derive short name: Octane.SecurityReviewer.agent.md → security
        stem = child.name.replace("Reviewer.agent.md", "")  # Octane.Security
        stem = stem.replace("Octane.", "")  # Security
        short_name = stem.lower()  # security

        result[short_name] = {
            "path": str(child),
            "scope_globs": scope_globs,
            "description": fm.get("description", ""),
        }
        logger.info(
            "Discovered specialist reviewer: %s (%s)",
            short_name, child.name,
        )

    return result


def _discover_specialist_reviewers_multi(
    agents_root: Optional[Path] = None,
    repo_agents_root: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """Discover specialist reviewers from multiple agent directories.

    Searches ``agents_root`` (plugin built-ins) first, then
    ``repo_agents_root`` (target repo custom agents).  Repo agents
    override built-ins with the same short name.

    Each entry in the result dict includes a ``source`` field:
    ``"plugin"`` or ``"repo"``.
    """
    result: Dict[str, Dict[str, Any]] = {}

    # 1. Discover from plugin agents root
    if agents_root is not None:
        for name, info in _discover_specialist_reviewers(agents_root).items():
            info["source"] = "plugin"
            result[name] = info

    # 2. Discover from repo custom agents root (overrides plugin)
    if repo_agents_root is not None:
        for name, info in _discover_specialist_reviewers(repo_agents_root).items():
            if name in result:
                logger.info(
                    "Repo custom reviewer '%s' overrides built-in from %s",
                    name, result[name]["path"],
                )
            info["source"] = "repo"
            result[name] = info

    return result


def _match_specialist_files(
    scope_globs: List[str],
    repo_path: Path,
    file_list: Optional[List[str]],
    changed_files: Optional[List[Dict[str, str]]],
    git_root: Optional[Path] = None,
    repo_root_rel: Optional[str] = None,
) -> List[str]:
    """Match files against a specialist reviewer's scope_globs.

    In diff mode (changed_files provided), only match against changed files.
    In file mode, match against the full file list.
    """
    if changed_files is not None:
        candidates = [cf["path"].replace("\\", "/") for cf in changed_files]
    elif file_list is not None:
        candidates = file_list
    else:
        # Fallback: list files
        candidates_raw = _list_repo_files(repo_path, git_root, repo_root_rel)
        candidates = candidates_raw if candidates_raw is not None else []

    matched: Set[str] = set()
    for pattern in scope_globs:
        pattern = _normalize_pattern(pattern, repo_root_rel)
        for fp in candidates:
            if fnmatch(fp, pattern) or PurePosixPath(fp).match(pattern):
                matched.add(fp)

    return sorted(matched)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def prepare_review(
    output_dir: str,
    mode: str,
    config_path: Optional[str] = None,
    commit_range: Optional[str] = None,
    staged: bool = False,
    untracked: bool = False,
    repo_path_override: Optional[str] = None,
    agents_root: Optional[str] = None,
    repo_agents_root: Optional[str] = None,
    changed_files_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full prepare-review pipeline and return the result dict.

    Args:
        changed_files_path: Path to a JSON file containing pre-computed changed
            files. Each entry: {"path": "src/Foo.cs", "change_type": "M"}.
            When provided in diff mode, skips internal git diff --name-status.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # -- 1. Find and parse config ------------------------------------------
    if config_path:
        cfg_path = Path(config_path)
        if not cfg_path.is_file():
            errors.append(f"Config file not found: {config_path}")
            return {
                "output_path": output_dir,
                "mode": mode,
                "config": {},
                "items": [],
                "dispatch_plan": {"reviewers": []},
                "errors": errors,
                "warnings": warnings,
            }
    else:
        start = Path(repo_path_override) if repo_path_override else Path.cwd()
        cfg_path = _discover_config(start)
        if cfg_path is None:
            errors.append(
                f"Config file not found: searched for .github/gatekeeper/gkpconfig.yml "
                f"(and legacy .github/gkpconfig.yml) starting from {start.resolve()}"
            )
            return {
                "output_path": output_dir,
                "mode": mode,
                "config": {},
                "items": [],
                "dispatch_plan": {"reviewers": []},
                "errors": errors,
                "warnings": warnings,
            }
        logger.info("Auto-discovered config: %s", cfg_path)

    raw_config = _parse_config(cfg_path)
    resolved = _resolve_config(raw_config, cfg_path, repo_path_override)

    errors.extend(resolved["errors"])
    warnings.extend(resolved["warnings"])

    if not resolved["valid"]:
        return {
            "output_path": output_dir,
            "mode": mode,
            "config": {
                "config_path": resolved["config_path"],
                "repo_root": resolved.get("repo_root", ""),
            },
            "items": [],
            "dispatch_plan": {"reviewers": []},
            "errors": errors,
            "warnings": warnings,
        }

    repo_path = Path(resolved["repo_root"])
    reviewers_config = resolved.get("reviewers", {})

    # -- 2. Detect git root for pattern normalisation ----------------------
    git_root = _find_git_root(repo_path)
    repo_root_rel: Optional[str] = None
    if git_root and git_root != repo_path:
        try:
            repo_root_rel = repo_path.relative_to(git_root).as_posix()
        except ValueError:
            repo_root_rel = None

    # -- 3. Discover files/changes -----------------------------------------
    changed_files: Optional[List[Dict[str, str]]] = None
    file_diffs: Optional[Dict[str, str]] = None

    if mode == "diff":
        git_cwd = git_root if git_root else repo_path

        if changed_files_path:
            # Use pre-computed changed files (e.g., from author-commit filtering)
            try:
                with open(changed_files_path, encoding="utf-8") as f:
                    changed_files = json.load(f)
                if not isinstance(changed_files, list) or not all(
                    isinstance(cf, dict) and "path" in cf and "change_type" in cf
                    for cf in changed_files
                ):
                    raise ValueError(
                        "Expected a JSON array of objects with 'path' and 'change_type' fields"
                    )
                logger.info(
                    "Using pre-computed changed files from %s: %d entries",
                    changed_files_path, len(changed_files),
                )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"Failed to read --changed-files {changed_files_path}: {exc}")
                return {
                    "output_path": output_dir,
                    "mode": mode,
                    "config": {"config_path": str(cfg_path), "repo_root": str(repo_path)},
                    "items": [],
                    "dispatch_plan": {"reviewers": []},
                    "errors": errors,
                    "warnings": warnings,
                }
        else:
            changed_files = _run_git_diff_name_status(
                git_cwd,
                commit_range=commit_range,
                staged=staged,
            )

        if not changed_files:
            warnings.append("No changed files found in diff")
        else:
            diff_text = _run_git_diff_unified(
                git_cwd,
                commit_range=commit_range,
                staged=staged,
            )
            file_diffs = _split_diff_by_file(diff_text)
            logger.info(
                "Diff mode: %d changed files, %d with diff content",
                len(changed_files), len(file_diffs),
            )

    # -- 4. Build file list once for reuse ---------------------------------
    file_list: Optional[List[str]] = None
    if changed_files is None:
        file_list = _list_repo_files(repo_path, git_root, repo_root_rel)

    # -- 5. Process each reviewer ------------------------------------------
    items: List[Dict[str, Any]] = []
    dispatch_plan: List[Dict[str, Any]] = []

    # Discover specialist reviewer agent files from multiple roots
    # Priority: repo custom agents override plugin built-in agents
    ar = Path(agents_root) if agents_root else None
    rar = Path(repo_agents_root) if repo_agents_root else None

    # Fallback: if neither root provided, use legacy config-relative path
    if ar is None and rar is None:
        config_dir = cfg_path.parent
        fallback_dir = config_dir / "agents"
        ar = fallback_dir if fallback_dir.is_dir() else None

    specialist_reviewers = _discover_specialist_reviewers_multi(
        agents_root=ar,
        repo_agents_root=rar,
    )

    # Collect searched roots for error messages
    searched_roots: List[str] = []
    if ar is not None:
        searched_roots.append(str(ar))
    if rar is not None:
        searched_roots.append(str(rar))

    for reviewer_name, reviewer_cfg in reviewers_config.items():
        reviewer_type = reviewer_cfg.get("type", "specialist")
        model = reviewer_cfg.get("model", "default")

        if reviewer_type == "guidelines":
            # Guidelines reviewer: run full guideline matching pipeline
            guidelines_root = reviewer_cfg.get("guidelines_root")
            folder_rules = reviewer_cfg.get("folder_rules", {})

            if not guidelines_root:
                warnings.append(
                    f"Reviewer '{reviewer_name}' missing guidelines_root"
                )
                continue

            skills_path = Path(guidelines_root)
            try:
                guidelines = _discover_guidelines(skills_path)
            except FileNotFoundError as exc:
                errors.append(str(exc))
                continue

            if not guidelines:
                warnings.append(
                    f"No guideline skills found in {guidelines_root}"
                )

            matched_items = _match_files_to_guidelines(
                guidelines=guidelines,
                repo_path=repo_path,
                folder_rules=folder_rules,
                mode=mode,
                changed_files=changed_files,
                file_diffs=file_diffs,
                repo_root_rel=repo_root_rel,
                git_root=git_root,
            )
            items.extend(matched_items)

            dispatch_plan.append({
                "name": reviewer_name,
                "type": "guidelines",
                "model": model,
                "guidelines_root": str(skills_path),
                "items_count": len(matched_items),
            })
            logger.info(
                "Guidelines reviewer '%s': %d items matched",
                reviewer_name, len(matched_items),
            )

        else:
            # Specialist reviewer: match scope_globs against files
            spec_info = specialist_reviewers.get(reviewer_name)
            if spec_info is None:
                # Reviewer agent file not found — mark as unavailable
                expected_name = (
                    f"Octane.{reviewer_name.capitalize()}"
                    f"Reviewer.agent.md"
                )
                roots_searched = ", ".join(searched_roots) if searched_roots else "(none)"
                dispatch_plan.append({
                    "name": reviewer_name,
                    "type": "specialist",
                    "model": model,
                    "reviewer_path": None,
                    "files": [],
                    "available": False,
                    "error": f"Reviewer agent file not found: "
                             f"{expected_name}. "
                             f"Searched: {roots_searched}",
                })
                warnings.append(
                    f"Specialist reviewer '{reviewer_name}' unavailable: "
                    f"no matching Octane.*Reviewer.agent.md found in "
                    f"[{roots_searched}]"
                )
                continue

            matched_files = _match_specialist_files(
                scope_globs=spec_info["scope_globs"],
                repo_path=repo_path,
                file_list=file_list,
                changed_files=changed_files,
                git_root=git_root,
                repo_root_rel=repo_root_rel,
            )

            dispatch_plan.append({
                "name": reviewer_name,
                "type": "specialist",
                "model": model,
                "reviewer_path": spec_info["path"],
                "files": matched_files,
                "available": True,
            })
            logger.info(
                "Specialist reviewer '%s': %d files matched",
                reviewer_name, len(matched_files),
            )

    logger.info(
        "Prepared %d guideline review items, %d reviewers in dispatch plan",
        len(items), len(dispatch_plan),
    )

    return {
        "output_path": output_dir,
        "mode": mode,
        "config": {
            "config_path": resolved["config_path"],
            "repo_root": str(repo_path),
        },
        "items": items,
        "dispatch_plan": {"reviewers": dispatch_plan},
        "errors": errors,
        "warnings": warnings,
    }


def _emit_sql(result: dict, sql_path: Path) -> None:
    """Write SQL INSERT statements for gk_review_items from prepare result."""
    lines: list[str] = []
    lines.append(
        "CREATE TABLE IF NOT EXISTS gk_review_items (\n"
        "    filename TEXT NOT NULL,\n"
        "    change_type TEXT,\n"
        "    diff_contents TEXT,\n"
        "    guidelines TEXT NOT NULL DEFAULT '[]',\n"
        "    PRIMARY KEY (filename)\n"
        ");"
    )
    for item in result.get("items", []):
        fn = item["filename"].replace("'", "''")
        ct = (item.get("change_type") or "").replace("'", "''")
        dc = (item.get("diff_contents") or "").replace("'", "''")
        gl = json.dumps(item.get("guidelines", []), ensure_ascii=False).replace("'", "''")
        lines.append(
            f"INSERT OR REPLACE INTO gk_review_items "
            f"(filename, change_type, diff_contents, guidelines) VALUES "
            f"('{fn}', '{ct}', '{dc}', '{gl}');"
        )
    sql_path.parent.mkdir(parents=True, exist_ok=True)
    sql_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote SQL inserts (%d items) to %s", len(result.get("items", [])), sql_path)


def _load_to_db(result: dict, db_path: str) -> None:
    """Load review items and dispatch plan into a SQLite database.

    Clears any existing rows in gk_review_items and gk_dispatch_plan
    before inserting to avoid stale data from prior runs.  All work
    happens in a single transaction so partial failures leave the
    tables unchanged.
    """
    if not os.path.isfile(db_path):
        raise FileNotFoundError(
            f"Database file does not exist: {db_path}. "
            "The --db path must point to an existing SQLite database."
        )

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")

        # -- Review items --------------------------------------------------
        conn.execute(
            "CREATE TABLE IF NOT EXISTS gk_review_items (\n"
            "    filename TEXT NOT NULL,\n"
            "    change_type TEXT,\n"
            "    diff_contents TEXT,\n"
            "    guidelines TEXT NOT NULL DEFAULT '[]',\n"
            "    PRIMARY KEY (filename)\n"
            ")"
        )
        conn.execute("DELETE FROM gk_review_items")

        rows = [
            (
                item["filename"],
                item.get("change_type") or "",
                item.get("diff_contents") or "",
                json.dumps(item.get("guidelines", []), ensure_ascii=False),
            )
            for item in result.get("items", [])
        ]
        conn.executemany(
            "INSERT INTO gk_review_items "
            "(filename, change_type, diff_contents, guidelines) VALUES (?, ?, ?, ?)",
            rows,
        )
        logger.info(
            "Loaded %d review items into %s", len(rows), db_path
        )

        # -- Dispatch plan -------------------------------------------------
        conn.execute(
            "CREATE TABLE IF NOT EXISTS gk_dispatch_plan (\n"
            "    reviewer_name TEXT PRIMARY KEY,\n"
            "    reviewer_type TEXT NOT NULL,\n"
            "    model TEXT DEFAULT 'default',\n"
            "    guidelines_root TEXT,\n"
            "    reviewer_path TEXT,\n"
            "    files TEXT DEFAULT '[]',\n"
            "    items_count INTEGER DEFAULT 0,\n"
            "    available INTEGER DEFAULT 1,\n"
            "    error TEXT\n"
            ")"
        )
        conn.execute("DELETE FROM gk_dispatch_plan")

        dispatch_reviewers = result.get("dispatch_plan", {}).get(
            "reviewers", []
        )
        for rev in dispatch_reviewers:
            conn.execute(
                "INSERT INTO gk_dispatch_plan "
                "(reviewer_name, reviewer_type, model, guidelines_root, "
                "reviewer_path, files, items_count, available, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rev["name"],
                    rev["type"],
                    rev.get("model", "default"),
                    rev.get("guidelines_root"),
                    rev.get("reviewer_path"),
                    json.dumps(rev.get("files", []), ensure_ascii=False),
                    rev.get("items_count", 0),
                    1 if rev.get("available", True) else 0,
                    rev.get("error"),
                ),
            )
        logger.info(
            "Loaded %d dispatch plan entries into %s",
            len(dispatch_reviewers), db_path,
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare review items for the Gatekeeper code review pipeline.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for review artifacts.",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["file", "diff"],
        help="Review mode: 'file' for full scan, 'diff' for change-based.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to gkpconfig.yml. Auto-discovered if omitted.",
    )
    parser.add_argument(
        "--commit-range",
        default=None,
        help="Git commit range for diff mode (e.g., HEAD~3..HEAD).",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Review staged changes (diff mode).",
    )
    parser.add_argument(
        "--untracked",
        action="store_true",
        help="Review untracked changes (diff mode).",
    )
    parser.add_argument(
        "--repo-path",
        default=None,
        help="Override repo_root from config. Also used as starting point "
             "for config auto-discovery.",
    )
    parser.add_argument(
        "--agents-root",
        default=None,
        help="Directory containing built-in reviewer agent files "
             "(e.g. $AGENCY_PLUGIN_DIR/agents). When provided, "
             "specialist reviewers are discovered here first.",
    )
    parser.add_argument(
        "--repo-agents-root",
        default=None,
        help="Directory containing repo-custom reviewer agent files "
             "(e.g. .github/gatekeeper/agents). Custom reviewers "
             "override built-in reviewers with the same short name.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--emit-sql",
        default=None,
        help="Path to write SQL INSERT statements for gk_review_items. "
             "The agent can execute this file directly via the sql tool.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to an existing SQLite database file. When provided, "
             "review items are loaded into gk_review_items and the "
             "dispatch plan is loaded into gk_dispatch_plan.",
    )
    parser.add_argument(
        "--changed-files",
        default=None,
        help="Path to a JSON file with pre-computed changed files. "
             "Each entry: {\"path\": \"src/Foo.cs\", \"change_type\": \"M\"}. "
             "When provided in diff mode, skips internal git diff --name-status.",
    )
    args = parser.parse_args()

    # Validate mode-specific arguments
    if args.mode == "diff" and not (args.commit_range or args.staged or args.untracked):
        parser.error(
            "Diff mode requires one of: --commit-range, --staged, or --untracked"
        )

    result = prepare_review(
        output_dir=args.output_dir,
        mode=args.mode,
        config_path=args.config,
        commit_range=args.commit_range,
        staged=args.staged,
        untracked=args.untracked,
        repo_path_override=args.repo_path,
        agents_root=args.agents_root,
        repo_agents_root=args.repo_agents_root,
        changed_files_path=args.changed_files,
    )

    output_json = json.dumps(result, indent=2, sort_keys=False)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json + "\n", encoding="utf-8")
        logger.info("Wrote output to %s", out_path)
    else:
        print(output_json)

    if args.emit_sql:
        _emit_sql(result, Path(args.emit_sql))

    # Exit with error code if there were errors
    if result["errors"]:
        sys.exit(1)

    if args.db:
        _load_to_db(result, args.db)


if __name__ == "__main__":
    main()
