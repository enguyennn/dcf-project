---
description: "Test-hardening guardrails: applied automatically when editing test files. Mirrors hardening-guardrails skill so passive edits get nudged toward stability-by-design without invoking a prompt."
applyTo: "**/*Tests*.cs,**/*Test.cs,**/Tests/**/*.cs,**/test_*.py,**/*_test.py,**/tests/**/*.py,**/*.test.{ts,tsx,js,jsx,mjs,cjs},**/*.spec.{ts,tsx,js,jsx,mjs,cjs},**/__tests__/**/*.{ts,tsx,js,jsx},**/*_test.go"
---

# Test Hardening — Editing Guardrails

These guardrails apply to **any** edit you make to a test file, regardless of which prompt is active. They mirror the invariants in `../skills/hardening-guardrails/SKILL.md` so test edits stay safe even outside the audit/improve workflow.

## Hard Rules

1. **Production code is off-limits.** A test-file edit must not require a sibling change to production code. If a finding only works with a production seam (new interface, new injection point, new accessor), mark it `requires-production-change` and skip. Do not invent the seam.
2. **Preserve every existing test method**, including `[Ignore]`, `[Skip]`, `it.skip`, `@pytest.mark.skip`. Removing or replacing a skipped test loses the institutional reason it was skipped.
3. **Preserve every existing assertion.** You may *strengthen* (`Assert.Equal` → `Assert.Equal` + bounds check) or *add* assertions. You may not delete, weaken, or replace an assertion with a less-specific one.
4. **No new sleeps.** Do not introduce `Thread.Sleep`, `await Task.Delay`, `await new Promise(r => setTimeout(...))`, `time.sleep`, or equivalent. If synchronization is needed, use an existing project helper (`WaitForCondition`, `waitFor`, `vi.waitFor`, `tenacity` retry). If no helper exists, mark `requires-helper` and skip.
5. **No new wall-clock dependencies.** Do not call `DateTime.Now`, `Date.now()`, `new Date()`, `time.time()` from a test body. Use the project's existing clock abstraction or framework fake timer (`vi.useFakeTimers`, `jest.useFakeTimers`, `freezegun`, injected `IClock` / `TimeProvider`).
6. **No unseeded randomness in assertions.** If a test asserts against random output, seed the generator or use the project's deterministic data builder.
7. **No hard-coded ports, paths, or hostnames.** Use ephemeral ports through an existing helper; use per-test temp directories (`Path.GetTempFileName`, `tmp_path` pytest fixture, `os.tmpdir()` + cleanup).
8. **Dispose owned resources.** `using` / `IDisposable` in .NET; `afterEach` cleanup in JS/TS; `try/finally` or pytest fixtures in Python.

## When in Doubt — Stop

If a proposed edit would violate any of the above, surface the conflict explicitly and stop. Do not silently weaken a guardrail to make a finding fit.

## Why This Exists

This scenario operates on tests that already pass. The cost of a wrong edit (silently dropping an assertion, replacing a real check with a no-op) is much higher than missing a finding. These guardrails are the floor; the full audit/improve workflow in `../skills/hardening-guardrails/SKILL.md` adds further constraints.
