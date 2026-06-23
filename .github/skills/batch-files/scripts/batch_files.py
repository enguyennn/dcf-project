#!/usr/bin/env python3
"""Batch review items into optimised review batches.

Reads a ``prepare_review.py`` output JSON (with file-to-guideline mappings)
and groups items into batches respecting configurable size limits using a
biclique cover algorithm.

Usage:
    python batch_files.py --input <prepare.json> --output <batches.json> \
        [--max-batch-size 10] [--max-guidelines-per-batch 10]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def _load_prepare_json(path: str) -> Dict[str, Set[str]]:
    """Load a ``prepare.json`` file and return a file->guidelines mapping.

    The prepare-review format has an ``items`` array where each entry
    contains ``filename`` and ``guidelines`` (list of relative paths
    like ``"name/SKILL.md"``).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Failed to read input '{path}': {exc}") from exc

    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError(f"Input '{path}' missing or invalid 'items' array")

    file_to_guidelines: Dict[str, Set[str]] = {}
    for item in items:
        filename = item.get("filename")
        guidelines = item.get("guidelines", [])
        if filename and guidelines:
            file_to_guidelines[filename] = set(guidelines)

    logger.info("Loaded %d files with guidelines", len(file_to_guidelines))
    return file_to_guidelines


# ---------------------------------------------------------------------------
# Core batching algorithm
# ---------------------------------------------------------------------------

def _biclique_cover(
    file_to_guidelines: Dict[str, Set[str]],
    max_batch_size: int,
    max_guidelines_per_batch: int,
) -> List[Dict[str, Any]]:
    """Cover all file-guideline edges with minimum biclique batches.

    A biclique batch ``(F', G')`` guarantees every file in *F'* matches
    every guideline in *G'*.

    **Algorithm — Group-then-Profile Batching:**

    1. Pack files into groups of *max_batch_size* using the greedy
       overlap-maximising heuristic (same as the legacy algorithm).
    2. For each group, compute the *shared core* — the intersection of
       all files' guideline sets.  Create biclique batches for the core
       (every file in the group matches every core guideline).
    3. For each group's *residual* guidelines (per-file guidelines not in
       the core), apply profile batching — group residual guidelines by
       their exact file-set within the group and batch per profile.

    This produces true bicliques with no wasted reviewer pairs and
    typically needs fewer batches than pure profile batching because file
    grouping maximises the shared core.
    """
    if not file_to_guidelines:
        return []

    # ── Step 1: Pack files into groups ────────────────────────────────
    file_groups = _pack_file_groups(file_to_guidelines, max_batch_size)

    logger.info(
        "Biclique cover: %d files packed into %d groups",
        len(file_to_guidelines), len(file_groups),
    )

    # ── Step 2-3: Per-group biclique batching ─────────────────────────
    batches: List[Dict[str, Any]] = []
    batch_number = 1

    for group in file_groups:
        files = group["files"]
        file_guidelines: Dict[str, Set[str]] = group.get(
            "file_guidelines", {}
        )
        if not file_guidelines:
            file_guidelines = {
                f: file_to_guidelines.get(f, set()) for f in files
            }

        # Compute shared core = intersection of all files' guideline sets
        shared: Optional[Set[str]] = None
        for f in files:
            fg = file_guidelines.get(f, set())
            shared = set(fg) if shared is None else shared & fg
        shared = shared or set()

        # -- Core batches (true bicliques: all files × shared guidelines) --
        shared_sorted = sorted(shared)
        for gi in range(0, len(shared_sorted), max_guidelines_per_batch):
            g_chunk = shared_sorted[gi : gi + max_guidelines_per_batch]
            sorted_files = sorted(files)
            batches.append({
                "batch_id": f"batch_{batch_number:03d}",
                "files": sorted_files,
                "guidelines": g_chunk,
                "file_to_guidelines": {
                    f: list(g_chunk) for f in sorted_files
                },
            })
            batch_number += 1

        # -- Residual batches (non-shared guidelines, profile-batched) --
        residual_g2f: Dict[str, Set[str]] = defaultdict(set)
        for f in files:
            fg = file_guidelines.get(f, set())
            for g in fg:
                if g not in shared:
                    residual_g2f[g].add(f)

        if residual_g2f:
            profile_to_gs: Dict[frozenset, List[str]] = defaultdict(list)
            for g, fset in residual_g2f.items():
                profile_to_gs[frozenset(fset)].append(g)

            for fset, gs in sorted(
                profile_to_gs.items(),
                key=lambda x: (-len(x[0]), sorted(x[1])[0]),
            ):
                pfiles = sorted(fset)
                pgs = sorted(gs)
                for gi in range(0, len(pgs), max_guidelines_per_batch):
                    g_chunk = pgs[gi : gi + max_guidelines_per_batch]
                    batches.append({
                        "batch_id": f"batch_{batch_number:03d}",
                        "files": pfiles,
                        "guidelines": g_chunk,
                        "file_to_guidelines": {
                            f: list(g_chunk) for f in pfiles
                        },
                    })
                    batch_number += 1

    total_edges = sum(len(gs) for gs in file_to_guidelines.values())
    logger.info(
        "Group-profile biclique cover (pre-compact): %d batches covering "
        "%d edges",
        len(batches), total_edges,
    )

    # ── Step 4: Cross-group compaction ────────────────────────────────
    # Merge batches that share the same guideline set (combine files
    # across groups) or the same file set (combine guidelines).  Both
    # merges preserve the biclique property.
    batches = _compact_batches(
        batches, file_to_guidelines, max_batch_size,
        max_guidelines_per_batch,
    )

    # Re-number batch IDs after compaction
    for i, b in enumerate(batches, 1):
        b["batch_id"] = f"batch_{i:03d}"

    logger.info(
        "Group-profile biclique cover (post-compact): %d batches "
        "covering %d edges",
        len(batches), total_edges,
    )

    return batches


