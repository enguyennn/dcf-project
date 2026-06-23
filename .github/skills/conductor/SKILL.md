---
name: conductor
description: >
  Conductor workflow that replays a pull request through the Gatekeeper code review
  pipeline to measure what percentage of human reviewer comments could have been caught
  automatically. Use when you want to run a structured, multi-agent replay with a visual
  DAG, cost tracking, and checkpoint/resume on failure.
license: MIT
metadata:
  author: Azure Core Team
  version: "1.0.0"
---

# Gatekeeper Replay Workflow

Conductor workflow version of the Gatekeeper Replay prompt. Replays a PR through the
full code review pipeline and classifies each reviewer comment as CAUGHT, PARTIAL,
MISSED, or OUT_OF_SCOPE.

## When to Use

- **Measuring Gatekeeper coverage** on historical PRs
- **Batch replay** across multiple PRs (use ReplayHarness for batch)
- **Visual monitoring** via the `--web` dashboard
- **Cost tracking** to understand per-iteration token usage

## Prerequisites

- **Conductor ≥ 0.1.11** required (for `--workspace-instructions`). Older versions reject the flag with `No such option: --workspace-instructions` — run `conductor update` to upgrade.
- [Conductor CLI](https://github.com/microsoft/conductor) installed (`uv tool install conductor`)
- `gkpconfig.yml` configuration file in the repository
- ADO PAT or GitHub token for fetching PR metadata and comments
- Python 3.10+ with dependencies for the skill scripts

## Usage

> **Resolve to an absolute path first.** Examples below show `replay.yaml` for brevity, but `--workspace-instructions` requires running conductor from the **target repo root** (so it can discover *that* repo's `AGENTS.md`, `.github/copilot-instructions.md`, `CLAUDE.md`). Set `$WORKFLOW` to the installed plugin's absolute path before invoking. Octane plugins install under `$HOME/.copilot/installed-plugins/octane/`.

```bash
# Set once per shell; resolve to your installed plugin's absolute path.
WORKFLOW="$HOME/.copilot/installed-plugins/octane/octane-gatekeeper/skills/conductor/assets/replay.yaml"

# Standard run
conductor run --workspace-instructions "$WORKFLOW" \
  --input pr_link="https://dev.azure.com/org/project/_git/repo/pullrequest/12345" \
  --input config_path=".github/gatekeeper/gkpconfig.yml" \
  --input output_dir="output/replay"

# With web dashboard
conductor run --workspace-instructions "$WORKFLOW" --web \
  --input pr_link="https://dev.azure.com/org/project/_git/repo/pullrequest/12345"

# Quiet mode (lifecycle + routing only)
conductor -q run --workspace-instructions "$WORKFLOW" \
  --input pr_link="https://dev.azure.com/org/project/_git/repo/pullrequest/12345"

# With worktree prefix to avoid collisions
conductor run --workspace-instructions "$WORKFLOW" \
  --input pr_link="..." \
  --input worktree_prefix="cd-"

# Dry run (preview execution plan)
conductor run --workspace-instructions "$WORKFLOW" --dry-run \
  --input pr_link="..."
```

> **Run conductor from the target repository root.** `--workspace-instructions` discovers the user's repo conventions by walking from the current working directory up to the git root. Do not `cd` into the installed skill directory, or conductor will discover Octane's own conventions instead of the target repo's.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `pr_link` | Yes | — | URL to the pull request (Azure DevOps or GitHub) |
| `config_path` | No | `.github/gatekeeper/gkpconfig.yml` | Path to gkpconfig.yml |
| `output_dir` | No | `output/replay` | Base output directory |
| `worktree_prefix` | No | `""` | Prefix for worktree directory names |

## Architecture

```
parse_config (script) → fetch_iterations (script)
  → setup_bridge (agent) → create_worktrees (script)
    → review_iterations (for_each) → remove_worktrees (script)
      → fetch_comments (script) → analyze_iterations (for_each)
        → merge_analyses (script) → reporter (agent) → $end
```

- **5 script steps**: deterministic Python scripts for config, iterations, comments, worktrees, merging
- **1 bridge agent**: converts script JSON to typed output for for_each groups
- **2 for_each groups**: parallel Gatekeeper review + parallel comment analysis
- **1 reporter agent**: final summary presentation

## Output

| File | Description |
|------|-------------|
| `{output_dir}/replay-analysis.json` | Unified machine-readable analysis |
| `{output_dir}/replay-analysis-report.md` | Unified human-readable report |
| `{output_dir}/run-manifest.json` | Execution metadata and summary |
| `{output_dir}/iteration-{id}/final-review.json` | Per-iteration Gatekeeper results |
| `{output_dir}/iteration-{id}/replay-analysis.json` | Per-iteration analysis |
| `{output_dir}/iteration-{id}/replay-analysis-report.md` | Per-iteration report |
