# Gatekeeper Code Review

> **First-time adopters:** Most teams should start with the [`gatekeeper-client`](../gatekeeper-client/) scenario, which provides a natural-language wrapper agent (`@GatekeeperAgent`), a first-time setup wizard, and PR comment posting. This `gatekeeper` scenario is the **review engine** itself — only install it directly if you're authoring the engine, customizing the pipeline, or running it from CI/CD.

## Overview

The **Gatekeeper** scenario provides an automated multi-stage code review pipeline that reviews repository code against configurable guidelines. It uses parallel sub-agents to efficiently filter, batch, and review code at scale. The system enables teams to:

1. **Define Code Guidelines** — Maintain a library of guideline documents that describe rules, detection instructions, and suggested fixes
2. **Automate Reviews** — Run a full pipeline that discovers guidelines, filters relevant files, batches work, and reviews code in parallel
3. **Generate Reports** — Produce structured JSON and Markdown violation reports for integration into PR workflows

## When to Use

Use this scenario when you need to:

- **Review code against a set of team guidelines** across an entire repository or specific changes
- **Automate code review** for pull requests, commit ranges, or staged changes
- **Scale reviews** across large codebases using parallel sub-agent execution
- **Generate actionable violation reports** with precise file locations and suggested fixes
- **Create new guideline documents** from code snippets or descriptions


## Quick Start Guide

> **Note:** Make sure you have a local clone of the repo you want to review. Gatekeeper will check out different revisions during its review.