def _compact_batches(
    batches: List[Dict[str, Any]],
    file_to_guidelines: Dict[str, Set[str]],
    max_batch_size: int,
    max_guidelines_per_batch: int,
) -> List[Dict[str, Any]]:
    """Merge compatible batches to reduce total count.

    Two merge rules are applied iteratively until convergence:

    1. **Same guideline set** — batches whose guideline lists are
       identical can merge their file lists (all files already match all
       the guidelines).  The merged file list is re-chunked by
       *max_batch_size*.
    2. **Same file set** — batches whose file lists are identical can
       merge their guideline lists.  Re-chunked by
       *max_guidelines_per_batch*.
    """
    changed = True
    while changed:
        changed = False

        # ── Pass A: merge files for identical guideline sets ──────────
        g_groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        for b in batches:
            g_groups[tuple(sorted(b["guidelines"]))].append(b)

        new_batches: List[Dict[str, Any]] = []
        for g_key, group in g_groups.items():
            all_files = sorted(
                set(f for b in group for f in b["files"])
            )
            guidelines = list(g_key)

            # Verify biclique: all files must match all guidelines
            valid = all(
                all(g in file_to_guidelines.get(f, set())
                    for g in guidelines)
                for f in all_files
            )
            if valid:
                for fi in range(0, len(all_files), max_batch_size):
                    f_chunk = all_files[fi : fi + max_batch_size]
                    new_batches.append({
                        "batch_id": "",
                        "files": f_chunk,
                        "guidelines": guidelines,
                        "file_to_guidelines": {
                            f: list(guidelines) for f in f_chunk
                        },
                    })
            else:
                new_batches.extend(group)

        if len(new_batches) < len(batches):
            changed = True
        batches = new_batches

        # ── Pass B: merge guidelines for identical file sets ──────────
        f_groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        for b in batches:
            f_groups[tuple(sorted(b["files"]))].append(b)

        new_batches = []
        for f_key, group in f_groups.items():
            all_gs = sorted(
                set(g for b in group for g in b["guidelines"])
            )
            files = list(f_key)
            for gi in range(0, len(all_gs), max_guidelines_per_batch):
                g_chunk = all_gs[gi : gi + max_guidelines_per_batch]
                new_batches.append({
                    "batch_id": "",
                    "files": files,
                    "guidelines": g_chunk,
                    "file_to_guidelines": {
                        f: list(g_chunk) for f in files
                    },
                })

        if len(new_batches) < len(batches):
            changed = True
        batches = new_batches

    return batches


