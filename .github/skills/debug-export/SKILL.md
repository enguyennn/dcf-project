---
name: debug-export
description: Export intermediate Gatekeeper pipeline state after each stage to enable cross-run comparison and determinism analysis. Use this skill when the --debug flag is passed to the Gatekeeper orchestrator.
---

# Gatekeeper Pipeline Debug Export

## Purpose

Export intermediate pipeline state after each Gatekeeper stage to enable cross-run comparison and determinism analysis. All debug files use **sorted, deterministic** ordering.

## When to Use

This skill is invoked by the Gatekeeper orchestrator when the user passes the `--debug` flag. It is NOT invoked during normal review runs.

## Inputs

- `output_dir` (string, required): Directory to write debug files to (e.g., `output/replay/iteration-5/`)

## Debug File Specifications

### After Stage 0 (Prepare)

`prepare.json` already captures the full pipeline state for this stage — guidelines discovered, file-to-guideline mappings, diff contents (if diff mode), errors, and warnings. No separate debug export needed.

Reference: `{output_dir}/prepare.json`

### After Stage 1 (Batch)
Write `{output_dir}/debug/stage-1-batches.json`:
```json
[{"batch_id": "batch_001", "files": ["a.cs", "b.cs"], "guidelines": ["guideline1/SKILL.md"]}]
```
`files` and `guidelines` sorted alphabetically within each batch. Batches sorted by `batch_id`.

### After Stage 2 (Review)
Write `{output_dir}/debug/stage-2-reviews.json` — a per-batch summary with **both** violations and non-violations for full coverage auditing:
```json
[
  {
    "batch_id": "batch_001",
    "assignments_total": 50,
    "assignments_reported": 50,
    "violations_count": 3,
    "violations": [
      {"file_name": "src/foo.cs", "startline": "42", "endline": "45", "guideline": "some-guideline/SKILL.md", "severity": "High", "violation": "..."}
    ],
    "non_violations_count": 47,
    "non_violations": [
      {"file_name": "src/foo.cs", "guideline": "other-guideline/SKILL.md", "reason": "No violations detected..."}
    ]
  }
]
```

Field definitions:
- `assignments_total`: Number of `(file, guideline)` pairs assigned to this batch (from `file_to_guidelines` in `batches.json`). This is the total work the reviewer was asked to do.
- `assignments_reported`: Number of `(file, guideline)` pairs that appear in either `violations` or `non_violations`. Must equal `assignments_total` — any gap indicates the reviewer silently skipped work.
- `violations`: Array of violation objects. Sorted by `(file_name, startline, guideline)`.
- `non_violations`: Array of non-violation objects, one per `(file, guideline)` pair that was evaluated and found clean. Sorted by `(file_name, guideline)`.

**Coverage audit**: If `assignments_reported < assignments_total`, the debug export MUST log a warning listing the missing `(file, guideline)` pairs. This catches reviewer truncation that silently drops guidelines.

## Pipeline Debug Summary Block

When debug mode is active, include this block in the response:
```
=== PIPELINE DEBUG SUMMARY ===
Mode: {file|diff}
Guidelines discovered: {count}
Review items: {count}
Changed files (diff mode): {count or "N/A"}
Batches created: {count}
Total violations: {count}
Total non-violations: {count}
Debug files written to: {output_dir}/debug/
=== END PIPELINE DEBUG SUMMARY ===
```
