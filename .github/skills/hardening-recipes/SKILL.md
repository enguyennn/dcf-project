---
name: hardening-recipes
description: Single source of truth for the six test-hardening categories. Defines what to find (audit view) and how to apply (improve view) for each category so the two phases share one specification.
---

# Hardening Recipes

This skill defines the six hardening categories used by the Audit and Improve phases. Audit references the **What to find** column to produce findings. Improve references the **How to apply** column to apply edits. Both phases work off the same definitions so they cannot drift.

For the universal rules that apply across categories (production off-limits, no test deletions, etc.), see `../hardening-guardrails/SKILL.md`.

## The Six Categories

### 1. Assertion strength

**What to find (audit view).** Tests that pass when the system under test produces a wrong result. Specifically:
- `Assert.True(true)` / `Assert.Pass()` placeholders.
- Missing assertion blocks (test ends after Act with no Assert).
- Over-broad `Assert.NotNull(x)` where a value-level assertion is warranted by the test name.
- Mock `.Verify()` calls that do not validate the call's effect on the system under test.
- Exception-only tests that catch an exception but do not inspect its type or message.

**How to apply (improve view).**
- Replace `Assert.True(true)` with a value assertion against the result.
- Replace `Assert.NotNull(x)` with `Assert.AreEqual(expected, x.Property)` when the test name implies a value check.
- Add a custom message to assertions that lack one (`"Expected ... but got ..."`).
- The replacement must check at least the same property as the original and must not change the test's intent.

**Calibration.**
- **BAD:** "`Assert.IsTrue(result.IsValid)` should use `Assert.That(result.IsValid, Is.True)` for better failure messages." -- style preference; the test catches the same bugs.
- **GOOD:** "Case 1 asserts `ValidateSettings == true` but not `serviceConfigValidationError == ""`. Cases 6/7 in the same method already do. A `true` return with non-empty error string would pass Case 1 undetected."

### 2. Edge-case coverage

**What to find (audit view).** Boundaries the test claims to cover (per the method name and Arrange section) but does not exercise: null, empty, single-element, max-size, negative, unicode, cancellation, concurrent access.

**How to apply (improve view).**
- Add `[DataRow(null)]` / `[DataRow("")]` / boundary rows when the existing test name implies handling them but the body does not.
- Never add a separate new test method; promote the existing method to data-driven if needed.
- Preserve every original input value as a row when collapsing.

**Calibration.**
- **BAD:** "Method `ProcessOrder_ReturnsSuccess` only tests positive paths -- should also cover failure cases." -- vague; no specific boundary cited.
- **GOOD:** "`ParseSubnet_ReturnsValid` only exercises `10.0.0.0/24`. The production method returns `false` for prefix lengths > 30 (line 87), but no `/31` or `/32` row exists. A regression weakening the `> 30` check would pass."

### 3. Stability-by-design

**What to find (audit view).** Latent non-determinism sources:
- `Thread.Sleep`, `Task.Delay` used as a synchronization primitive.
- `DateTime.Now` / `DateTime.UtcNow` without injection.
- Unseeded randomness affecting assertions.
- Shared static state across test methods.
- Hard-coded ports, hard-coded filesystem paths.
- Missing `using` / dispose on files, processes, timers, HTTP clients, cancellation sources.
- Order-dependent collection assertions where order is incidental.
- Retry-without-bound, infinite poll loops.
- Unisolated filesystem / network / process state.

**How to apply (improve view).**
- **Search the project first** for the required helper (`WaitForCondition`, `WriteFileWithRetry`, `TimeProvider`, `IClock`, deterministic-random helpers, temp-directory fixtures). If found, cite the file and use it. If not found, mark `requires-helper` and skip.
- Replace `Thread.Sleep(N)` / `await Task.Delay(N)` / `await new Promise(r => setTimeout(r, N))` with the project's existing wait-for-condition helper (e.g., `WaitForCondition`, `waitFor` from `@testing-library`, `vi.waitFor`, `pytest`'s `tenacity` retry, etc.). When no helper exists, mark `requires-helper` and skip.
- Replace `DateTime.UtcNow` / `Date.now()` / `new Date()` / `time.time()` with the existing clock abstraction or framework fake timer (`vi.useFakeTimers()` + `vi.setSystemTime(...)`, `jest.useFakeTimers()` + `jest.setSystemTime(...)`, `freezegun` in pytest). Cite the existing usage; if none, mark `requires-helper`.
- Seed `Random` / `Math.random` / `random.random()` or use existing deterministic data builders when randomness affects assertions.
- Assert unordered equivalence when order is intentionally irrelevant (`CollectionAssert.AreEquivalent`, `expect(arr).toEqual(expect.arrayContaining(...))`, `assert sorted(actual) == sorted(expected)`).
- Isolate filesystem state with per-test temp paths and reliable cleanup (`Path.GetTempFileName` + try/finally, `tmp_path` pytest fixture, `os.tmpdir()` + `afterEach` cleanup).
- Use ephemeral ports through an established helper.
- Dispose all owned resources reliably (`using` / `IDisposable`, `afterEach` teardown, `try/finally`).
- Retry / wait logic must complement explicit assertions, not replace them.

