#!/usr/bin/env python3
"""Back-populate content_regex into existing SKILL.md frontmatter.

Reads guideline SKILL.md files, analyses the ``## Detection Instructions``
section for explicit regex patterns and code tokens, and writes
``content_regex`` entries into the YAML frontmatter.

Usage:
    python populate_content_regex.py --skills-dir <path> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frontmatter parsing helpers
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> Optional[Tuple[str, str]]:
    """Split a SKILL.md into (frontmatter_text, body_text).

    Returns None if no valid frontmatter delimiters found.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    fm = "".join(lines[1:end])
    body = "".join(lines[end + 1:])
    return fm, body


def _parse_frontmatter_yaml(fm_text: str) -> Optional[Dict[str, Any]]:
    """Parse frontmatter text as YAML. Returns None on failure."""
    try:
        import yaml
        return yaml.safe_load(fm_text) or {}
    except ImportError:
        return None
    except Exception:
        return None


def _has_content_regex(fm_text: str) -> bool:
    """Check if frontmatter already contains a content_regex field."""
    for line in fm_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("content_regex:") or stripped == "content_regex:":
            return True
    return False


# ---------------------------------------------------------------------------
# Pattern extraction from Detection Instructions
# ---------------------------------------------------------------------------

def _extract_section(body: str, heading: str) -> Optional[str]:
    """Extract the content of a markdown section by heading name."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line, re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        return None

    # Collect until next ## heading or end of file
    end = len(lines)
    for i in range(start, len(lines)):
        if re.match(r"^##\s+", lines[i]):
            end = i
            break
    return "\n".join(lines[start:end]).strip()


def _extract_regex_from_code_fences(text: str) -> List[str]:
    """Extract regex patterns from code fences marked as ``regex``."""
    patterns: List[str] = []
    fence_re = re.compile(r"```(?:regex)\s*\n(.*?)```", re.DOTALL)
    for match in fence_re.finditer(text):
        block = match.group(1)
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Validate it compiles
            try:
                re.compile(line)
                patterns.append(line)
            except re.error:
                logger.debug("Skipping non-compilable line from regex fence: %s", line)
    return patterns


def _extract_backtick_patterns(text: str) -> List[str]:
    """Extract backtick-wrapped patterns that look like regex.

    Only accepts patterns that contain *intentional* regex syntax
    (backslash escapes, character classes, quantifiers applied to groups,
    anchors, alternation).  Plain code tokens that happen to contain
    metacharacters (parentheses, dots, brackets) are handled by
    ``_extract_code_tokens`` instead — this avoids emitting both a raw
    and an escaped duplicate for the same token.

    Patterns longer than ``_MAX_BACKTICK_PATTERN_LEN`` characters are
    rejected as likely prose / pseudocode snippets rather than useful
    regex filters.
    """
    patterns: List[str] = []
    backtick_re = re.compile(r"`([^`]{4,})`")
    for match in backtick_re.finditer(text):
        candidate = match.group(1)
        # Skip overly long patterns — these are prose / pseudocode
        if len(candidate) > _MAX_BACKTICK_PATTERN_LEN:
            continue
        # Require *intentional* regex syntax, not just parentheses or
        # dots that appear in normal code tokens like ``Foo.Bar()``
        if not _looks_like_intentional_regex(candidate):
            continue
        try:
            re.compile(candidate)
            patterns.append(candidate)
        except re.error:
            pass
    return patterns


# Maximum length for a backtick-wrapped pattern to be treated as regex.
# Longer strings are almost certainly pseudocode or prose examples.
_MAX_BACKTICK_PATTERN_LEN = 60


def _looks_like_intentional_regex(candidate: str) -> bool:
    """Return True if *candidate* contains syntax that signals intentional regex.

    We look for backslash escapes (``\\.``, ``\\s``, ``\\w``), character
    classes (``[^A]``, ``[a-z]``), quantifiers on groups (``(...)+``),
    anchors (``^``, ``$`` at boundaries), or alternation (``|``).

    Plain code tokens like ``Task.Run()``, ``[DataMember]``, or
    ``Assert.Equal(x, y)`` do NOT qualify — they contain metacharacters
    only incidentally.
    """
    # Backslash sequences that are clearly regex
    if re.search(r"\\[.dDwWsSbB+*?()\[\]{}|^$]", candidate):
        return True
    # Character classes like [^A], [a-z], [0-9]
    if re.search(r"\[[^\]]{1,20}\]", candidate):
        # Exclude C# attributes like [DataMember], [TestMethod],
        # [JsonProperty("name")], [Description("...")]
        if re.match(r"^\[[A-Z][a-zA-Z]+(\(.*\))?\]$", candidate):
            return False
        return True
    # Alternation with | (but not || which is a logical operator)
    if "|" in candidate and "||" not in candidate:
        return True
    # Anchors at string boundaries
    if candidate.startswith("^") or candidate.endswith("$"):
        return True
    # Named groups, lookahead, lookbehind
    if "(?P<" in candidate or "(?=" in candidate or "(?!" in candidate:
        return True
    if "(?<=" in candidate or "(?<!" in candidate:
        return True
    return False


# Words/phrases to exclude from backtick extraction (markdown formatting, prose)
_EXCLUDE_TOKENS = frozenset({
    # Markdown / SKILL.md formatting
    "it is not a violation", "it is a violation",
    "not a violation", "a violation",
    # Common English words that appear in backticks
    "true", "false", "null", "none", "yes", "no",
    "e.g.", "i.e.", "etc.", "note", "example",
    "see", "above", "below", "optional", "required",
})

# Language keywords that are too broad to be useful as content_regex
# filters — they appear in virtually every C# file and provide no
# signal for guideline applicability.
_BROAD_KEYWORDS = frozenset({
    "async", "await", "catch", "throw", "using", "lock",
    "static", "override", "virtual", "sealed", "readonly",
    "volatile", "params", "yield", "return", "interface",
    "abstract", "internal", "protected", "private", "public",
    "new", "var", "void", "string", "int", "bool", "class",
    "if", "else", "for", "foreach", "while", "do", "switch",
    "case", "break", "continue", "try", "finally", "typeof",
    "namespace", "enum", "struct", "delegate", "event",
})

# Minimum length for a backtick token to be considered a code identifier
_MIN_TOKEN_LEN = 2


def _is_code_token(token: str) -> bool:
    """Return True if a backtick-wrapped token looks like a code identifier.

    Accepts: PascalCase, camelCase, dotted names (Foo.Bar), method calls
    (Foo()), type names (List<T>), attributes ([Attr]), namespaced
    identifiers, and common language keywords.

    Rejects: broad single-keyword tokens that match virtually every C#
    file, prose-like snippets with many spaces, and tokens in the
    exclude list.
    """
    if token.lower() in _EXCLUDE_TOKENS:
        return False
    if token in _BROAD_KEYWORDS:
        return False
    if len(token) < _MIN_TOKEN_LEN:
        return False
    # Reject prose-like tokens: too many spaces signals a sentence/snippet
    if token.count(" ") > 4:
        return False
    # Reject very long tokens — likely pseudocode examples
    if len(token) > 80:
        return False

    # Contains a dot → likely qualified name (e.g., Task.Run, ex.Message)
    if "." in token:
        return True
    # Contains :: → C++ / C# scope (e.g., System::IO)
    if "::" in token:
        return True
    # PascalCase with at least 2 uppercase (e.g., CancellationToken, TimeSpan)
    if re.match(r"^[A-Z][a-zA-Z0-9]*[A-Z]", token):
        return True
    # Has parentheses → method call or signature (e.g., Dispose(), async Task)
    if "(" in token:
        return True
    # Has angle brackets → generic type (e.g., List<T>)
    if "<" in token:
        return True
    # Has square brackets → attribute or indexer (e.g., [TestMethod])
    if token.startswith("[") and token.endswith("]"):
        return True
    # camelCase with at least one uppercase after first char
    if re.match(r"^[a-z][a-zA-Z0-9]*[A-Z]", token):
        return True
    # Starts with uppercase and >= 5 chars (likely a type/class name)
    if token[0].isupper() and len(token) >= 5 and token.isidentifier():
        return True
    # Contains underscore → likely a constant or identifier
    if "_" in token and token.replace("_", "").isalnum():
        return True

    return False


def _token_to_regex(token: str) -> str:
    """Convert a code token to a regex pattern for content matching.

    Escapes regex metacharacters so the token matches literally.
    """
    return re.escape(token)


def _extract_code_tokens(text: str) -> List[str]:
    """Extract backtick-wrapped code tokens and convert to literal regex."""
    patterns: List[str] = []
    backtick_re = re.compile(r"`([^`]+)`")
    seen: set = set()

    for match in backtick_re.finditer(text):
        token = match.group(1).strip()
        if not token or token.lower() in seen:
            continue
        seen.add(token.lower())

        if _is_code_token(token):
            regex = _token_to_regex(token)
            patterns.append(regex)

    return patterns


def _derive_content_regex(body: str) -> List[str]:
    """Derive content_regex patterns from Detection Instructions.

    Extraction strategy (ordered by confidence):
    1. Regex code fences (```regex blocks) — used as-is
    2. Backtick-wrapped patterns with regex metacharacters — used as-is
    3. Backtick-wrapped code tokens (identifiers, method names, types) —
       escaped to literal regex
    """
    section = _extract_section(body, "Detection Instructions")
    if not section:
        # Also try "Detection Patterns" (used in raw guidelines)
        section = _extract_section(body, "Detection Patterns")
    if not section:
        return []

    patterns: List[str] = []

    # Strategy 1: Regex code fences (highest confidence — use as-is)
    patterns.extend(_extract_regex_from_code_fences(section))

    # Strategy 2: Backtick-wrapped patterns with regex metacharacters
    patterns.extend(_extract_backtick_patterns(section))

    # Strategy 3: Infer from backtick-wrapped code tokens (identifiers,
    # method names, types) — escaped to literal regex
    patterns.extend(_extract_code_tokens(section))

    # Dedupe and sort
    return sorted(set(patterns))


# ---------------------------------------------------------------------------
# Frontmatter rewriting
# ---------------------------------------------------------------------------

def _insert_content_regex(fm_text: str, patterns: List[str]) -> str:
    """Insert content_regex into frontmatter text after the scope block."""
    lines = fm_text.splitlines(keepends=True)
    insert_after = None

    # Find the last line of the scope block
    in_scope = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("scope:"):
            in_scope = True
            continue
        if in_scope:
            if stripped.startswith("- "):
                insert_after = i
            else:
                break

    if insert_after is None:
        # Fallback: insert before the end
        insert_after = len(lines) - 1

    # Build content_regex YAML block
    regex_lines = ["  content_regex:\n"]
    for p in patterns:
        # Escape for YAML double-quoted string
        escaped = p.replace("\\", "\\\\").replace('"', '\\"')
        regex_lines.append(f'    - "{escaped}"\n')

    # Insert after the scope block
    new_lines = lines[: insert_after + 1] + regex_lines + lines[insert_after + 1:]
    return "".join(new_lines)


def _rebuild_file(fm_text: str, body: str) -> str:
    """Rebuild a SKILL.md file from frontmatter and body."""
    return f"---\n{fm_text}---\n{body}"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def populate_one(skill_dir: Path, dry_run: bool = False) -> Optional[str]:
    """Populate content_regex for a single SKILL.md.

    Returns the guideline name if updated, None if skipped.
    """
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None

    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read %s: %s", skill_md, exc)
        return None

    parts = _split_frontmatter(text)
    if parts is None:
        logger.warning("No frontmatter in %s — skipping", skill_md)
        return None

    fm_text, body = parts

    # Parse frontmatter to check type
    parsed = _parse_frontmatter_yaml(fm_text)
    if parsed:
        metadata = parsed.get("metadata", {})
        if not isinstance(metadata, dict) or metadata.get("type") != "guideline":
            return None
        # Skip if already has content_regex with values
        existing = metadata.get("content_regex", [])
        if isinstance(existing, list) and existing:
            logger.debug("Guideline '%s': already has content_regex — skipping", skill_dir.name)
            return None

    # Check raw frontmatter for existing content_regex field
    if _has_content_regex(fm_text):
        logger.debug("Guideline '%s': frontmatter already has content_regex — skipping", skill_dir.name)
        return None

    # Derive patterns from body
    patterns = _derive_content_regex(body)
    if not patterns:
        logger.debug("Guideline '%s': no patterns derived — skipping", skill_dir.name)
        return None

    # Insert into frontmatter
    new_fm = _insert_content_regex(fm_text, patterns)
    new_text = _rebuild_file(new_fm, body)

    if dry_run:
        logger.info(
            "[DRY RUN] Would update '%s' with %d content_regex patterns: %s",
            skill_dir.name, len(patterns), patterns,
        )
    else:
        skill_md.write_text(new_text, encoding="utf-8")
        logger.info(
            "Updated '%s' with %d content_regex patterns",
            skill_dir.name, len(patterns),
        )

    return skill_dir.name


def populate_all(
    skills_dir: Path,
    dry_run: bool = False,
) -> Dict[str, List[str]]:
    """Populate content_regex for all guidelines in a directory.

    Returns a summary dict with 'updated' and 'skipped' lists.
    """
    if not skills_dir.is_dir():
        raise FileNotFoundError(f"Skills directory not found: {skills_dir}")

    updated: List[str] = []
    skipped: List[str] = []

    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        result = populate_one(child, dry_run=dry_run)
        if result:
            updated.append(result)
        elif (child / "SKILL.md").is_file():
            skipped.append(child.name)

    return {"updated": updated, "skipped": skipped}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back-populate content_regex into SKILL.md frontmatter.",
    )
    parser.add_argument(
        "--skills-dir",
        required=True,
        help="Directory containing guideline skill subdirectories.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print changes without modifying files.",
    )
    args = parser.parse_args()

    try:
        summary = populate_all(Path(args.skills_dir), dry_run=args.dry_run)
    except (FileNotFoundError, OSError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    prefix = "[DRY RUN] " if args.dry_run else ""
    logger.info(
        "%s%d updated, %d skipped",
        prefix, len(summary["updated"]), len(summary["skipped"]),
    )

    # Print summary JSON to stdout
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
