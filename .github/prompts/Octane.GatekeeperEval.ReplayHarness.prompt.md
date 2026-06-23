---
agent: GatekeeperEval
description: Run the Gatekeeper Replay workflow against multiple PRs in parallel and produce a comparison report.
model: Claude Opus 4.6 (copilot)
---

# Gatekeeper Replay Harness

## Inputs

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `PR Links` | list of strings | **yes** | Azure DevOps PR URLs to replay. Format: `https://msazure.visualstudio.com/{org}/{project}/_git/{repo}/pullrequest/{id}` |
| `Config Path` | string | conditional | Path to an existing `.gkpconfig` or `gkpconfig.yml` file. If provided, `Repo Path` and `Guidelines Path` are read from the config and do not need to be specified separately. |
| `Repo Path` | string | conditional | Absolute path to a local clone of the target repository. Required if `Config Path` is not provided. |
| `Guidelines Path` | string | conditional | Absolute path to a directory of `.md` anti-pattern guideline files. Required if `Config Path` is not provided. |
| `Output Root` | string | optional | Directory for all outputs. Default: `./replay-harness-output` |
| `Replay Prompt Path` | string | optional | Path to `Octane.GatekeeperEval.Replay.prompt.md`. Default: auto-discover under `$AGENCY_PLUGIN_DIR/prompts/`. |

## Primary Directive

Run the Gatekeeper Replay workflow against every PR in the input list **in parallel**, using a shared guideline library, and produce a single comparison report. The entire process must complete **without human intervention** — no interactive prompts, no manual file management.

## Constraints

1. **No user interaction.** Every sub-agent must run autonomously. If a sub-agent fails, retry it once; if it fails again, record the failure and continue with the remaining PRs.
2. **No working-tree conflicts.** Each parallel replay must operate in its own isolated git working tree (via `git worktree`). Never run two replays against the same working directory.
3. **Deterministic output paths.** All outputs go under `{Output Root}/{pr_number}/`. No two runs may clobber each other's files.
4. **Restore repo state.** After all replays complete (or fail), all worktrees must be removed and the main repo returned to its original HEAD.

---

## Workflow

### Phase 0 — Validate & Initialize

1. **Parse PR links.** Extract `{pr_number}` from each URL.

2. **Resolve configuration.**
   - If `Config Path` is provided, parse the gkpconfig file (YAML) and extract `repo_root` as `{Repo Path}` and `guidelines_root` as `{Guidelines Path}`. Preserve any additional config fields (e.g., `folder_rules`) for use in Phase 2.
   - If `Config Path` is not provided, `Repo Path` and `Guidelines Path` must both be specified. Error if either is missing.

3. **Validate paths.**
   - `Repo Path` exists and is a git repository (`git -C {Repo Path} rev-parse --git-dir`).
   - `Guidelines Path` exists and contains at least one `.md` file.
   - Resolve `Replay Prompt Path`. If not provided, search for `Octane.GatekeeperEval.Replay.prompt.md` under `$AGENCY_PLUGIN_DIR/prompts/`.

4. **Validate ADO authentication.** Attempt a lightweight ADO REST API call (e.g., fetch PR metadata for the first PR in the list). If it fails with an auth error, abort the entire run with a clear message indicating that a valid PAT (`AZURE_DEVOPS_PAT` env var) or `az login` session is required.

5. **Validate PR commits are reachable.** For each PR, verify the target and source commits exist in the local clone. If any are missing, report which PRs are affected and suggest running `git fetch` before retrying. Mark unreachable PRs as `failed` and continue with the rest.

6. **Count guidelines.** Report: "Found {N} guideline files in {Guidelines Path}."

7. **Create output root.** `mkdir -p {Output Root}`

8. **Create tracking tables.**

```sql
CREATE TABLE IF NOT EXISTS harness_runs (
    pr_number   TEXT PRIMARY KEY,
    pr_link     TEXT NOT NULL,
    worktree    TEXT,
    status      TEXT DEFAULT 'pending',   -- pending | worktree_ready | running | done | failed
    attempt     INTEGER DEFAULT 0,
    error       TEXT,
    started_at  TEXT,
    finished_at TEXT
);
```

6. **Insert rows** — one per PR.

```sql
INSERT INTO harness_runs (pr_number, pr_link)
VALUES ('{pr_number}', '{pr_link}');
```

7. **Save baseline ref.**
```
original_ref=$(git -C {Repo Path} rev-parse HEAD)
```

