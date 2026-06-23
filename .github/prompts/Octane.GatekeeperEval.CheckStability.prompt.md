---
agent: GatekeeperEval
description: Run the Gatekeeper pipeline multiple times on the same input and measure run-to-run stability by comparing violations, batches, and filters across runs.
model: Claude Opus 4.6 (1M context)(copilot)
---

## INPUTS

- `Mode` (string, required): One of `review` or `replay`.
  - `review` — Run the Gatekeeper Review pipeline directly.
  - `replay` — Run the Gatekeeper Replay pipeline against a pull request.
- `Runs` (integer, optional): Number of times to run the pipeline. Defaults to `10`. Maximum `20`.
- `Config Path` (string, optional): Path to `gkpconfig.yml`. Defaults to `.github/gatekeeper/gkpconfig.yml` (falls back to `.github/gkpconfig.yml`).

**When Mode = `review`:**
- `Review Mode` (string, optional): One of `--branch`, `--commit-range <range>`, `--staged`, `--untracked`, or `--full`. Defaults to `--branch` if omitted.

**When Mode = `replay`:**
- `PR Link` (string, required): URL to the pull request (Azure DevOps or GitHub).

## PRIMARY DIRECTIVE

Run the Gatekeeper pipeline **N times** on the exact same input and compare the results to measure **run-to-run stability**. For each pair of runs, compute overlap metrics at every pipeline stage (filter, batch, review). Produce a structured stability report identifying what is deterministic, what varies, and why.

This prompt is used to validate that pipeline changes improve consistency or to diagnose sources of non-determinism.

## WORKFLOW STEPS

Present the following steps as **trackable todos** to guide progress:

### 1. Initialize

- Parse and validate all inputs.
- Determine the number of runs N (default 10, max 20).
- **Generate a unique run ID** using the `run-id` skill:
  ```bash
  RUN_ID=$(python "{plugin_root}/skills/run-id/scripts/generate_run_id.py")
  ```
  This produces a 6-character hex string (e.g., `a1b2c3`). The output directory for this execution is `output/stability-{RUN_ID}/`.
- **Announce the output directory** immediately:
  ```
  Stability output directory: output/stability-{RUN_ID}/
  ```
- If Mode = `review` with `--commit-range`, save the current HEAD:
  ```
  original_ref=$(git rev-parse HEAD)
  ```
  Checkout the head commit of the range so the working tree matches the code under review. This checkout is done **once** — all N runs use the same working tree state.
- Create the output directory: `output/stability-{RUN_ID}/`

### 2. Execute N Runs

For each run `i` from 1 to N:

