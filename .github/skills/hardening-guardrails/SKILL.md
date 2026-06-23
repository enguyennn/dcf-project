---
name: hardening-guardrails
description: Cross-prompt invariants for the test-hardening scenario. All four prompts (Audit, Improve, Submit, End2End) reference these guardrails so the same rule is not repeated across files.
---

# Hardening Guardrails

These eight rules apply to every phase of the test-hardening workflow. Each prompt may add **phase-specific** rules on top of these, but it must not relax or contradict any rule below.

## The Eight Invariants

1. **Production code is never modified.** Hardening scope is the test code only. Findings that require a production-code seam must be reported with `requires-production-change: true` in the Audit and skipped in the Improve.
2. **No test deletions.** Existing test methods, including those decorated `[Ignore]` / `[Skip]` / `[Fact(Skip=...)]` / `pytest.mark.skip`, are preserved. They may be owned by other teams.
3. **No new dependencies.** Use only libraries already referenced by the test project. Do not add NuGet packages, npm packages, pip requirements, or framework switches.
4. **No test framework changes.** Do not migrate MSTest -> xUnit, NUnit -> MSTest, JUnit -> TestNG, etc. If a finding implies a framework switch, skip it.
5. **Minimal diff.** Edit only the lines required by the finding. No drive-by formatting, no reordering, no rename refactors unless the finding itself is a naming finding with every call site updated atomically.
6. **No new sleeps.** Replacing `Thread.Sleep(N)` with `Thread.Sleep(M)` is not stability-by-design. Sleeps may only be replaced with an awaited condition helper that already exists in the project.
7. **No blind masking.** Do not add `[Ignore]`, `[Skip]`, broad `catch` blocks, blind retries, or looser assertions to make a test pass. If a test is failing for a real reason, surface the reason; do not hide it.
8. **Preserve every assertion.** When replacing an assertion, the replacement must verify at least the same property as the original, with equal or greater specificity. If the replacement cannot be confirmed strictly stronger, skip the finding and report.

## Application by Phase

| Phase | How the invariants apply |
|-------|--------------------------|
| Audit | A proposed finding that would violate any invariant is discarded. Findings that require a production-code seam are reported with `requires-production-change: true` so Improve can skip them. |
| Improve | An edit that would violate any invariant is reverted before continuing. Skip reasons map to specific invariants: `requires-production-change` (rule 1), `requires-helper` when rule 6 forbids inventing a new wait helper, etc. |
| Submit | A `git diff --stat` pre-push check enforces rule 1 (no production files in the diff) and rule 4 (no `*.csproj` / `package.json` / `pyproject.toml` mutations). |
| End2End | The orchestrator does not relax these rules. If a sub-prompt reports a violation, End2End surfaces it in the developer summary. |

## Why these live in a shared skill

Earlier versions of this scenario duplicated these rules across all four prompts and the agent file. The duplication drifted (slightly different wording each time) and consumed prompt tokens without changing behavior. Centralizing here lets each prompt say *"Follow `hardening-guardrails`."* once and spend its token budget on phase-specific logic.
