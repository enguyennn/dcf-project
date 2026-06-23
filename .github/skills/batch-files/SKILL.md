---
name: batch-files
description: Groups review items into optimized batches for parallel code review. Takes prepare_review.py output and produces batches using a biclique cover algorithm.
---

# Batch Files Skill

See [`scripts/batch_files.py`](scripts/batch_files.py) for the implementation.

## When to Use

Use this skill **after `prepare_review.py`** produces its output JSON. The prepare script maps each file to its applicable guidelines. This skill takes that mapping and groups items into optimally sized batches for parallel code review.

## How to Invoke

```bash
python .github/skills/batch-files/scripts/batch_files.py \
  --input <prepare.json> \
  --output <batches.json> \
  [--max-batch-size 10] \
  [--max-guidelines-per-batch 10]
```

### Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--input` | Yes | — | Path to `prepare_review.py` output JSON |
| `--output` | Yes | — | Path to write the batches JSON output |
| `--max-batch-size` | No | `10` | Maximum number of files per batch |
| `--max-guidelines-per-batch` | No | `10` | Maximum number of guidelines per batch |

## Input Format

The input JSON is the output of `prepare_review.py`. The script reads the `items` array, where each item has `filename` and `guidelines`:

```json
{
  "items": [
    {
      "filename": "src/auth.cs",
      "guidelines": ["blocking-call-in-async-method/SKILL.md", "catch-all-exception/SKILL.md"]
    }
  ]
}
```

## Output Format

```json
{
  "configuration": {
    "max_batch_size": 5,
    "max_guidelines_per_batch": 10
  },
  "statistics": {
    "total_batches": 3,
    "total_files": 25,
    "total_guidelines": 4,
    "avg_files_per_batch": 8.3,
    "avg_guidelines_per_batch": 2.0,
    "min_files": 5,
    "max_files": 10
  },
  "batches": [
    {
      "batch_id": "batch_001",
      "files": ["src/auth.cs", "src/utils.cs"],
      "guidelines": ["blocking-call-in-async-method/SKILL.md", "catch-all-exception/SKILL.md"],
      "file_to_guidelines": {
        "src/auth.cs": ["blocking-call-in-async-method/SKILL.md", "catch-all-exception/SKILL.md"],
        "src/utils.cs": ["catch-all-exception/SKILL.md"]
      },
      "file_count": 2,
      "guideline_count": 2
    }
  ]
}
```

## Example Pipeline Usage

```bash
# 1. Prepare review items (config, guidelines, file matching)
python .github/skills/prepare-review/scripts/prepare_review.py \
  --output-dir output/ --mode file --output output/prepare.json

# 2. Batch items into review groups
python .github/skills/batch-files/scripts/batch_files.py \
  --input output/prepare.json \
  --output output/batches.json \
  --max-batch-size 10 \
  --max-guidelines-per-batch 10
```