1. **Invoke the Gatekeeper agent** using `runSubagent` with these parameters:
   - `agentName`: `"Gatekeeper"`
   - `description`: `"Stability run {i} of {N}"`
   - `prompt`:

   **If Mode = `review`:**
   ```
   Run the Gatekeeper Review pipeline with these inputs:

   - Review Mode: {review_mode}
   - Config Path: {resolved_config_path}
   - Flags: --debug

   PROMPT FILE: Read the review agent instructions ONLY from this exact path:
     $AGENCY_PLUGIN_DIR/agents/Octane.GatekeeperReview.agent.md
   Do NOT search for or read any other files matching "review" or "gatekeeper-review".
   Do NOT read any files under .github/workflows/.

   IMPORTANT:
   - Run the FULL Gatekeeper pipeline: prepare review items, batch, dispatch GatekeeperGuidelineReviewer sub-agents, and aggregate.
   - Write all output files to: output/stability-{RUN_ID}/run-{i}/
   - Return the complete final-review.json content and a summary of all violations found (file, line, guideline, severity, description).
   - Do NOT skip any pipeline stages. Do NOT guess or assume violations — actually read the code and review it.
   - The --debug flag is set: write debug state files and include the PIPELINE DEBUG SUMMARY block per the debug-export skill.

   OUTPUT ISOLATION (CRITICAL):
   - Do NOT read, search, or reference ANY files under the output/ directory. Treat the entire output/ directory as write-only.
   - Do NOT use file_search, semantic_search, or grep_search with patterns that could match output/ paths.
   - Do NOT read final-review.json, replay-analysis.json, run-manifest.json, or any other JSON files from previous runs.
   - Each run must derive all results solely from reading source code and guideline skills — never from previous pipeline output.
   ```

   **If Mode = `replay`:**
   ```
   Run the Gatekeeper Replay pipeline with these inputs:

   - PR Link: {pr_link}
   - Config Path: {resolved_config_path}
   - Output Dir: output/stability-{RUN_ID}/run-{i}

   PROMPT FILE: Read the replay prompt ONLY from this exact path:
     $AGENCY_PLUGIN_DIR/prompts/Octane.GatekeeperEval.Replay.prompt.md
   Do NOT search for or read any other files matching "replay" or "gatekeeper-replay".
   Do NOT read any files under .github/workflows/.

   IMPORTANT:
   - Run the FULL Replay pipeline with --debug enabled.
   - The Output Dir is set to output/stability-{RUN_ID}/run-{i}/ — the Replay prompt's {OUTPUT_DIR} variable MUST resolve to this path. All output files (iterations, debug snapshots, replay-analysis.json, replay-analysis-report.md, run-manifest.json) go under this directory.
   - Return the complete results including per-iteration violations, the run manifest, and the replay analysis.
   - Do NOT skip any steps. Do NOT fabricate results.
   - PLATFORM DETECTION: Parse the PR Link URL to determine the platform. If the URL contains "dev.azure.com" or "visualstudio.com", the platform is Azure DevOps — use ADO REST APIs and `az` CLI commands ONLY. Do NOT use `gh` CLI, GitHub MCP tools (mcp_github_*), or any GitHub-specific APIs. If the URL contains "github.com", the platform is GitHub — use `gh` CLI and GitHub APIs.

   OUTPUT ISOLATION (CRITICAL):
   - Do NOT read, search, or reference ANY existing files under the output/ directory. Treat the entire output/ directory as write-only.
   - Do NOT use file_search, semantic_search, or grep_search with patterns that could match output/ paths.
   - Do NOT read final-review.json, replay-analysis.json, run-manifest.json, or any other JSON files from previous or other stability runs.
   - When the Replay prompt instructs inner sub-agents to write to output/replay/iteration-{id}/, override that path to output/stability-{RUN_ID}/run-{i}/iteration-{id}/ instead.
   - Each run must derive all results solely from fetching PR data via APIs and reviewing source code — never from previous pipeline output.
   ```

2. **Collect the result** for run `i`. Store:
   - The full violation list (file, startline, guideline, severity, description)
   - The filter results table (guideline → glob_patterns, content_regex)
   - The batch assignments (batch_id → files, guidelines)
   - The pipeline summary counts (guidelines, changed files, batches, violations)

3. **Repeat** for all N runs. Each run MUST be an independent `runSubagent` call — do not reuse state between runs.

### 3. Compare Runs

After all N runs complete, **dispatch a comparison sub-agent** to analyze stability across all runs. The comparison must cover every unique pair of runs (for N runs, that is N×(N−1)/2 pairs).

