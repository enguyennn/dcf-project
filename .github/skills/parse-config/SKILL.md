---
name: parse-config
description: Parses and validates gkpconfig.yml for the Gatekeeper pipeline. Resolves paths, validates skills_root exists with SKILL.md subdirectories, and returns a JSON summary with repo_root, skills_root, folder_rules, skills count, and validation status.
---

# Parse Config Skill

Parses `gkpconfig.yml`, resolves paths, validates that `skills_root` contains guideline skills, and returns a structured JSON result.

## When to Use

Use this skill at the **start of any Gatekeeper pipeline** (Replay, Review, CheckStability) to load and validate configuration instead of manual YAML parsing.

## How to Invoke

```bash
python .github/skills/parse-config/scripts/parse_config.py \
  --config .github/gatekeeper/gkpconfig.yml \
  --output output/replay/config.json
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--config` | Yes | Path to gkpconfig.yml |
| `--output` | No | Output file path. If omitted, prints JSON to stdout. |

### Exit Codes

- `0`: Config is valid
- `1`: Config has errors (missing skills_root, etc.)

## Output Format

```json
{
  "config_path": "/abs/path/to/.github/gatekeeper/gkpconfig.yml",
  "repo_root": "/abs/path/to/src",
  "skills_root": "/abs/path/to/.github/skills",
  "folder_rules": { "**": { "guidelines": ["**"] } },
  "skills_count": 209,
  "skill_names": ["catch-all-exception-swallowing", "..."],
  "errors": [],
  "warnings": [],
  "valid": true
}
```