**Calibration.**
- **BAD:** "`Thread.Sleep(100)` is a code smell; consider increasing to `Thread.Sleep(500)` for stability." -- violates `no-new-sleeps` guardrail.
- **GOOD:** "Line 42 sleeps 100ms then asserts the file exists. `TestHelpers.WaitForFile(path, TimeSpan.FromSeconds(5))` already exists at `TestHelpers/FileWaiters.cs:18` and is used by 7 sibling tests. Under CI load the sleep is insufficient; the test flakes ~3% per the cited ADO bug."

### 4. Parameterization

**What to find (audit view).** Near-duplicate test methods that differ only in input values and could collapse to `[DataRow]` / `[Theory]` / `parametrize` without reducing coverage clarity.

**How to apply (improve view).**
- Collapse only when the methods differ exclusively in input/expected pairs.
- Preserve every original input value as a row.
- Use the framework's native mechanism:
  - **.NET**: `[DataRow]` (MSTest), `[TestCase]` (NUnit), `[Theory] + [InlineData]` (xUnit).
  - **Python**: `@pytest.mark.parametrize`.
  - **JS/TS**: `test.each([...])` / `it.each([...])` (Jest, Vitest), `describe.each` for fixture sharing.
  - **Go**: table-driven subtests via `t.Run(name, func)`.

**Calibration.**
- **BAD:** "`TestFoo_A` and `TestFoo_B` look similar -- could be parameterized." -- no proof they differ only in inputs.
- **GOOD:** "`TestValidate_Email_Accepts_Gmail`, `TestValidate_Email_Accepts_Outlook`, `TestValidate_Email_Accepts_Yahoo` differ only in the input string and the expected result is identical (`true`). Collapse to `[DataRow]` rows; no coverage loss."

### 5. Naming and intent

**What to find (audit view).** Test names that do not describe the verified behavior; missing or out-of-order Arrange / Act / Assert blocks; setup logic that obscures intent.

**How to apply (improve view).**
- Rename a test only if every reference site within the same test project is updated atomically.
- Add Arrange / Act / Assert comments only when the body is non-trivial. Do not pad short tests with ceremony.

**Calibration.**
- **BAD:** "`Test_ValidateConfig` uses underscores; rename to `ValidateConfig_ShouldPass`." -- style preference; no bug caught.
- **GOOD:** "`TestNetworkValidation` asserts `result.Code == 0`. The test name says nothing about which validation branch is exercised; the body exercises only the IPv4 branch. Rename to `ValidateIPv4Subnet_AcceptsClassC` so a regression that breaks IPv4-only coverage is named in the failure report."

### 6. Mock saturation

**What to find (audit view).** Tests where the system under test is so heavily mocked that no real behavior is validated.

**How to apply (improve view).**
- Reduce mock setup to the minimum required for the assertion.
- If reduction would change the assertion target or require production seams, mark `requires-production-change: true` and skip.

**Calibration.**
- **BAD:** "Too many mocks; refactor to use real dependencies." -- not actionable; would change test scope.
- **GOOD:** "`mockRepo.Setup(r => r.GetUser).Returns(u)`, `mockCache.Setup(c => c.Get).Returns(u)`, `mockLogger.Setup(l => l.Log)`, `mockClock.Setup(c => c.Now).Returns(now)` -- but the assertion is `Assert.AreEqual(u.Id, result.Id)`. Only `mockRepo` is needed for that assertion; the other three setups are dead. Remove them; failure mode `logic`: a bug in `cache` or `logger` would still pass."

## Failure-Mode Lens

Every Audit finding must map to at least one concrete failure mode below. If a finding cannot name one of these, it is style noise and must be discarded:

- **runtime**: null dereference, invalid cast, undefined method/member, invalid state transition, exception type mismatch.
- **logic**: stale variable, wrong branch, missing condition, inverted condition, incomplete implementation, wrong aggregation.
- **validation**: invalid input accepted, valid input rejected, boundary skipped, missing error-string / error-code check.
- **data-integrity**: data truncation, stale data, corrupt serialization, missing ID / key propagation, shared mutable state.
- **security**: missing authorization, injection, sandbox escape, secret / PII leak, bypassed staleness / permission guard.
- **concurrency**: race, deadlock / hang, leaked process / global state, unsafe parallel fixture / static mutation.
- **error-handling**: swallowed error, wrong exception type, raw traceback / user-facing leak, retry without bound.
- **performance**: claimed optimization is a no-op, accidental O(n^2), unbounded polling / looping.

## Impact Definitions

- **High**: the current test can pass when the system under test produces a *wrong result*.
- **Medium**: the current test can pass *sometimes* when it should fail, or fail *sometimes* when it should pass (latent stability risk).
- **Low**: the current test detects the bug but the diagnostic is unhelpful, or near-duplicate methods could be collapsed.

## Bug Gate

Every Audit finding must answer: *"What specific incorrect behavior would pass undetected with the current test but be caught with the proposed change?"* Findings that cannot answer this are not hardening findings; they are code-review comments and must be discarded.

## Confidence Rubric

The Audit phase assigns a 0-10 confidence score to every finding. Use these definitions:

- **9-10**: verbatim ready-to-apply snippet + sibling-test evidence + named failure mode + reproduction trace (for high-impact).
- **7-8**: verbatim snippet + production-one-level evidence + named failure mode.
- **5-6**: speculative; no verbatim snippet OR no production evidence OR no named failure mode.
- **<= 4**: style-only or speculative; discard.

The Improve phase drops any finding whose confidence is below 7 with reason `low-confidence-after-audit`.
