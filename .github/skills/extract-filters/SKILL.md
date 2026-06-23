---
name: extract-filters
description: Extracts filter specifications (glob patterns + content regex) from guideline SKILL.md frontmatter. Use this skill at the start of the filter stage to deterministically produce filter output without LLM inference.
---

# Extract Filters Skill

See [`scripts/extract_filters.py`](scripts/extract_filters.py) for the implementation.

## When to Use

Use this skill at the **start of Stage 1 (filtering)** in the Gatekeeper pipeline. It replaces the LLM-based frontmatter extraction with a deterministic Python script, ensuring identical filter output across runs.

In **diff mode**, call this script first to extract all filter specs, then dispatch the GatekeeperFilter agent to assess which guidelines are relevant to the diff.

## How to Invoke

```bash
python .github/skills/extract-filters/scripts/extract_filters.py \
  --skills-dir <path_to_skills> \
  [--output <filter_output.json>]
```

### Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--skills-dir` | Yes | — | Directory containing guideline skill subdirectories with SKILL.md files |
| `--output` | No | stdout | Path to write the filter output JSON file |

### Exit Codes

- `0`: Success
- `1`: Fatal error (skills directory not found, I/O error)

### Prerequisites

- **Python 3.6+**
- **PyYAML** recommended (falls back to minimal built-in parser)

## Behavior

1. Walks `--skills-dir` for subdirectories containing `SKILL.md`
2. Parses YAML frontmatter from each `SKILL.md`
3. **Skips** non-guideline skills (requires `metadata.type: guideline`)
4. Extracts `metadata.scope` → `glob_patterns`
5. Extracts `metadata.content_regex` → `content_regex` (defaults to `[]` if absent)
6. Validates all regex patterns are compilable (`re.compile`)
7. Deduplicates and sorts both arrays alphabetically
8. Outputs JSON keyed by guideline directory name

Warnings are logged to stderr for:
- Missing or malformed frontmatter
- Empty `metadata.scope`
- Invalid regex patterns (skipped individually, valid patterns still included)
- Frontmatter `name` not matching directory name

## Output Format

The output JSON is an object keyed by guideline name. Each value contains:

- `glob_patterns`: array of glob pattern strings to match files
- `content_regex`: array of regex strings for content-level filtering

```json
{
  "blocking-call-in-async-method": {
    "glob_patterns": ["**/*.cs"],
    "content_regex": ["async\\s+Task", "await\\s+"]
  },
  "descriptive-test-method-names": {
    "glob_patterns": ["**/*Test.cs", "**/*Tests.cs"],
    "content_regex": []
  }
}
```

This format is directly compatible with the [batch-files](../batch-files/SKILL.md) skill input format.

## Back-Populating content_regex

A companion script [`populate_content_regex.py`](scripts/populate_content_regex.py) can back-populate `content_regex` into existing SKILL.md frontmatter by analyzing the `## Detection Instructions` section for explicit regex patterns and code tokens.

```bash
python .github/skills/extract-filters/scripts/populate_content_regex.py \
  --skills-dir <path_to_skills> \
  [--dry-run]
```

See the script's `--help` for details.

## Example Pipeline Usage

```bash
# 1. Extract filter specs from guideline frontmatter (deterministic)
python .github/skills/extract-filters/scripts/extract_filters.py \
  --skills-dir .github/skills \
  --output output/filters.json

# 2. Batch files for review
python .github/skills/batch-files/scripts/batch_files.py \
  --input output/filters.json \
  --output output/batches.json \
  --repo-path .
```