def _pack_file_groups(
    file_to_guidelines: Dict[str, Set[str]],
    max_batch_size: int,
) -> List[Dict[str, Any]]:
    """Pack files into groups of up to *max_batch_size* using greedy bin-packing.

    Files are sorted by guideline-count descending so the "heaviest" files
    are placed first.  For each file we try to add it to the group where
    adding it introduces the **fewest new guidelines** (minimum marginal
    union growth), breaking ties by highest overlap then smallest file
    count.  This keeps the per-group guideline union tight, reducing the
    number of guideline chunks produced by the subsequent split phase.

    Each group tracks the per-file guideline sets so downstream phases
    can build precise applicability maps.

    Returns a list of ``{"files": [...], "guidelines": set(...),
    "file_guidelines": {file: set(...)}}``.
    """
    # Sort files by number of guidelines (descending) so heavy files land first,
    # then by path for determinism.
    sorted_files = sorted(
        file_to_guidelines.items(),
        key=lambda x: (-len(x[1]), x[0]),
    )

    groups: List[Dict[str, Any]] = []

    for file_path, guidelines in sorted_files:
        best_idx = -1
        best_new = float("inf")
        best_overlap = -1
        best_file_count = float("inf")

        for idx, group in enumerate(groups):
            if len(group["files"]) >= max_batch_size:
                continue
            new_count = len(guidelines - group["guidelines"])
            overlap = len(guidelines & group["guidelines"])
            file_count = len(group["files"])
            if (new_count < best_new
                or (new_count == best_new and overlap > best_overlap)
                or (new_count == best_new and overlap == best_overlap
                    and file_count < best_file_count)):
                best_idx = idx
                best_new = new_count
                best_overlap = overlap
                best_file_count = file_count

        if best_idx >= 0:
            groups[best_idx]["files"].append(file_path)
            groups[best_idx]["guidelines"] |= guidelines
            groups[best_idx]["file_guidelines"][file_path] = guidelines
        else:
            groups.append({
                "files": [file_path],
                "guidelines": set(guidelines),
                "file_guidelines": {file_path: guidelines},
            })

    logger.info(
        "File packing: %d files -> %d groups (max %d files/group)",
        len(file_to_guidelines), len(groups), max_batch_size,
    )
    return groups