1. Install [Agency](https://aka.ms/agency):
    ```powershell
    # Agency wraps GitHub Copilot CLI with plugin management
    agency --version  # Verify installation
    ```

2. Make the Gatekeeper plugin available (choose one):

    **Option A — Marketplace install** (recommended for most users):
    ```powershell
    agency plugin install market:gatekeeper-octane-version@agency-microsoft/playground --engine copilot
    ```

    **Option B — Vendored plugin** (if the repo ships with the plugin at `.github/plugins/gatekeeper-octane-version/`):
    No install needed. Pass `--plugin-dir` when invoking (see step 5).

3. Build guidelines for your reviews

    a. If you're already working with the AzCore OCTO team, they may have already generated guidelines for your repo — check with them first.

    b. To create your own, run Gatekeeper Extract on a PR to generate guidelines.

4. Create a config file at `.github/gatekeeper/gkpconfig.yml` in your target repository:
```yaml
repo_root: .
reviewers:
  guidelines_reviewer:
    guidelines_root: .github/skills
    folder_rules:
      '**':
        guidelines:
          - '**'
  domain: {}
  security: {}
```

5. Run a review:

    **With marketplace install** (Option A):
    ```powershell
    agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
      --no-default-mcps `
      -p "Review Mode: --branch" `
      --allow-all
    ```

    **With vendored plugin** (Option B):
    ```powershell
    agency copilot `
      --plugin-dir .github/plugins/gatekeeper-octane-version `
      --agent gatekeeper-octane-version:Octane.GatekeeperReview `
      --no-default-mcps `
      -p "Review Mode: --branch" `
      --allow-all
    ```

> **Note:** `--allow-all` is required for Gatekeeper to execute Python scripts and access files outside the repository root. Every `agency copilot` invocation — including nested calls from Replay/CheckStability — must include this flag.

## Prerequisites

### Required Software

- **[Agency CLI](https://aka.ms/agency)** — The supported runtime for Gatekeeper
- **Python 3.8+** — For operational scripts (prepare-review, batch-files, merge-reports)
- **Git** — For diff extraction and repository operations
- **Conductor ≥ v0.1.19** — multi-agent workflow engine for the Replay pipeline; the per-agent `context_tier` used by the reviewers requires v0.1.19+ (added in conductor#252)

### Access Requirements

- Access to the repository you want to review
- A guidelines directory containing guideline skill subdirectories (for guideline review)

### Architecture: Plugin vs Repository Content

Gatekeeper operational scripts and built-in reviewer agents are shipped with the **Agency plugin** and resolved via `$AGENCY_PLUGIN_DIR` at runtime. Target repositories contain only:

- `.github/gatekeeper/gkpconfig.yml` — Pipeline configuration
- `.github/skills/` (or custom path) — Guideline/knowledge-context skill content
- `.github/gatekeeper/agents/` (optional) — Custom specialist reviewer agents that override or extend built-in reviewers

**Plugin resolution options:**

| Method | How | `AGENCY_PLUGIN_DIR` set to |
|--------|-----|---------------------------|
| Marketplace install | `agency plugin install market:...` then invoke normally | Temp staging dir (absolute path) |
| Vendored in repo | `--plugin-dir .github/plugins/gatekeeper-octane-version` | The vendored directory (relative path) |
| GitHub branch | `agency plugin install "github:owner/repo:path@branch"` | Temp staging dir (absolute path) |

All three methods set `AGENCY_PLUGIN_DIR` — prompts, agents, and scripts work identically regardless of source.

## What's Included

### Workflow Agents (user-facing)

- **[GatekeeperReview](agents/Octane.GatekeeperReview.agent.md)** — Multi-stage code review pipeline: prepare, batch, dispatch specialist and guideline reviewers in parallel, aggregate and deduplicate findings
- **[CriticReview](agents/Octane.CriticReview.agent.md)** — Expert code reviewer analyzing correctness, security, performance, and maintainability (adapted from [AI-First Dev Starter Pack](https://github.com/1ES-AI/ai-first-dev-starter-pack))
- **[GatekeeperExtract](agents/Octane.GatekeeperExtract.agent.md)** — Extract reusable guideline skills from Azure DevOps pull request review threads
- **[GatekeeperGenerator](agents/Octane.GatekeeperGenerator.agent.md)** — Generate guideline skill directories from code snippets or descriptions
- **[GatekeeperEval](agents/Octane.GatekeeperEval.agent.md)** — Evaluation/benchmarking orchestrator for CheckStability, Replay, and ReplayHarness workflows

### Internal Orchestrator Agents

- **[GatekeeperConvertOrchestrator](agents/Octane.GatekeeperConvertOrchestrator.agent.md)** — Batch-convert guideline `.md` files into skill directories using parallel GatekeeperGuidelineConverter sub-agents
- **[GatekeeperVerifyOrchestrator](agents/Octane.GatekeeperVerifyOrchestrator.agent.md)** — Verify converted skills match their original sources using parallel GatekeeperGuidelineVerifier sub-agents

### Sub-Agents (dispatched internally)

- **[GatekeeperGuidelineReviewer](agents/Octane.GatekeeperGuidelineReviewer.agent.md)** — Reviews code files against provided guidelines, writes results to session SQL
- **[GatekeeperReplayAnalyzer](agents/Octane.GatekeeperReplayAnalyzer.agent.md)** — Merges per-iteration review reports, classifies PR comments against violations
- **[CommentClassifier](agents/Octane.CommentClassifier.agent.md)** — Classifies PR reviewer comments against Gatekeeper violations by semantic relevance
- **[GatekeeperResultCritic](agents/Octane.GatekeeperResultCritic.agent.md)** — Mandatory post-merge critic that filters false positives and out-of-scope findings from the merged final report using a minimal filtered-findings artifact
- **[GatekeeperGuidelineConverter](agents/Octane.GatekeeperGuidelineConverter.agent.md)** — Converts guideline `.md` files into skill directories with SKILL.md frontmatter
- **[GatekeeperGuidelineVerifier](agents/Octane.GatekeeperGuidelineVerifier.agent.md)** — Verifies converted skills match their original guideline sources

### Specialist Reviewers

Composable, domain-focused reviewers that run alongside the guideline-based review. Built-in reviewers are shipped with the plugin and discovered automatically via `--agents-root`. Custom reviewers can be placed in `.github/gatekeeper/agents/` in the target repository (passed via `--repo-agents-root`).

- **[Security](agents/Octane.SecurityReviewer.agent.md)** — Analyzes for injection vulnerabilities, authentication/authorization bypass, sensitive data exposure, and security misconfigurations
- **[Reliability](agents/Octane.ReliabilityReviewer.agent.md)** — Analyzes for error handling gaps, null reference risks, resource management problems, concurrency issues, and diagnosability gaps
- **[Performance](agents/Octane.PerformanceReviewer.agent.md)** — Analyzes for algorithmic inefficiencies, resource management issues, database/IO bottlenecks, and language-specific performance issues
- **[Quality](agents/Octane.QualityReviewer.agent.md)** — Analyzes for test coverage gaps, feature flag misuse, unsafe rollout patterns, deployment safety, and QEI compliance (Change Management, Production Readiness, Service Health)
- **[Domain](agents/Octane.DomainReviewer.agent.md)** — Knowledge-driven reviewer that loads repo-local domain skills (feature area maps, component profiles, behavioral patterns, known traps). Doc-backed findings carry a `tag` equal to a `[GK-<PREFIX>-<NUMBER>]` rule tag in the cited guideline doc; insights from untagged docs or pure reasoning are emitted as deep-reasoning findings (`guideline: "deep-reasoning"`, `tag: "DEEPREASONING"`). The deterministic [`validate-finding-tags`](skills/validate-finding-tags/) post-step drops any doc-backed finding whose tag cannot be verified.

> **Creating custom reviewers:** Create an `Octane.{Name}Reviewer.agent.md` file in the `agents/` directory to add your own specialist reviewer. See [Creating Custom Reviewers](#creating-custom-reviewers) below.

### Evaluation Prompts (used with GatekeeperEval agent)

- **[Octane.GatekeeperEval.Replay](prompts/Octane.GatekeeperEval.Replay.prompt.md)** — Replay a pull request through Gatekeeper to measure what percentage of human reviewer comments could have been caught automatically
- **[Octane.GatekeeperEval.ReplayHarness](prompts/Octane.GatekeeperEval.ReplayHarness.prompt.md)** — Run parallel Gatekeeper Replays across multiple PRs and produce an aggregated comparison report
- **[Octane.GatekeeperEval.CheckStability](prompts/Octane.GatekeeperEval.CheckStability.prompt.md)** — Measure run-to-run pipeline stability by executing the review or replay pipeline multiple times and comparing results

### Skills

- **[batch-files](skills/batch-files/)** — Python script that groups file-guideline filter results into optimized review batches for parallel processing
- **[merge-reports](skills/merge-reports/)** — Python script that aggregates code review results from multiple batch reviews into a unified final JSON and Markdown report
- **[post-comments](skills/post-comments/)** — Posts deduplicated review findings as line-level PR comments to ADO or GitHub, with deduplication, finding_type-based routing, and feedback loop tagging
- **[resolve-knowledge-docs](skills/resolve-knowledge-docs/)** — Deterministic Python script that pre-resolves which knowledge-context skill documents are relevant for a set of changed files, eliminating LLM-based routing
- **[validate-finding-tags](skills/validate-finding-tags/)** — Deterministic Python post-validator invoked by the DomainReviewer; drops doc-backed findings whose `tag` cannot be verified as a `[GK-<PREFIX>-<NUMBER>]` tag inline in the cited `guideline` doc. Deep-reasoning findings (`guideline: "deep-reasoning"`, `tag: "DEEPREASONING"`) are always kept.
- **[guideline-templates](skills/guideline-templates/)** — Reference templates for authoring guideline skills and formatting violation reports
- **[debug-export](skills/debug-export/)** — Exports deterministic intermediate pipeline state after each stage for cross-run comparison (activated via `--debug` flag)
- **[reviewer-eval](skills/reviewer-eval/)** — Quality gate scoring for specialist reviewer output against a 5-category rubric
- **[classify-comments](skills/classify-comments/)** — Python scripts for batching, classifying, and merging PR comment classifications against Gatekeeper violations
- **[run-id](skills/run-id/)** — Python script for generating deterministic pipeline run identifiers
- **[conductor](skills/conductor/)** — Conductor workflow for the Gatekeeper Replay pipeline with DAG visualization, cost tracking, and checkpoint/resume on failure
- **[custom-reviewers](skills/custom-reviewers/)** — Guide and templates for creating custom specialist reviewers with the required frontmatter, output schema, and registration steps
- **[download-skills](skills/download-skills/)** — Downloads the latest guideline skills from `azure-core/pandora` into the target repository's `.github/skills/` folder
- **[extract-filters](skills/extract-filters/)** — Deterministically extracts glob patterns and content regex from guideline SKILL.md frontmatter, bypassing LLM inference at the filter stage
- **[fetch-pr-comments](skills/fetch-pr-comments/)** — Fetches code-level reviewer comments from an ADO or GitHub PR, maps them to iterations, and returns JSON for the Replay pipeline
- **[fetch-pr-iterations](skills/fetch-pr-iterations/)** — Fetches the PR iteration timeline with comment mappings from ADO or GitHub for use at the start of a Replay
- **[parse-config](skills/parse-config/)** — Parses and validates `gkpconfig.yml`, resolves paths, and returns a structured JSON summary for any Gatekeeper pipeline stage
- **[prepare-review](skills/prepare-review/)** — Consolidates config parsing, guideline discovery, specialist file matching, and diff extraction into a single script at pipeline startup

## Pipeline Architecture

The Gatekeeper pipeline consists of five stages driven by script-backed skills:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Prepare    │────▶│    Batch     │────▶│   Dispatch   │────▶│  Aggregate & │────▶│ ResultCritic │
│  (Stage 0)   │     │  (Stage 1)   │     │  (Stage 2)   │     │  Deduplicate │     │  (Stage 4)   │
└──────────────┘     └──────────────┘     └──────────────┘     │  (Stage 3)   │     └──────────────┘
  Parse config,       Group files into      Dispatch all         └──────────────┘       Filter merged
  discover            optimized batches     reviewer sub-        Merge guideline        final report
  guidelines,         for all reviewer      agents in            + specialist
  match files,        types                 parallel             results, dedup
  extract diffs                             (guidelines +        cross-model
                                            specialists)         findings
```

### Stage 0 — Prepare

Uses the `prepare-review` skill (backed by `prepare_review.py`) to consolidate startup work into a single script call: parse and validate `gkpconfig.yml` via `parse-config`, discover guideline skills, run filter extraction via `extract-filters` (deterministic, no LLM inference), match specialist reviewer scope globs against repo files, and extract diff contents for the target review mode. Outputs a `review_items.json` and `dispatch_plan.json` for the next stage.

### Stage 1 — Batch

Uses the `batch-files` skill to group review items into optimized batches (max ~10 files per batch) for both guideline and specialist reviewers. Batch plan is written to the SQL database and is **immutable** — the pipeline never re-batches.

### Stage 2 — Dispatch All Reviewers (Unified Parallel Loop)

Dispatches all reviewer sub-agents in a single unified loop with a concurrency pool:

- **Guideline batches** → `GatekeeperGuidelineReviewer` sub-agents, each reviewing their assigned files against assigned guidelines
- **Specialist batches** → Specialist reviewer agents (Security, Reliability, Performance, Quality, Domain, or custom), each scoped to their file globs and running on their configured model(s)
- **Two-strike failure policy**: if any batch fails twice, the entire pipeline stops and waits for running agents before reporting

Multi-model dispatch: when `reviewers.models` is configured, each specialist reviewer is dispatched once per model in parallel.

### Stage 3 — Aggregate & Deduplicate

Uses the `merge-reports` skill to combine all guideline and specialist review results, then deduplicates across models:
- Same file + overlapping line range + same severity from different models → merged into a single **high-confidence** finding
- Unique findings from one model → kept and flagged as **single-model** for human review

Outputs:
- `output/final-review.json` — Machine-readable aggregated results
- `output/final-review-report.md` — Human-readable Markdown report with a Model Coverage Summary

### Stage 4 — Mandatory Result Critic

After Stage 3 merge completes, Gatekeeper runs `GatekeeperResultCritic` once on the merged `final-review.json`.

- Input: merged final report (guideline + specialist + domain findings)
- Behavior: filters false positives and out-of-scope findings
- Output artifacts:
  - `output/pre-critic-final-review.json` (snapshot before filtering)
  - `output/final-review.json` (filtered)
  - `output/critic-filtered-findings.json` (minimal artifact with filtered items only)

## Review Modes

| Mode | Trigger | Description |
|------|---------|-------------|
| **Branch review** | Default | Reviews changes on the current branch vs origin/master (`origin/master...HEAD`) |
| **Full scan** | `--full` | Reviews all matching files in the repository |
| **Commit range** | `--commit-range <range>` | Reviews only files changed in the specified commit range |
| **Staged changes** | `--staged` | Reviews only staged (git index) changes |
| **Untracked changes** | `--untracked` | Reviews only untracked file changes |

## Configuration

Configure the pipeline via `.github/gatekeeper/gkpconfig.yml` in the target repository:

### Canonical Config (recommended)

```yaml
# Plugin source (omit to default to github:azure-core/octane:artifacts/scenarios/gatekeeper@main)
# plugin: .github/plugins/gatekeeper-octane-version                              # vendored local copy
# plugin: github:azure-core/octane:artifacts/scenarios/gatekeeper@main           # GitHub ref (or @sha to pin)
# plugin: gatekeeper-octane-version@agency-microsoft/playground                  # marketplace

repo_root: .
reviewers:
  guidelines_reviewer:
    guidelines_root: .github/skills
    folder_rules:
      '**':
        guidelines:
          - '**'
      'src/tests/**':
        guidelines:
          - 'test-*'
  domain: {}
  security: {}
  reliability: {}
  performance: {}
  quality: {}
```

### Legacy Config (still accepted)

```yaml
repo_root: .
skills_root: .github/skills

folder_rules:
  '**':
    guidelines:
      - '**'
```

Legacy configs with top-level `skills_root` are normalized to a `guidelines_reviewer` entry automatically.

| Key | Description | Default |
|-----|-------------|---------|
| `plugin` | Plugin source reference. Accepts three formats: local path (e.g., `.github/plugins/gatekeeper-octane-version`), GitHub ref (e.g., `github:azure-core/octane:artifacts/scenarios/gatekeeper@main`), or marketplace (e.g., `gatekeeper-octane-version@agency-microsoft/playground`). GitHub refs support `@commit-sha` for pinning. | `github:azure-core/octane:artifacts/scenarios/gatekeeper@main` (auto-fetched) |
| `repo_root` | Path to the repository root (relative to config file) | `.` |
| `reviewers.guidelines_reviewer.guidelines_root` | Path to guideline skill directories (each with a `SKILL.md`) | *required for guideline review* |
| `reviewers.guidelines_reviewer.folder_rules` | Per-folder guideline overrides | `{}` (all guidelines apply to all files) |
| `reviewers.{name}` | Specialist reviewer (e.g., `domain: {}`, `security: {}`) — discovered from plugin built-in agents or `.github/gatekeeper/agents/` | *optional* |
| `reviewers.{name}.model` | AI model for a specific reviewer | `default` |

### Result Critic (Mandatory)

ResultCritic is mandatory and not driven by config. It runs once after merge on the full merged final report.

For full design rationale and review checklist, see [docs/gatekeeper/gatekeeper-critic-enablement-design.md](../../../docs/gatekeeper/gatekeeper-critic-enablement-design.md).

> **Repo Path precedence**: When `--repo-path` is provided (e.g., by the Replay orchestrator), it overrides `repo_root` from config. This ensures correct resolution even when `repo_root: .` would otherwise resolve to the config file's parent directory.

## Workflows

### Running a Code Review

1. **Configure guidelines** — Create guideline skill directories in `.github/skills/` (see [Guideline Format](#guideline-format)) and configure `.github/gatekeeper/gkpconfig.yml`
2. **Run the review** — Invoke via Agency from your repo directory:
   ```powershell
   agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
     --no-default-mcps `
     -p "Review Mode: --branch" `
     --allow-all
   ```
3. **Wait for pipeline completion** — The orchestrator discovers guidelines, filters files, batches work, and dispatches parallel reviewers automatically
4. **Review the report** — Examine the generated `output/final-review-report.md` for violations and suggested fixes
5. **Fix violations** — Address findings and re-run on staged changes to verify:
   ```powershell
   agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
     --no-default-mcps `
     -p "Review Mode: --staged" `
     --allow-all
   ```

### Common Invocation Examples

**Review current branch changes (default)**:
```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
  --no-default-mcps `
  -p "Review Mode: --branch" `
  --allow-all
```

**Review staged changes only**:
```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
  --no-default-mcps `
  -p "Review Mode: --staged" `
  --allow-all
```

**Review a commit range**:
```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
  --no-default-mcps `
  -p "Review Mode: --commit-range HEAD~5..HEAD" `
  --allow-all
```

**Full repository scan**:
```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
  --no-default-mcps `
  -p "Review Mode: --full" `
  --allow-all
```

**Explicit config and repo path** (for repos where CWD isn't the repo root):
```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
  --no-default-mcps `
  -p "Review Mode: --branch
Config Path: C:\code\my-repo\.github\gatekeeper\gkpconfig.yml
Repo Path: C:\code\my-repo
Output Dir: C:\code\my-repo\review-output" `
  --allow-all
```

**Silent mode** (no interactive output — useful for scripting):
```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperReview `
  --no-default-mcps `
  -p "Review Mode: --branch" `
  --allow-all --silent
```

**Using a vendored plugin** (no marketplace install needed):
```powershell
agency copilot `
  --plugin-dir .github/plugins/gatekeeper-octane-version `
  --agent gatekeeper-octane-version:Octane.GatekeeperReview `
  --no-default-mcps `
  -p "Review Mode: --branch" `
  --allow-all
```

### Input Parameters Reference

All parameters are passed as lines in the `-p` prompt string:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `Review Mode` | Yes | `--branch` (default), `--full`, `--staged`, `--commit-range <range>` |
| `Config Path` | No | Absolute path to `gkpconfig.yml`. Auto-discovered if omitted. |
| `Repo Path` | No | Absolute path to repo root. Uses CWD if omitted. Overrides `repo_root` from config. |
| `Output Dir` | No | Where to write reports. Defaults to `output/`. |
| `Flags` | No | `--debug` enables intermediate state export after each stage. |

### How Workflow Invocation Works

Each Gatekeeper workflow is a self-contained agent under `agents/`. Invoke it by name via `--agent plugin:AgentName` and pass parameters via `-p`:

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.<WorkflowAgent> `
  --no-default-mcps `
  -p "<Input1>: <value>
<Input2>: <value>" `
  --allow-all
```

For evaluation workflows (Replay, CheckStability, ReplayHarness), use the `GatekeeperEval` agent with a prompt file reference:

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperEval `
  --no-default-mcps `
  -p "Follow the workflow instructions in the prompt file at `$AGENCY_PLUGIN_DIR/prompts/Octane.GatekeeperEval.Replay.prompt.md
PR Link: <url>
Config Path: .github/gatekeeper/gkpconfig.yml" `
  --allow-all
```

### Generating a New Guideline

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperGenerator `
  --no-default-mcps `
  -p "Guideline Name: SQL Injection via String Concatenation
Code Snippet: var query = 'SELECT * FROM users WHERE id = ' + userId;" `
  --allow-all
```

### Extracting Guidelines from a PR

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperExtract `
  --no-default-mcps `
  -p "PR Link: https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}" `
  --allow-all
```

### Replaying a Pull Request

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperEval `
  --no-default-mcps `
  -p "Follow the workflow instructions in the prompt file at `$AGENCY_PLUGIN_DIR/prompts/Octane.GatekeeperEval.Replay.prompt.md
PR Link: https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}
Config Path: .github/gatekeeper/gkpconfig.yml
Output Dir: output/replay" `
  --allow-all
```

### Checking Pipeline Stability

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperEval `
  --no-default-mcps `
  -p "Follow the workflow instructions in the prompt file at `$AGENCY_PLUGIN_DIR/prompts/Octane.GatekeeperEval.CheckStability.prompt.md
Mode: review
Review Mode: --branch
Runs: 5" `
  --allow-all
```

### Converting Guidelines to Skills

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperConvertOrchestrator `
  --no-default-mcps `
  -p "Guidelines Folder: .github/guidelines
Output Folder: .github/skills" `
  --allow-all
```

The replay pipeline:
1. Reads the PR and identifies iterations (pushes) that received reviewer comments
2. For each commented iteration, runs a full Gatekeeper review against the diff visible at that point
3. All iteration reviews run **in parallel** via sub-agents
4. A specialized **GatekeeperReplayAnalyzer** agent merges results and compares them against actual PR comments
5. Produces a coverage analysis with the percentage of comments that could have been avoided

## Expected Output

After the pipeline completes, two report files are generated:

| File | Format | Description |
|------|--------|-------------|
| `output/final-review.json` | JSON | Machine-readable aggregated results with all violations, non-violations, and metadata |
| `output/final-review-report.md` | Markdown | Human-readable report with violations grouped by severity, file locations, and suggested fixes |

The pipeline also prints a summary to the chat showing the number of guidelines reviewed, files scanned, and violations found broken down by severity (Critical, High, Medium, Low, Informational).

## Validation Results

The specialist reviewers have been validated against a golden test fixture containing 17 intentionally planted issues across two files simulating Portal extension code.

### Golden Test Scorecard

| Reviewer | Detection | Severity | Actionability | Scope | Signal:Noise | **Overall** | Gate |
|----------|:---------:|:--------:|:------------:|:-----:|:------------:|:-----------:|:----:|
| Security | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | **5.0** | ✅ Pass |
| Reliability | 5.0 | 4.0 | 5.0 | 4.5 | 4.5 | **4.6** | ✅ Pass |
| Performance | 4.0 | 3.5 | 5.0 | 5.0 | 4.5 | **4.4** | ✅ Pass |

### Detection Summary

- **Security** — 6/6 expected issues found, 0 false positives, no scope bleed
- **Reliability** — 6/6 expected + 3 legitimate bonus findings, 0 false positives
- **Performance** — 4/5 expected issues found (missed low-severity inline style object), 0 false positives

### Known Characteristics

- **Severity overcalibration** — Reviewers tend to rate issues slightly higher than warranted (e.g., Medium→High). This is a known LLM pattern and does not cause findings to be dropped.
- **Cross-domain overlap** — Reliability may flag unbounded arrays (a performance concern) as an OOM/crash risk. Both perspectives are valid.
- **Low-severity gaps** — Performance missed one Low-severity finding (object literal in render). This is acceptable given the quality gate threshold.

Golden test fixtures are located at `test/golden-test/` with `EXPECTED-FINDINGS.md` documenting all 17 planted issues.

## Guideline Format

Guidelines use the **Guideline** document format:

```markdown
# Guideline: Title

## Scope
(glob/regex patterns for file matching)

## Rationale
(why this guideline exists)

## Detection Instructions
(how to detect violations)

## Negative Example
(example demonstrating a violation)

## Positive Example
(corrected example)
```

## Best Practices

1. **Organize guidelines by category** — Group into folders like `security/`, `performance/`, `concurrency/`
2. **Use specific scopes** — Narrow file matching with precise glob/regex patterns to reduce noise
3. **List non-violations first** — In detection instructions, define acceptable patterns before violation patterns to reduce false positives
4. **Use folder rules** — Map specific guidelines to specific directories for targeted reviews
5. **Run incrementally** — Use commit range or staged modes for PR reviews instead of full scans
6. **Use specialist reviewers** — Enable domain-specific reviewers for security, reliability, and performance analysis beyond guideline-based reviews
7. **Create custom reviewers** — Build team-specific reviewers (e.g., accessibility, documentation quality) and place them in the `agents/` directory following the `Octane.{Name}Reviewer.agent.md` naming convention
8. **Use multi-model review** — Run specialist reviewers across multiple AI models for wider coverage and higher confidence findings

## Specialist Reviewer Configuration

Specialist reviewers run automatically with zero configuration. To customize:

```yaml
# .github/gatekeeper/gkpconfig.yml

# OPTIONAL — omit to enable all discovered reviewers
reviewers:
  enabled:
    - security
    - reliability
    - performance
    - quality

# Per-folder reviewer restrictions (optional)
folder_rules:
  'src/api/**':
    reviewers: [security, reliability]
  'src/ui/**':
    reviewers: [performance]
```

| Config state | Behavior |
|---|---|
| No `reviewers` key | All discovered `Octane.*Reviewer.agent.md` agents run |
| `reviewers.enabled: [security, reliability]` | Only security and reliability reviewers run |
| `reviewers.enabled: []` | Specialist reviewers disabled (guideline-only review) |

## Creating Custom Reviewers

To create your own specialist reviewer:

### 1. Create the reviewer file

Create an `Octane.{Name}Reviewer.agent.md` file in the `agents/` directory:

```
agents/
├── Octane.SecurityReviewer.agent.md      # built-in
├── Octane.ReliabilityReviewer.agent.md   # built-in
├── Octane.PerformanceReviewer.agent.md   # built-in
├── Octane.QualityReviewer.agent.md       # built-in
└── Octane.MyCustomReviewer.agent.md      # your custom reviewer
```

### 2. Add YAML frontmatter

```yaml
---
name: MyCustomReviewer
description: "Specialist reviewer: analyzes code for [your focus area]."
tools: ["*"]
scope_globs:
  - "**/*.ts"
  - "**/*.js"
---
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Agent name (PascalCase, used for dispatch) |
| `description` | Yes | Description including "Specialist reviewer:" prefix |
| `scope_globs` | Yes | File patterns this reviewer cares about |
| `tools` | Yes | Always include `read` and `search` |
| `severity_range` | No | Min/max severity range (default: `[0.7, 0.9]`) |

### 3. Include required sections

Your reviewer MUST include these sections (copy from any built-in reviewer as a template):

- **Autonomous Execution** — No interaction, no clarifying questions
- **JSON Output Requirement** — Output between `========= JSON START/END =============` markers
- **Role** — What this reviewer analyzes
- **Analysis Focus** — Specific categories of issues to detect
- **Anti-Hallucination Rules** — Never report without reading actual code
- **Output Format** — Same violations JSON schema as built-in reviewers

### 4. Use the standard output schema

All reviewers must output the same JSON structure:

```json
{
  "guidelines_reviewed": ["my-custom-review"],
  "files_reviewed": ["path/to/file.ts"],
  "violations": [
    {
      "file_name": "path/to/file.ts",
      "startline": "42",
      "startrow": "1",
      "endline": "45",
      "endrow": "80",
      "detection": "ISSUE TYPE: [specific problem]",
      "violation": "IMPACT: [what goes wrong]",
      "guideline": "my-custom-review",
      "suggestion": "FIX: [specific solution]",
      "severity": "Critical|High|Medium|Low"
    }
  ],
  "non_violations": []
}
```

### 5. Enable (optional)

If your `gkpconfig.yml` has a `reviewers.enabled` list, add your reviewer's short name (the `{Name}` portion of `Octane.{Name}Reviewer.agent.md`, lowercased). If there's no `reviewers` config, your reviewer activates automatically.

## Multi-Model Review

Run specialist reviewers across multiple AI models for wider coverage. Different models have different strengths — findings confirmed by multiple models are higher confidence. Multi-model dispatch is handled directly by the Gatekeeper orchestrator.

```yaml
# gkpconfig.yml
reviewers:
  enabled: [security, reliability, performance, quality]
  models:
    - claude-sonnet-4-5       # balanced speed/quality
    - claude-opus-4-5         # deep reasoning
    - gpt-4o                  # cross-vendor perspective
```

| Config state | Behavior |
|---|---|
| No `models` key | Each reviewer runs once on its default model (backward compatible) |
| `models: [claude-sonnet-4-5, claude-opus-4-5]` | Each reviewer dispatched 2× (once per model) |

Deduplication happens in Stage 3 (Aggregate): findings from different models at the same file + overlapping line range + same severity are merged into a single **high-confidence** finding. Unique single-model findings are kept and flagged for human review. The final report includes a **Model Coverage Summary**.

## Critic — Lightweight Code Review

The **CriticReview** agent provides a fast, standalone code review outside the full Gatekeeper pipeline. Adapted from the [AI-First Dev Starter Pack](https://github.com/1ES-AI/ai-first-dev-starter-pack), it analyzes code changes for correctness, security, performance, error handling, maintainability, clarity, consistency, and testability.

Use CriticReview when you want a quick review of local changes without running the full guideline-based pipeline:

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.CriticReview `
  --no-default-mcps `
  --allow-all
```

By default it compares against `main`. To specify a different base branch:

```powershell
agency copilot --agent gatekeeper-octane-version:Octane.CriticReview `
  --no-default-mcps `
  -p "targetBranch: my-feature-base" `
  --allow-all
```

Each finding includes a severity level, confidence score, and a concise code example showing the corrected pattern.

## Related Scenarios

- **[Test Analysis](../test-analysis/README.md)** — Analyze test results and coverage
- **[PR Insights](../pr-insights/README.md)** — Pull request analysis and insights

## Difficulty

**Advanced** — Requires understanding of:
- Code review guidelines and guideline authoring
- Multi-agent orchestration and parallel pipelines
- SQL-based pipeline state management
- Git diff modes and file filtering

## Tags

`code-review` `guidelines` `automation` `quality` `parallel-pipeline`
