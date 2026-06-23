---
name: stress-validation-protocol
description: Stress-validate any stability-by-design edit after a successful local build. Defines the pass-rate target, partial-revert rules, and cloud-validation handoff.
---

# Stress Validation Protocol

Stability-by-design edits change non-determinism behavior; a single passing run is not evidence. Stress validation runs the affected test methods repeatedly and verifies a 100% pass rate before shipping.

## When to Run

Run this protocol when **both** conditions hold:
- The Improve phase applied at least one `stability-by-design` finding.
- The build outcome is `LOCAL_BUILD_OK` (see `../build-outcome-classification/SKILL.md`).

If the build outcome is `LOCAL_BUILD_BLOCKED`, mark stress validation `deferred-to-cloud` and continue — do not stress on a broken local environment.

## Execution

1. Read `../stress-test/SKILL.md` and run the stress run on the affected test methods.
2. Pass-rate target: **100%** across all iterations.
3. **Local mode acceleration (optional).** When local mode is selected and the iteration count × per-iteration time bottlenecks wall-clock, use the **Parallel Local Mode** in `../stress-test/SKILL.md#45-parallel-local-mode-optional`. Pass-rate target and partial-revert rules are unchanged; only the dispatch is concurrent.

## On Failure (any iteration fails)

1. **Identify** the stability-by-design finding(s) that touched each failing test method.
2. **Revert ONLY those** finding(s). Keep all other edits (non-failing stability, assertion-strength, edge-case, parameterization, naming, mock-saturation).
3. **Set RunSummary fields**:
   - `Stress validation: stress-failed`
   - `Cloud validation: required`
4. **Add skipped-finding entry** with reason `stress-failure-investigation-needed`, listing test method, iterations attempted, pass count.
5. **Do NOT abort.** The rest of the hardening is still valid; Submit creates a Draft PR and the cloud build re-stresses.

## Outcomes

| Outcome | RunSummary value |
|---------|------------------|
| 100% pass | `stress-validation: <pass-rate>%` and `cloud-validation: not-required` (unless build was BLOCKED) |
| At least one fail | `stress-validation: stress-failed`, `cloud-validation: required`, PR created as Draft |
| Skipped (build BLOCKED) | `stress-validation: deferred-to-cloud`, `cloud-validation: required` |
| No stability-by-design edits applied | `stress-validation: not-applicable` |

## Concurrent Execution (Folder-Mode Only)

The single-file Improve flow uses this protocol serially; the rules in this section apply **only** when invoked from `Octane.TestHardening.Folder.prompt.md`.

### Allowed: parallelize across different test classes

When applied `stability-by-design` findings touch test methods in **two or more different test classes** (different `[TestClass]` / pytest class / xUnit class / Go test file), dispatch one stress sub-agent per class via the `agent` tool. Sub-agents run in parallel; each follows the Execution and On Failure rules above for its own class only.

This is safe because:
- Different test classes have **different fixtures** (`[ClassInitialize]`, `conftest.py` class scope, xUnit class fixtures) — no shared mutable state across classes.
- Pass-rate is a **per-class statistic** — combining classes would dilute the signal anyway.
- Partial-revert rules operate on **findings**, which always map to specific test methods inside a specific class — reverts stay local.

### Forbidden: parallelize methods within one class

Within a single test class, stress runs stay **serial**. Reasons:
- `[ClassInitialize]` / `setup_class` / class-scoped fixtures are shared mutable state.
- The 100% pass-rate target assumes test methods do not race on shared resources.
- MSTest `[Parallelize(Scope = MethodLevel)]` requires explicit thread-safety annotations that this protocol does not verify.

### Aggregation rules

The Folder orchestrator collects per-class outcomes and rolls them up:
- **All classes 100% pass** → folder-level `stress-validation: <weighted-pass-rate>%`, `cloud-validation: not-required`.
- **Any one class stress-failed** → folder-level `stress-validation: stress-failed`, `cloud-validation: required`. The PR is created as Draft. Stress-failed classes contribute their failing findings to the partial-revert set; non-failing classes retain their edits.
- **Any one class deferred-to-cloud** (its build was BLOCKED in folder mode's per-project build step) → folder-level `stress-validation: deferred-to-cloud`, `cloud-validation: required`.
