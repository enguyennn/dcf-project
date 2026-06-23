#!/usr/bin/env python3
"""
validate_finding_tags.py — Deterministic post-review validator for finding tags.

Findings are grounded two ways:
  - Deep-reasoning findings cite the reserved guideline "deep-reasoning" and carry the
    tag "DEEPREASONING". They are always kept — this is the only non-[GK-*-N] path.
  - Doc-backed findings cite the full file path of a knowledge/guideline doc. For each
    such violation this script verifies that:
      - violation["guideline"] resolves to an existing file
      - that file contains at least one inline [GK-<PREFIX>-<NUMBER>] tag
      - violation["tag"] is present, well-formed, and exists as a tag in that file

Violations that fail any check are moved into the row's dropped_findings array
with a structured drop_reason. The script rewrites the row's violations and
dropped_findings JSON columns atomically.

Usage:
    python validate_finding_tags.py --batch-id <id> --repo <path>
                                    [--skills-root <path>] [--db <path>]

Drop reasons (in check order):
    guideline-doc-missing  — guideline path doesn't resolve to a file
    guideline-untagged     — guideline doc contains zero [GK-*-N] tags
    missing-tag            — violation has no tag (or empty string)
    malformed-tag          — tag doesn't match ^GK-[A-Z0-9]+-\\d+$
    tag-not-found          — tag is well-formed but not present in the doc

Exit codes:
    0  success (drops are normal)
    2  IO / SQL / JSON error
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


TAG_REGEX = re.compile(r"\[(GK-[A-Z0-9]+-\d+)\]")
FINDING_TAG_REGEX = re.compile(r"^GK-[A-Z0-9]+-\d+$")
DEEP_REASONING_SENTINEL = "deep-reasoning"
DEEP_REASONING_TAG = "DEEPREASONING"


def _resolve_guideline_path(
    guideline: str, repo: Path, skills_root: Path
) -> Path | None:
    """Resolve a guideline reference against absolute, repo-relative, then skills-root-relative."""
    if not guideline:
        return None
    candidate = Path(guideline)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    for base in (repo, skills_root):
        p = (base / guideline).resolve()
        if p.is_file():
            return p
    return None


def _extract_tags(doc_path: Path) -> set[str]:
    """Return the set of [GK-*-N] tags found inline in the document."""
    try:
        text = doc_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(TAG_REGEX.findall(text))


def _build_drop_entry(violation: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    """Construct a dropped_findings entry from a rejected violation."""
    return {
        "file": violation.get("file_name"),
        "line": violation.get("startline"),
        "suspected_issue": violation.get("violation") or violation.get("detection") or "",
        "drop_reason": reason,
        "detail": detail,
    }


def _validate_one(
    violation: dict[str, Any], repo: Path, skills_root: Path
) -> tuple[bool, str | None, str | None]:
    """Return (kept, drop_reason, detail). kept=True ⇒ drop_reason/detail are None."""
    guideline = (violation.get("guideline") or "").strip()
    tag = violation.get("tag")

    # Deep-reasoning findings carry the DEEPREASONING tag (with the
    # "deep-reasoning" sentinel guideline). They are the only non-[GK-*-N]
    # path and are always kept.
    if guideline == DEEP_REASONING_SENTINEL or tag == DEEP_REASONING_TAG:
        return True, None, None

    doc_path = _resolve_guideline_path(guideline, repo, skills_root)
    if doc_path is None:
        return False, "guideline-doc-missing", f"guideline path did not resolve: {guideline!r}"

    tags = _extract_tags(doc_path)
    if not tags:
        return False, "guideline-untagged", f"no [GK-*-N] tags found in {doc_path}"

    if not tag:
        return False, "missing-tag", "violation has no tag field"
    if not FINDING_TAG_REGEX.fullmatch(tag):
        return False, "malformed-tag", f"tag {tag!r} does not match ^GK-[A-Z0-9]+-\\d+$"
    if tag not in tags:
        return (
            False,
            "tag-not-found",
            f"tag {tag!r} not present in {doc_path}; available tags: {sorted(tags)}",
        )

    return True, None, None


def validate_batch(
    db_path: Path, batch_id: str, repo: Path, skills_root: Path
) -> dict[str, Any]:
    """Validate all violations in the given batch's row. Returns a summary dict."""
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT violations, dropped_findings FROM gk_review_results WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"no gk_review_results row for batch_id={batch_id!r}")

        violations_raw = row["violations"] or "[]"
        dropped_raw = row["dropped_findings"] or "[]"
        try:
            violations = json.loads(violations_raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"violations column is not valid JSON: {e}") from e
        try:
            dropped = json.loads(dropped_raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"dropped_findings column is not valid JSON: {e}") from e

        if not isinstance(violations, list):
            raise ValueError(f"violations is not a JSON array: {type(violations).__name__}")
        if not isinstance(dropped, list):
            raise ValueError(f"dropped_findings is not a JSON array: {type(dropped).__name__}")

        kept: list[dict[str, Any]] = []
        drops_by_reason: dict[str, int] = {}
        new_dropped: list[dict[str, Any]] = []

        for violation in violations:
            if not isinstance(violation, dict):
                # Unparseable entry — drop with a generic reason.
                reason = "malformed-violation"
                new_dropped.append(
                    {
                        "file": None,
                        "line": None,
                        "suspected_issue": str(violation)[:200],
                        "drop_reason": reason,
                        "detail": "violation entry is not a JSON object",
                    }
                )
                drops_by_reason[reason] = drops_by_reason.get(reason, 0) + 1
                continue

            ok, reason, detail = _validate_one(violation, repo, skills_root)
            if ok:
                kept.append(violation)
            else:
                assert reason is not None and detail is not None
                new_dropped.append(_build_drop_entry(violation, reason, detail))
                drops_by_reason[reason] = drops_by_reason.get(reason, 0) + 1

        merged_dropped = dropped + new_dropped

        conn.execute(
            "UPDATE gk_review_results SET violations = ?, dropped_findings = ? WHERE batch_id = ?",
            (json.dumps(kept), json.dumps(merged_dropped), batch_id),
        )
        conn.commit()

        return {
            "batch_id": batch_id,
            "kept": len(kept),
            "dropped": len(new_dropped),
            "drops_by_reason": drops_by_reason,
        }
    finally:
        conn.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically validate reviewer finding tags against their cited guideline docs."
    )
    parser.add_argument("--batch-id", required=True, help="Batch ID whose gk_review_results row to validate.")
    parser.add_argument("--repo", required=True, type=Path, help="Absolute path to the repository root.")
    parser.add_argument(
        "--skills-root",
        type=Path,
        default=None,
        help="Absolute path to the skills root. Defaults to <repo>/.github/skills.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to the session SQLite database. Defaults to env GK_SESSION_DB.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    repo = args.repo.resolve()
    skills_root = (args.skills_root or (repo / ".github" / "skills")).resolve()

    db_path = args.db
    if db_path is None:
        env_db = os.environ.get("GK_SESSION_DB")
        if not env_db:
            print(
                "error: --db not provided and GK_SESSION_DB is not set",
                file=sys.stderr,
            )
            return 2
        db_path = Path(env_db)
    db_path = db_path.resolve()

    try:
        summary = validate_batch(db_path, args.batch_id, repo, skills_root)
    except (FileNotFoundError, LookupError, ValueError, sqlite3.Error) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    json.dump(summary, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
