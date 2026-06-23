---
name: prepare-review
description: Prepares review items and dispatch plan for the Gatekeeper code review pipeline. Parses the reviewer-centric config, runs guideline discovery and file matching for guidelines_reviewer, matches specialist reviewer scope_globs against repo files, and outputs both a review items JSON and a dispatch plan JSON.
---

# Prepare Review Skill

See [`scripts/prepare_review.py`](scripts/prepare_review.py) for the implementation.

## When to Use

Use this skill at the **start of the Gatekeeper pipeline** (Stage 0). It consolidates config parsing, reviewer config resolution, guideline discovery, specialist file matching, and diff extraction into a single script invocation.

## How to Invoke

```bash
python .github/skills/prepare-review/scripts/prepare_review.py \
  --output-dir <output_dir> \
  --mode file|diff \
  [--config <gkpconfig.yml>] \
  [--commit-range <base>..<head>] \
  [--staged] \
  [--untracked] \
  [--repo-path <path>] \
  [--output <output.json>] \
  [--db <session.db>]
```

### Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--output-dir` | Yes | — | Output directory for review artifacts |
| `--mode` | Yes | — | `file` for full scan, `diff` for change-based review |
| `--config` | No | auto-discover | Path to `gkpconfig.yml` |
| `--commit-range` | No | — | Git commit range for diff mode |
| `--staged` | No | — | Review staged changes (diff mode) |
| `--untracked` | No | — | Review untracked changes (diff mode) |
| `--repo-path` | No | from config | Override `repo_root` from config |
| `--output` | No | stdout | Output JSON file path |
| `--db` | No | — | SQLite database path — loads review items into `gk_review_items` and the dispatch plan into `gk_dispatch_plan` |

## Config Format

The script expects the new reviewer-centric `gkpconfig.yml`:

```yaml
repo_root: .
reviewers:
  guidelines_reviewer:
    model: claude-sonnet-4
    guidelines_root: .github/skills
    folder_rules:
      '**':
        guidelines: ['**']
  critic:
    model: claude-opus-4.6
  security:
    model: claude-sonnet-4
  reliability:
    model: claude-sonnet-4
```

## Behavior

1. **Parse config** — load `gkpconfig.yml`, resolve reviewer configs
2. **For each reviewer**:
   - **guidelines_reviewer**: discover guidelines from `guidelines_root`, match files using scope globs and folder rules, load into SQL via `--db`
   - **specialist reviewers**: discover `Octane.*Reviewer.agent.md` files in `agents/` directory, match `scope_globs` against repo files (or changed files in diff mode)
3. **Unavailable specialists**: if a configured specialist has no matching `Octane.*Reviewer.agent.md` file, it is marked as `available: false` in the dispatch plan
4. **Output** — `prepare.json` (review items), dispatch plan written to `gk_dispatch_plan` SQL table via `--db`

## Dispatch Plan Format

```json
{
  "reviewers": [
    {
      "name": "guidelines_reviewer",
      "type": "guidelines",
      "model": "claude-sonnet-4",
      "guidelines_root": "/abs/path/to/skills",
      "items_count": 42
    },
    {
      "name": "security",
      "type": "specialist",
      "model": "claude-sonnet-4",
      "reviewer_path": "/abs/path/agents/Octane.SecurityReviewer.agent.md",
      "files": ["src/a.ts", "src/b.ts"],
      "available": true
    },
    {
      "name": "missing_reviewer",
      "type": "specialist",
      "model": "claude-opus-4.6",
      "reviewer_path": null,
      "files": [],
      "available": false,
      "error": "Reviewer agent file not found: ..."
    }
  ]
}
```
