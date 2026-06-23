# Audit Golden Fixture

This fixture is a canonical Audit-phase emission against the synthetic test case below. Maintainers diff future Audit runs against this file.

## Synthetic Test Case

`src/Services/Example/Tests/OrderValidatorTests.cs`:

```csharp
[TestClass]
public class OrderValidatorTests
{
    [TestMethod]
    public void Validate_RejectsNegativeQuantity()
    {
        var validator = new OrderValidator();
        var order = new Order { Quantity = -1 };

        var result = validator.Validate(order);

        Assert.IsFalse(result.IsValid);
    }

    [TestMethod]
    public void Validate_AcceptsValidQuantityAt1()
    {
        var validator = new OrderValidator();
        var order = new Order { Quantity = 1 };

        var result = validator.Validate(order);

        Assert.IsTrue(result.IsValid);
        Assert.AreEqual(string.Empty, result.Error);
    }

    [TestMethod]
    public void Validate_TimesOutAfter5Seconds()
    {
        var validator = new OrderValidator();
        var order = new Order { Quantity = 1 };

        Thread.Sleep(5000);
        var result = validator.Validate(order);

        Assert.IsTrue(result.IsValid);
    }
}
```

Production code under test exposes `Validate(Order) -> ValidationResult { IsValid, Error }`. A sibling test (`OrderValidator_FluentTests.cs`) asserts both `IsValid` and `Error` on every code path.

## Golden Audit Output

```
Schema: RunSummary v1 | Phase: Audit
Test Hardening -- Audit complete.
  Target:             OrderValidatorTests
  Test framework:     MSTest
  Files inspected:    1 test files, 2 production files
  Findings kept:      3   (high=1, medium=1, low=1)
  Findings discarded: 2   (failed Bug Gate)
  Production-blocked: 0   (requires-production-change=true)
  Findings overflow:  0   (kept out of top-15 report)
  Avg confidence:     8.3
  Stability evidence: not provided
```

### Findings

**F1 -- assertion-strength (high, confidence 9) -- failure-mode: validation**
`OrderValidatorTests.cs:14` -- `Validate_RejectsNegativeQuantity` asserts `result.IsValid` is false but does not assert `result.Error` is non-empty. A validator that returns `IsValid=false` with an empty `Error` would pass this test silently, leaking the failure reason. Sibling test `OrderValidator_FluentTests.cs:42` already asserts both fields together.

Evidence depth: `sibling-test`.

Reproduction trace:
1. `OrderValidatorTests.cs:13` -- `validator.Validate(order)` returns `new ValidationResult { IsValid = false, Error = "" }`.
2. `OrderValidatorTests.cs:14` -- assertion passes because only `IsValid` is checked.
3. Production defect at `OrderValidator.cs:31` (empty `Error` after `IsValid = false`) goes undetected.

Suggested edit (verbatim):
```csharp
Assert.IsFalse(result.IsValid);
Assert.IsFalse(string.IsNullOrEmpty(result.Error), $"Expected non-empty error, got: '{result.Error}'");
```

**F2 -- stability-by-design (medium, confidence 8) -- failure-mode: performance**
`OrderValidatorTests.cs:32` -- `Validate_TimesOutAfter5Seconds` uses `Thread.Sleep(5000)` as a synchronization primitive, then asserts `IsValid`. The sleep does not gate any state; the test runs for 5 seconds regardless. Project has `WaitForCondition(predicate, timeout)` at `src/Services/Example/Tests/TestHelpers.cs:18`.

Evidence depth: `production-one-level`.

Suggested edit (verbatim):
```csharp
var result = validator.Validate(order);
Assert.IsTrue(result.IsValid);
```

(The `Thread.Sleep(5000)` line is removed; the test as written never produced a timing condition to wait for.)

**F3 -- parameterization (low, confidence 7) -- failure-mode: logic**
`OrderValidatorTests.cs:7` and `OrderValidatorTests.cs:18` -- `Validate_RejectsNegativeQuantity` and `Validate_AcceptsValidQuantityAt1` differ only in the `Quantity` input and the expected `IsValid` output. They can collapse to one `[DataTestMethod]` with two `[DataRow]`s without losing coverage.

Evidence depth: `test-only`.

Suggested edit (verbatim):
```csharp
[DataTestMethod]
[DataRow(-1, false)]
[DataRow(1, true)]
public void Validate_ReturnsExpectedValidity(int quantity, bool expectedValid)
{
    var validator = new OrderValidator();
    var order = new Order { Quantity = quantity };

    var result = validator.Validate(order);

    Assert.AreEqual(expectedValid, result.IsValid);
}
```

### Hardening Recommendation Summary

| File | Category | Impact | Confidence | Failure Mode | Proposal |
|------|----------|--------|------------|--------------|----------|
| OrderValidatorTests.cs:14 | assertion-strength | high | 9 | validation | Add `Error`-non-empty assertion alongside `IsValid=false`. |
| OrderValidatorTests.cs:32 | stability-by-design | medium | 8 | performance | Remove unused `Thread.Sleep(5000)`. |
| OrderValidatorTests.cs:7 | parameterization | low | 7 | logic | Collapse two near-duplicate methods to `[DataTestMethod]`. |

## Discarded Findings (illustrative)

- *"Test names use snake_case; rename to PascalCase"* -- discarded: style-only, fails Bug Gate.
- *"Use `Assert.That` instead of `Assert.IsTrue`"* -- discarded: framework preference, no detection gap.

## What this fixture validates

- The Audit header conforms to `RunSummary v1`.
- High-impact findings include a reproduction trace.
- Every kept finding cites a failure mode from the lens.
- Confidence scores reflect the rubric (9 with snippet + sibling evidence; 8 with snippet + production evidence; 7 with snippet + test-only).
- Discarded findings carry a reason.
