---
name: resolve-knowledge-docs
description: "Deterministic resolver for knowledge-context skill documents. Parses SKILL.md routing tables, matches changed files against path patterns, and outputs pre-resolved child document paths for the reviewer."
---

# resolve-knowledge-docs

Deterministic Python script that resolves which child `.md` files from knowledge-context skills are relevant for a given set of changed files.

## Usage

```bash
python resolve_knowledge_docs.py --skills-dir <path> --changed-files '<json_array>'
```

## Input

- `--skills-dir`: Path to the directory containing skill subdirectories (each with a `SKILL.md`)
- `--changed-files`: JSON array of changed file paths (relative to repo root)

## Output

JSON object to stdout:

```json
{
  "skill_name": {
    "type": "knowledge-context" | "knowledge-context-routed",
    "skill_dir": "/path/to/skill_name",
    "resolved_docs": ["/path/to/SKILL.md", "/path/to/domain/file.md"],
    "matches": [
      {"changed_file": "src/Foo.cs", "pattern": "Foo", "area_code": "[EXT]", "doc": "domain/vm-extensions.md"}
    ]
  }
}
```

## Supported Formats

| `metadata.format` | Behavior |
|---|---|
| `knowledge-context` | Returns just the SKILL.md (self-contained) |
| `knowledge-context-routed` | Parses routing tables, matches changed files, returns SKILL.md + matched child docs |
| *(absent)* | Skipped (regular guideline skill) |