---

### Phase 1 — Create Worktrees

For each PR in the list, create an isolated worktree:

```bash
git -C {Repo Path} worktree add --detach {Output Root}/worktrees/{pr_number} HEAD
```

Update tracking:
```sql
UPDATE harness_runs
   SET worktree = '{Output Root}/worktrees/{pr_number}',
       status   = 'worktree_ready'
 WHERE pr_number = '{pr_number}';
```

If worktree creation fails for any PR, set `status = 'failed'` with the error message and continue with the remaining PRs.

---

### Phase 2 — Dispatch Parallel Replays

Query all ready PRs:

```sql
SELECT pr_number, pr_link, worktree
  FROM harness_runs
 WHERE status = 'worktree_ready';
```

For **every** ready PR, first generate a temporary gkpconfig file at `{Output Root}/{pr_number}/gkpconfig.yml`:

```yaml
repo_root: {worktree}
guidelines_root: {Guidelines Path}
# Include any additional fields from the original Config Path (e.g., folder_rules)
```

Then dispatch a sub-agent **in parallel** using `mode: "background"`:

> **Sub-agent prompt (one per PR):**
>
> Follow the instructions in `{Replay Prompt Path}`.
>
> **Configuration:**
> - Use the gkpconfig file at `{Output Root}/{pr_number}/gkpconfig.yml`.
> - The input PR is `{pr_link}`.
> - Write all output to `{Output Root}/{pr_number}`.
>
> **Constraints:**
> - Do NOT prompt the user for any input. Run fully autonomously.
> - Do NOT skip any pipeline stages or simulate violations.
> - After replay is complete, do NOT attempt to restore git state — the harness manages worktree cleanup.

Update tracking:

```sql
UPDATE harness_runs
   SET status   = 'running',
       attempt  = attempt + 1,
       started_at = datetime('now')
 WHERE pr_number = '{pr_number}';
```

**Wait for all agents to complete.** Use `read_agent` with `wait: true` on each agent. As each completes:

- **On success:** Set `status = 'done'`, record `finished_at`.
- **On failure (first attempt):** Set `status = 'worktree_ready'` to trigger one retry in a follow-up dispatch round.
- **On failure (second attempt):** Set `status = 'failed'`, record the error.

**Retry round:** After all first-attempt agents finish, query for any PRs back in `worktree_ready` status and re-dispatch them (same sub-agent prompt). This gives each PR at most **two attempts**.

---

### Phase 3 — Aggregate Results

After all replays have completed or failed:

1. **Collect individual reports.** For each PR with `status = 'done'`, read:
   - `{Output Root}/{pr_number}/replay/replay-analysis.json`

2. **Build comparison table.** Extract from each report's `summary` block:

| PR | Title | Total Comments | Actionable | Caught | Partial | Missed | Out of Scope | Avoidable % | Caught % |
|----|-------|---------------|------------|--------|---------|--------|--------------|-------------|----------|
| {pr_number} | {pr_title} | {total} | {actionable} | {caught} | {partial} | {missed} | {oos} | {avoidable_pct} | {caught_pct} |
| ... | | | | | | | | | |
| **Totals** | | {sum} | {sum} | {sum} | {sum} | {sum} | {sum} | {weighted_avg} | {weighted_avg} |

   Weighted averages use each PR's `actionable_comments` as the weight:
   ```
   weighted_avoidable = Σ(avoidable_pct × actionable) / Σ(actionable)
   weighted_caught    = Σ(caught_pct × actionable)    / Σ(actionable)
   ```

3. **Build gap analysis.** Merge the `gaps.suggested_guidelines` arrays from all reports. Deduplicate by theme. Rank by total `missed_comment_count` across PRs.

4. **Record failed PRs.** List any PRs with `status = 'failed'` and their error messages.

5. **Write final report** to `{Output Root}/harness-report.md` with:
   - Run metadata (date, guideline count, PR count, guideline directory)
   - Comparison table
   - Per-PR detail links (path to each individual `replay-analysis-report.md`)
   - Aggregate gap analysis
   - Failures section (if any)

6. **Write machine-readable summary** to `{Output Root}/harness-report.json`:

