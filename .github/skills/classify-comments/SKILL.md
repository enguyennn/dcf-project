---
name: classify-comments
description: Deterministic scripts for the replay analysis classification pipeline. Includes merge_violations.py (Steps 1-2), group_comments.py (Step 3 Phase 1), and merge_classifications.py (Phase 3 + Steps 4-6). Use this skill in the GatekeeperReplayAnalyzer agent.
---

# Classify Comments Skill

Scripts for the deterministic stages of the replay analysis pipeline.

## Pipeline

```
merge_violations.py    -->  group_comments.py   -->  [sub-agents]  -->  merge_classifications.py
(Steps 1-2: merge)         (Phase 1: batch)         (Phase 2: LLM)     (Phase 3 + Steps 4-6: reports)
```

## Scripts

### merge_violations.py — Steps 1 & 2

Loads per-iteration `final-review.json` reports, merges all violations, and deduplicates by `(file_name, startline, guideline)` keeping the earliest iteration.

```bash
python .github/skills/classify-comments/scripts/merge_violations.py \
  --iteration-dir <replay_output_dir> \
  --output <all_violations.json> \
  [--summary <merge_summary.json>]
```

| Argument | Required | Description |
|---|---|---|
| `--iteration-dir` | Yes* | Directory containing `iteration-*/final-review.json` subdirectories |
| `--files` | Yes* | Alternative: explicit list of `final-review.json` paths |
| `--output` | Yes | Path to write deduplicated violations JSON array |
| `--summary` | No | Path to write merge summary JSON |

*Use `--iteration-dir` or `--files`, not both.

### group_comments.py — Step 3 Phase 1

Groups PR comments by file basename, pairs each group with its file's violations, and splits large groups into batches for parallel sub-agent classification.

```bash
python .github/skills/classify-comments/scripts/group_comments.py \
  --comments <pr_comments.json> \
  --violations <all_violations.json> \
  --output <classify-batches.json> \
  [--max-per-batch 8]
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--comments` | Yes | — | Path to PR comments JSON array |
| `--violations` | Yes | — | Path to deduplicated violations JSON |
| `--output` | Yes | — | Path to write classification batches JSON |
| `--max-per-batch` | No | 8 | Max comments per batch |

### merge_classifications.py — Phase 3 + Steps 4-6

Merges per-batch sub-agent classification results, auto-MISSes unmatched comments, computes coverage metrics, identifies gap patterns, and generates the final JSON and Markdown reports.

```bash
python .github/skills/classify-comments/scripts/merge_classifications.py \
  --batches <classify-batches.json> \
  --results <classifications_dir> \
  --comments <pr_comments.json> \
  --violations <all_violations.json> \
  [--merge-summary <merge_summary.json>] \
  --output-dir <output_dir> \
  [--pr-url <url>] [--pr-title <title>] [--platform <platform>]
```

| Argument | Required | Description |
|---|---|---|
| `--batches` | Yes | Path to `classify-batches.json` (from group_comments.py) |
| `--results` | Yes | Directory containing `classify-*.json` sub-agent result files |
| `--comments` | Yes | Path to original PR comments JSON |
| `--violations` | Yes | Path to deduplicated violations JSON |
| `--merge-summary` | No | Path to merge summary (from merge_violations.py) |
| `--output-dir` | Yes | Directory to write `replay-analysis.json` and `replay-analysis-report.md` |
| `--pr-url` | No | PR URL for the report |
| `--pr-title` | No | PR title for the report |
| `--platform` | No | Platform name (`azure-devops` or `github`) |

**Expected results directory**: Each sub-agent saves its JSON array output to `classify-NNN.json` in the results directory (matching batch_id from batches JSON).

### merge_iteration_analyses.py — Per-Iteration Report Merge

Merges per-iteration `replay-analysis.json` files (produced by parallel per-iteration analysis) into a unified report with the same schema as the whole-PR analysis.

```bash
python .github/skills/classify-comments/scripts/merge_iteration_analyses.py \
  --iteration-dir <replay_output_dir> \
  --output-dir <output_dir> \
  [--pr-url <url>] [--pr-title <title>] [--platform <platform>]
```

| Argument | Required | Description |
|---|---|---|
| `--iteration-dir` | Yes | Directory containing `iteration-*/replay-analysis.json` subdirectories |
| `--output-dir` | Yes | Directory to write merged `replay-analysis.json` and `replay-analysis-report.md` |
| `--pr-url` | No | PR URL for the report |
| `--pr-title` | No | PR title for the report |
| `--platform` | No | Platform name (`azure-devops` or `github`) |

The script:
- Concatenates `comment_classifications` from all iterations (no dedup — comments are unique per iteration)
- Sums classification counts and recalculates percentages
- Merges gap analyses (missed_by_type, missed_by_file, suggested_guidelines)
- Produces unified `replay-analysis.json` and `replay-analysis-report.md`

## Determinism Guarantees

All three scripts are fully deterministic:
- Iterations sorted by ID, violations sorted by `(basename, startline)`
- Comments sorted by `(basename, line_number)`, batches by alphabetical file order
- Classifications sorted by `(iteration_id, basename, line_number)`
- Same inputs always produce byte-identical output (verified by SHA256)