1. **Invoke the comparison sub-agent** using `runSubagent` with these parameters:
   - `agentName`: `"Gatekeeper"`
   - `description`: `"Stability comparison across {N} runs"`
   - `prompt`:

   ```
   You are given the output from {N} independent Gatekeeper pipeline runs stored under output/stability-{RUN_ID}/run-1/ through output/stability-{RUN_ID}/run-{N}/.

   Compare ALL unique pairs of runs (every combination, not just consecutive). For each pair, analyze:

   ## Filter Stage Comparison

   - Compare the filter results table from each run (guideline → glob_patterns, content_regex).
   - For each guideline, check if `glob_patterns` and `content_regex` are identical.
   - Report: number of guidelines with identical filters / total guidelines.
   - **Expected**: 100% match. Any difference here is a filter instability bug.

   ## Batch Stage Comparison

   - Compare the batch assignments (batch_id → files, guidelines).
   - Check: same number of batches? Same files in each batch? Same guidelines per batch?
   - Report: number of identical batches / total batches.
   - If batches differ, identify the cause: different file→guideline mapping, different grouping, different split order.

   ## Violation Stage Comparison

   - Build a **canonical violation key** for each violation: `(basename(file_name), startline, guideline_basename)`. Use basenames to avoid path format differences.
   - Compute:
     - **Matched**: violations found in BOTH runs (same key)
     - **Run A only**: violations found only in the first run
     - **Run B only**: violations found only in the second run
     - **Total unique**: union of all violations across both runs
     - **Jaccard overlap**: matched / total_unique × 100%
   - For each unmatched violation, classify the likely cause:
     - `BATCH_DIFFERENCE` — the file+guideline pair was in different batches (or missing from a batch)
     - `REVIEWER_VARIANCE` — same batch composition, reviewer found it in one run but not the other
     - `SIBLING_MISS` — the violation was found in a sibling method in one run but not the other
     - `REGION_DECAY` — a related violation was found nearby (same file, same guideline, ±10 lines) in the other run
     - `UNKNOWN` — no clear cause

   ## Aggregate Metrics

   Across all pairs, compute:

   | Metric | Formula |
   |--------|---------|
   | **Filter stability** | % of guidelines with identical filter specs across all pairs |
   | **Batch stability** | % of batches that are identical across all pairs |
   | **Violation overlap (Jaccard)** | Average Jaccard overlap across all pairs |
   | **Violation overlap (min)** | Minimum Jaccard overlap across all pairs |
   | **Total unique violations** | Union of all violations across ALL runs |
   | **Core violations** | Violations found in EVERY run (intersection) |
   | **Core ratio** | Core violations / total unique × 100% |

   Return the full pairwise comparison results AND the aggregate metrics.
   Write the comparison output to: output/stability-{RUN_ID}/comparison-results.json
   ```

2. **Collect the comparison results** from the sub-agent.

### 4. Restore Repository

If a checkout was performed in Step 1, restore the original ref:
```
git checkout {original_ref} --quiet
```

### 5. Present Results

Display the stability report.

## OUTPUT

Write the report to `output/stability-{RUN_ID}/stability-report.json`:

```json
{
  "timestamp": "ISO-8601",
  "mode": "review|replay",
  "runs": N,
  "input_summary": { "config_path": "...", "review_mode": "...", "pr_link": "..." },
  "per_run_summary": [
    { "run": 1, "guidelines": N, "changed_files": N, "batches": N, "violations": N },
    { "run": 2, "guidelines": N, "changed_files": N, "batches": N, "violations": N }
  ],
  "pairwise_comparisons": [
    {
      "pair": "run-1 vs run-2",
      "filter_stability_pct": 100.0,
      "batch_stability_pct": 100.0,
      "violations_matched": N,
      "violations_run_a_only": N,
      "violations_run_b_only": N,
      "violations_total_unique": N,
      "jaccard_overlap_pct": 75.0,
      "unmatched_causes": { "BATCH_DIFFERENCE": N, "REVIEWER_VARIANCE": N, "SIBLING_MISS": N, "REGION_DECAY": N, "UNKNOWN": N }
    }
  ],
  "aggregate": {
    "filter_stability_pct": 100.0,
    "batch_stability_pct": 100.0,
    "avg_jaccard_overlap_pct": 75.0,
    "min_jaccard_overlap_pct": 71.4,
    "total_unique_violations": N,
    "core_violations": N,
    "core_ratio_pct": 60.0
  }
}
```

### Summary Format

