# Test Hardening Scenario

## Overview

The Test Hardening scenario takes **existing** tests and improves their quality without changing test intent or modifying production code. It audits passing tests for latent weaknesses and produces a minimal-diff PR with stronger assertions, missing edge cases, stability-by-design changes, and better parameterization.

> For fixing observed flaky test failures, see `flaky-test-fix`. This scenario proactively audits passing tests to strengthen them.

It fills the gap between `unit-test-generation` (which creates new tests) and `coverage-only-test-analysis` (which only flags low-value tests).

## When to Use

- A test suite is going into a release branch and you want to harden it before promotion.
- After onboarding or a framework migration, when test quality is uneven.
- A test was flagged by `coverage-only-test-analysis` as low-value but you want concrete fixes.
- You suspect a test has latent flakiness (`Thread.Sleep`, `DateTime.Now`, shared statics, hard-coded ports) and want to remove it before it shows up in CI.
- You want to collapse near-duplicate test methods into data-driven tests.

Do **not** use this scenario to:
- Generate new tests for uncovered code (use `unit-test-generation`).
- React to an observed flaky failure (use `flaky-test-fix`).
- Only report on test runs / coverage (use `test-analysis`).

## Prerequisites

- A Git repository with existing tests (.NET MSTest/xUnit/NUnit, pytest, Jest, Vitest, or Mocha).
- The test project builds locally.
- For ADO PR submission: the `ado-stdio/*` MCP server configured per the shared `mcp.json`.
- For GitHub PR submission: the [`gh` CLI](https://cli.github.com/) installed and authenticated (`gh auth login`).
- For stress validation: the `deflaker/*` MCP server (optional; falls back to local repeated runs).
- For code navigation: the `code-search/*` MCP server (optional; falls back to workspace `search` / `read` / `semantic_search`).

## What's Included

### Agents
- **TestHardening** -- Senior Test Engineer that audits, edits, validates, and submits the PR (ADO or GitHub). A single agent runs all four phases via dedicated prompts.

### Prompts
- **Octane.TestHardening.Audit** -- Reads the target test(s) and produces a structured **Test Hardening Audit** report ranked by impact across six hardening categories. Every finding must pass a Bug Gate: "What specific incorrect behavior would go undetected with the current test but be caught with the proposed change?"
- **Octane.TestHardening.Improve** -- Applies the audit findings as minimal, test-only edits and validates via build, single-test, and (for stability-by-design) stress-test. Enforces a completeness invariant: applied + skipped = total audit findings.
- **Octane.TestHardening.Submit** -- Pushes the branch and opens a pull request. ADO repos use the `ado-stdio/*` MCP tools; GitHub repos use `gh pr create`. Creates Draft PRs when local validation was blocked. Unknown remotes get a `Submit skipped` summary with manual-PR instructions.
- **Octane.TestHardening.End2End** -- End-to-end orchestrator that chains audit -> improve -> (optional) submit. Stops early if audit finds zero findings.
- **Octane.TestHardening.Folder** -- Folder-mode orchestrator. Classifies the input path, fans out per-file audits in parallel (one sub-agent per test file), then runs a **hybrid** improve: project sub-agents run in parallel (one per test project), files inside a project are improved sequentially, and stress validation fans out per test class. One build per project; one PR for the whole folder. Single-file paths short-circuit to `End2End`; production files, empty folders, and over-cap folders stop with a classification message.

### Hardening Categories
1. **Assertion strength** -- replace no-op or over-broad assertions with explicit, diagnostic ones.
2. **Edge-case coverage** -- add boundary inputs the test name implies but the body misses (null, empty, max, negative, unicode, cancellation, concurrent).
3. **Stability-by-design** -- remove latent races (`Thread.Sleep`, `DateTime.Now`, shared statics, hard-coded ports) before they manifest as flakiness.
4. **Parameterization** -- collapse near-duplicate test methods into `[DataRow]` / `[Theory]` / `parametrize` rows.
5. **Naming and intent** -- rename tests whose names don't describe the behavior; clarify Arrange/Act/Assert when the body is non-trivial.
6. **Mock saturation** -- reduce over-mocked tests so they validate real behavior. Cross-links to `coverage-only-test-analysis` patterns.

### Skills (colocated under `skills/`)
- **hardening-recipes** -- Single source of truth for the six categories (audit + improve views).
- **hardening-guardrails** -- Cross-phase invariants shared by all four prompts.
- **run-summary** -- Versioned output schema (`RunSummary v1`) that downstream prompts parse.
- **build-outcome-classification** -- `LOCAL_BUILD_OK` / `LOCAL_BUILD_FAILED_BY_EDIT` / `LOCAL_BUILD_BLOCKED` decision rules.
- **stress-validation-protocol** -- When to stress-test, pass-rate target, partial-revert rules.
- **analysis-report** -- Audit report template.
- **build-and-test** -- Build and single-test validation.
- **stress-test** -- Stress runner mechanics (cloud + local modes).
- **pr-description** -- PR template adapted for hardening.
- **test-hardening-fixtures** -- Golden-output fixtures used by maintainers to diff prompt-run output and detect regressions.
- **test-file-discovery** -- Classifies the `test path` input (file vs. folder vs. production file vs. ambiguous) and enumerates test files in a folder. Used by `Octane.TestHardening.Folder` before any audit work.

### Shared Skills (consumed from `artifacts/shared/skills/`, declared in `scenario.json#shared_artifacts`)
- **save-branch-and-push** -- Generic branch creation; this scenario sets `$phaseTag = "harden"` for the `dev/<alias>/harden<short-guid>` pattern.
- **detect-default-branch** -- Generic default-branch detection (network + offline fallbacks).

### MCP Servers (Optional)
None are required.

- **code-search** -- preferred for codebase navigation; falls back to workspace `search` / `read` / `semantic_search`.
- **deflaker** -- used by stress validation when stability-by-design edits are applied.
- **azure-devops** -- required only for the Submit phase on ADO repositories. GitHub Submit uses the `gh` CLI instead (see Prerequisites).

## Example Prompts

```text
# Audit a single test (read-only; no edits)
@Octane.TestHardening.Audit "Namespace.Class.TestMethod"

# Apply the audit findings to the test file (test-only edits + validation)
@Octane.TestHardening.Improve

# Submit a PR (ADO via MCP, GitHub via gh CLI)
@Octane.TestHardening.Submit

# End-to-end: audit -> improve -> validate -> submit
@Octane.TestHardening.End2End "Namespace.Class.TestMethod"

# End-to-end with a category filter
@Octane.TestHardening.End2End "Namespace.Class.TestMethod" "assertion-strength,stability-by-design"

# Audit with optional stability evidence URL (ADO work item or issue)
@Octane.TestHardening.Audit "Namespace.Class.TestMethod" "<ado-work-item-url>"

# Folder mode: harden every test file in a folder (parallel audit, single PR)
@Octane.TestHardening.Folder "src/MyService/Tests/Unit/"

# Folder mode with a category filter and explicit cap raise
@Octane.TestHardening.Folder "src/MyService/Tests/" "assertion-strength,stability-by-design" "" 50
```

## Expected Output

### Audit phase

A structured audit report ending with a `Hardening Recommendation Summary` table:

```
Schema: RunSummary v1 | Phase: Audit
Test Hardening -- Audit complete.
  Target:             Namespace.Class.TestMethod
  Test framework:     MSTest
  Files inspected:    1 test file, 2 production files
  Findings kept:      4   (high=1, medium=2, low=1)
  Findings discarded: 6   (failed Bug Gate)
  Production-blocked: 0   (requires-production-change=true)
  Findings overflow:  0
  Avg confidence:     8.2
  Stability evidence: not provided
```

### Improve phase

Per-finding before/after diffs, the skipped-findings list, and a RunSummary block.

### Submit phase

The PR URL plus a `Submit complete.` RunSummary block. The same prompt handles ADO (via `ado-stdio/*` MCP) and GitHub (via `gh pr create`). Non-ADO/non-GitHub remotes receive a `Submit skipped.` block with manual-PR instructions.

### End2End phase

The orchestrator emits an aggregated RunSummary block plus the per-finding bullets and developer Next-Steps section. See `prompts/Octane.TestHardening.End2End.prompt.md` for the full template.

## Hard Guardrails

See `skills/hardening-guardrails/SKILL.md` for the eight cross-phase invariants. Summary:

- **Production code is never modified.**
- **No test deletions.** Every existing test method (including `[Ignore]` / `[Skip]`) is preserved.
- **No new dependencies. No test framework changes.**
- **Minimal diff.** Edits are scoped to the lines each finding identifies.
- **No new sleeps.** Replacing one sleep with another is not stability-by-design.
- **No blind masking.** No `[Ignore]`, blind retries, or weakened assertions to make a test pass.
- **Preserve every assertion.** Replacements must verify at least the same property with equal or greater specificity.

## Quality Controls
- **Bug Gate**: every audit finding must state what wrong behavior goes undetected. Findings that only improve style are discarded.
- **Impact definitions**: High/Medium/Low have concrete, testable criteria (not gut feeling).
- **Confidence rubric**: 0-10 scale with explicit deduction rules (see `skills/hardening-recipes/SKILL.md`). Findings below 7 are discarded.
- **Discard step**: weak findings are killed before ranking. Fewer, sharper findings beat a padded report.
- **Edit verification**: after each edit, the agent verifies it closes the detection gap and doesn't weaken existing assertions.
- **Completeness invariant**: applied + skipped must equal total audit findings. Silent drops are a hard error.
- **Search before applying**: helpers and patterns are verified to exist in the project before use.

## Performance

The scenario uses parallelism where it preserves the report and the diff, and stays serial where parallelism would risk quality. Authoritative rules: see `agents/Octane.TestHardening.agent.md#parallelism--caching`.

| Where | Mode | What changes |
|-------|------|--------------|
| Audit -- evidence gathering | Parallel | `code-search/*` calls and file reads in Todos 3, 5, 6 fan out as batches. Same evidence, same reasoning, same report -- only delivery is faster. |
| Audit -- category walk & ranking | Serial | Categories share evidence; cross-category ranking depends on the full set. |
| Folder mode -- audit fan-out | Parallel via `agent` tool | One sub-agent per test file; isolated contexts. |
| Folder mode -- improve across projects | Parallel via `agent` tool | Build artifacts are project-scoped; cross-project edits are independent. |
| Folder mode -- improve inside a project | Serial | Shared fixtures and shared build artifacts; preserves assertion-preservation and monotonic skip-set rules. |
| Folder mode -- stress across classes | Parallel via `agent` tool | Different classes use different fixtures; per-class pass-rate is statistically valid. |
| Folder mode -- stress inside one class | Serial | `[ClassInitialize]` / `conftest.py` class fixtures are shared mutable state. |
| Single-finding application | Serial | Concurrent edits on the same file would race on lines and break minimal-diff guarantees. |

**Session-scope cache.** Within one agent session, the scenario reuses `code-search/_get_started` results per `repo + branch` and already-read file contents. The cache flushes on branch or repo change and is not persisted across sessions.

**Backward compatibility.** Single-file invocations (`Audit`, `Improve`, `Submit`, `End2End`) produce the same report content and the same RunSummary blocks as before. Parallelism changes how evidence is gathered, not the reasoning that produces findings.

## Use Cases
- Hardening test suites before a release branch.
- Strengthening unit-test quality after onboarding or migration.
- Proactively removing latent flakiness before it shows up in CI.
- Improving low-value tests flagged by `coverage-only-test-analysis`.

## Difficulty
**Intermediate** -- requires understanding of testing frameworks and the production code under test.

## Tags
`testing` `test-quality` `hardening` `assertions` `stability-by-design` `parameterization`