```json
{
  "run_timestamp": "ISO-8601",
  "guidelines_path": "{Guidelines Path}",
  "guideline_count": 74,
  "pr_results": [
    {
      "pr_number": "12515472",
      "pr_link": "https://...",
      "pr_title": "...",
      "status": "done",
      "summary": { /* ...from replay-analysis.json... */ }
    }
  ],
  "aggregate": {
    "total_comments": 0,
    "total_actionable": 0,
    "total_caught": 0,
    "total_partial": 0,
    "total_missed": 0,
    "total_out_of_scope": 0,
    "weighted_avoidable_pct": 0.0,
    "weighted_caught_pct": 0.0
  },
  "failures": [],
  "gaps": {
    "suggested_guidelines": []
  }
}
```

---

### Phase 4 — Cleanup

1. **Remove all worktrees.**

```bash
git -C {Repo Path} worktree remove {Output Root}/worktrees/{pr_number} --force
```

   Do this for every PR in the tracking table (even failed ones).

2. **Prune worktree metadata.**

```bash
git -C {Repo Path} worktree prune
```

3. **Verify repo state.** Confirm the main repo is on `{original_ref}`:

```bash
git -C {Repo Path} rev-parse HEAD
```

   If not, restore it: `git -C {Repo Path} checkout {original_ref} --quiet`

4. **Present summary** to the user:
   - Total PRs attempted / succeeded / failed
   - Weighted avoidable %
   - Path to `harness-report.md`

---

## Output Structure

```
{Output Root}/
├── harness-report.md              # Human-readable comparison report
├── harness-report.json            # Machine-readable aggregate
├── 12515472/
│   └── replay/
│       ├── replay-analysis.json
│       ├── replay-analysis-report.md
│       └── iteration-{id}/
│           └── final-review.json
├── 12627803/
│   └── replay/
│       └── ...
├── ...
└── worktrees/                     # Temporary — removed in Phase 4
    ├── 12515472/                  # git worktree for PR 12515472
    ├── 12627803/
    └── ...
```

---

## Error Handling

| Failure Mode | Behavior |
|---|---|
| Invalid or missing gkpconfig | Abort with clear error listing missing fields |
| ADO API unreachable / auth failure | Detected in Phase 0 validation; abort with instructions to set `AZURE_DEVOPS_PAT` or run `az login` |
| PR commits not reachable in local clone | Detected in Phase 0; mark affected PRs as `failed` with suggestion to `git fetch`, continue with rest |
| No guidelines found | Abort entire run with clear error message |
| Worktree creation fails | Mark PR as `failed`, continue with remaining PRs |
| Sub-agent times out or crashes | Retry once. If second attempt fails, mark as `failed` |
| `replay-analysis.json` missing after "successful" agent | Mark as `failed` with error "output file not found" |
| All PRs fail | Still produce `harness-report.md` with failures section |

---

## Example Invocation

```
Follow the instructions in Octane.GatekeeperEval.ReplayHarness.prompt.md.

PR Links:
- https://msazure.visualstudio.com/One/_git/Compute-CPlat-Core/pullrequest/12515472
- https://msazure.visualstudio.com/One/_git/Compute-CPlat-Core/pullrequest/12627803
- https://msazure.visualstudio.com/One/_git/Compute-CPlat-Core/pullrequest/12675752
- https://msazure.visualstudio.com/One/_git/Compute-CPlat-Core/pullrequest/12736260
- https://msazure.visualstudio.com/One/_git/Compute-CPlat-Core/pullrequest/12667474

Repo Path: C:\Users\jeffstclair\source\repos\Compute-CPlat-Core
Guidelines Path: C:\Users\jeffstclair\source\repos\pandora\experiments\initial-gatekeeper-readout\generated-anti-patterns\combined-anti-patterns
Output Root: C:\Users\jeffstclair\source\repos\pandora\experiments\replay-harness-run-001
```

---

## Assumptions & Open Questions

1. **Worktree disk space.** Each worktree is a lightweight checkout (~repo working tree size). For a large monorepo, 5 worktrees could consume significant disk. The harness creates them on demand and cleans up after.

2. **Concurrency limit.** All PRs are dispatched simultaneously. For very large PR lists (>10), consider batching to avoid overwhelming the system. This prompt does not impose a concurrency cap — add one if needed.

3. **Replay prompt compatibility.** This harness assumes the Replay prompt accepts a gkpconfig file for configuration. If the Replay prompt's interface changes, the sub-agent prompt template in Phase 2 must be updated.

## Cleanup

Clean up all temporary files, worktrees, and intermediate artifacts before reporting completion. Output directories should contain only the documented report files.