```markdown
# Gatekeeper Stability Report

## Configuration

| Setting | Value |
|---------|-------|
| **Mode** | review / replay |
| **Runs** | N |
| **Input** | [details] |

## Per-Run Summary

| Run | Guidelines | Changed Files | Batches | Violations |
|-----|-----------|---------------|---------|------------|
| 1   | N         | N             | N       | N          |
| 2   | N         | N             | N       | N          |

## Stability Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| **Filter stability** | X% | ✅ Stable / ❌ Unstable |
| **Batch stability** | X% | ✅ Stable / ⚠️ Partial / ❌ Unstable |
| **Avg violation overlap** | X% | ✅ High (>80%) / ⚠️ Moderate (50-80%) / ❌ Low (<50%) |
| **Core ratio** | X% | [N core / M unique] |

## Pairwise Comparison: Run 1 vs Run 2

### Violations Found in Both Runs (N matched)

| File | Line | Guideline | Severity |
|------|------|-----------|----------|
| ... | ... | ... | ... |

### Violations Found Only in Run 1 (N unique)

| File | Line | Guideline | Severity | Likely Cause |
|------|------|-----------|----------|-------------|
| ... | ... | ... | ... | REVIEWER_VARIANCE |

### Violations Found Only in Run 2 (N unique)

| File | Line | Guideline | Severity | Likely Cause |
|------|------|-----------|----------|-------------|
| ... | ... | ... | ... | REVIEWER_VARIANCE |

### Unmatched Cause Breakdown

| Cause | Count | Description |
|-------|-------|-------------|
| BATCH_DIFFERENCE | N | File+guideline in different batches |
| REVIEWER_VARIANCE | N | Same batch, reviewer found in one run only |
| SIBLING_MISS | N | Found in sibling method in other run |
| REGION_DECAY | N | Related violation ±10 lines in other run |
| UNKNOWN | N | No clear cause |

## Assessment

> **[VERDICT]**: [Summary statement]

- ✅ **STABLE** (overlap ≥80%): Pipeline produces consistent results. Remaining variance is inherent LLM non-determinism.
- ⚠️ **MODERATE** (overlap 50-80%): Pipeline has partial stability. [Identify top contributing factor].
- ❌ **UNSTABLE** (overlap <50%): Pipeline has significant non-determinism. [Identify root cause at which stage].
```

## CONSTRAINTS

- **DO NOT** reuse pipeline state between runs — each run MUST be a fresh, independent `runSubagent` call
- **DO NOT** skip any pipeline stages in any run — every run must execute the full pipeline
- **DO NOT** leave the repository in detached HEAD state after the stability test completes
- **DO NOT** fabricate or assume violations — all violations must come from actual Gatekeeper sub-agent output
- **DO NOT** read any files from the `output/` directory during pipeline runs — `output/` is write-only for each run. Sub-agents must not search for, read, or reference any existing output files (including `final-review.json`, `replay-analysis.json`, `run-manifest.json`, or debug state from previous or concurrent runs)
- **DO NOT** use `file_search`, `semantic_search`, or `grep_search` with patterns that match `output/` during pipeline runs
- **DO** generate a unique run ID via the `run-id` skill and use it for the output directory
- **DO** announce the output directory (`output/stability-{RUN_ID}/`) at the start of the run
- **DO** use `--debug` flag for every run so debug state files are available for comparison
- **DO** use basename-only matching when comparing violations to avoid path format differences
- **DO** override all hardcoded `output/replay/` paths in the Replay prompt with the run-specific `output/stability-{RUN_ID}/run-{i}/` path — this prevents cross-run contamination via shared output directories
- When comparing batches, normalize by sorting files and guidelines alphabetically before comparison
- The stability test itself must be deterministic — comparison logic must not introduce additional variance
- **DO** clean up temporary files (scratch scripts, intermediate diffs, temp JSON) before reporting completion — output directories should contain only documented output files