def _compute_statistics(batches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics for the batch set."""

    file_counts = [len(b["files"]) for b in batches]
    all_files: Set[str] = set()
    all_guidelines: Set[str] = set()
    total_pairs = 0
    for b in batches:
        all_files.update(b["files"])
        all_guidelines.update(b["guidelines"])
        f2g = b.get("file_to_guidelines", {})
        if f2g:
            total_pairs += sum(len(gls) for gls in f2g.values())
        else:
            total_pairs += len(b["files"]) * len(b["guidelines"])

    return {
        "total_batches": len(batches),
        "total_files": len(all_files),
        "total_guidelines": len(all_guidelines),
        "total_file_guideline_pairs": total_pairs,
        "avg_files_per_batch": round(sum(file_counts) / len(batches), 2) if batches else 0,
        "avg_guidelines_per_batch": round(
            sum(len(b["guidelines"]) for b in batches) / len(batches), 2
        ) if batches else 0,
        "min_files": min(file_counts, default=0),
        "max_files": max(file_counts, default=0),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    input_path: str,
    output_path: str,
    max_batch_size: int = 10,
    max_guidelines_per_batch: int = 10,
) -> None:
    """Load prepare-review JSON and produce optimised review batches."""

    file_to_guidelines = _load_prepare_json(input_path)

    if not file_to_guidelines:
        logger.warning("No files in input — writing empty batch output")

    batches = _biclique_cover(
        file_to_guidelines, max_batch_size, max_guidelines_per_batch
    )

    for b in batches:
        b["file_count"] = len(b["files"])
        b["guideline_count"] = len(b["guidelines"])

    output = {
        "configuration": {
            "max_batch_size": max_batch_size,
            "max_guidelines_per_batch": max_guidelines_per_batch,
        },
        "statistics": _compute_statistics(batches),
        "batches": batches,
    }

    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
    except OSError as exc:
        raise OSError(f"Failed to write output file '{output_path}': {exc}") from exc

    logger.info(
        "Wrote %d batches (%d files, %d guidelines) to %s",
        output["statistics"]["total_batches"],
        output["statistics"]["total_files"],
        output["statistics"]["total_guidelines"],
        output_path,
    )

    return output


def _emit_sql(batches_output: dict, sql_path: str) -> None:
    """Write SQL INSERT statements for gk_batches from batch output."""
    lines: list[str] = []
    lines.append(
        "CREATE TABLE IF NOT EXISTS gk_batches (\n"
        "    batch_id TEXT PRIMARY KEY,\n"
        "    files TEXT NOT NULL DEFAULT '[]',\n"
        "    guidelines TEXT NOT NULL DEFAULT '[]',\n"
        "    file_to_guidelines TEXT NOT NULL DEFAULT '{}',\n"
        "    status TEXT DEFAULT 'pending'\n"
        ");"
    )
    for batch in batches_output.get("batches", []):
        bid = batch["batch_id"].replace("'", "''")
        files = json.dumps(batch["files"], ensure_ascii=False).replace("'", "''")
        guidelines = json.dumps(batch["guidelines"], ensure_ascii=False).replace("'", "''")
        ftg = json.dumps(batch["file_to_guidelines"], ensure_ascii=False).replace("'", "''")
        lines.append(
            f"INSERT OR REPLACE INTO gk_batches "
            f"(batch_id, files, guidelines, file_to_guidelines, status) VALUES "
            f"('{bid}', '{files}', '{guidelines}', '{ftg}', 'pending');"
        )
    out = Path(sql_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(
        "Wrote SQL inserts (%d batches) to %s",
        len(batches_output.get("batches", [])),
        sql_path,
    )


def _load_to_db(batches_output: dict, db_path: str) -> None:
    """Load batches directly into a SQLite database.

    Clears any existing rows in gk_batches before inserting to avoid
    stale data from prior runs.  All work happens in a single
    transaction so partial failures leave the table unchanged.
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

        conn.execute(
            "CREATE TABLE IF NOT EXISTS gk_batches (\n"
            "    batch_id TEXT PRIMARY KEY,\n"
            "    files TEXT NOT NULL DEFAULT '[]',\n"
            "    guidelines TEXT NOT NULL DEFAULT '[]',\n"
            "    file_to_guidelines TEXT NOT NULL DEFAULT '{}',\n"
            "    status TEXT DEFAULT 'pending'\n"
            ")"
        )
        conn.execute("DELETE FROM gk_batches")

        rows = [
            (
                batch["batch_id"],
                json.dumps(batch["files"], ensure_ascii=False),
                json.dumps(batch["guidelines"], ensure_ascii=False),
                json.dumps(batch["file_to_guidelines"], ensure_ascii=False),
                "pending",
            )
            for batch in batches_output.get("batches", [])
        ]
        conn.executemany(
            "INSERT INTO gk_batches "
            "(batch_id, files, guidelines, file_to_guidelines, status) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        logger.info(
            "Loaded %d batches into %s", len(rows), db_path
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch prepare-review output into optimised review batches.",
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to prepare_review.py output JSON.",
    )
    parser.add_argument(
        "--output", required=True, help="Path to write batches JSON output",
    )
    parser.add_argument(
        "--max-batch-size",
        type=int,
        default=10,
        help="Maximum files per batch (default: 10)",
    )
    parser.add_argument(
        "--max-guidelines-per-batch",
        type=int,
        default=10,
        help="Maximum guidelines per batch (default: 10)",
    )
    parser.add_argument(
        "--emit-sql",
        default=None,
        help="Path to write SQL INSERT statements for gk_batches. "
             "The agent can execute this file directly via the sql tool.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to an existing SQLite database file. When provided, "
             "batches are loaded directly into the gk_batches table, "
             "bypassing the need for --emit-sql file loading.",
    )
    args = parser.parse_args()

    if args.max_batch_size < 1:
        parser.error("--max-batch-size must be at least 1")
    if args.max_guidelines_per_batch < 1:
        parser.error("--max-guidelines-per-batch must be at least 1")

    try:
        result = run(
            input_path=args.input,
            output_path=args.output,
            max_batch_size=args.max_batch_size,
            max_guidelines_per_batch=args.max_guidelines_per_batch,
        )
        if args.emit_sql:
            _emit_sql(result, args.emit_sql)
        if args.db:
            _load_to_db(result, args.db)
    except (ValueError, FileNotFoundError, OSError) as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
