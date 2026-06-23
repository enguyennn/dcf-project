# Coverage-Only Test Analysis

**Identify tests that exist solely for coverage metrics without validating meaningful behavior.**

## Overview

This scenario helps you find and assess "coverage-only" tests—unit tests that inflate coverage numbers but don't catch real bugs or validate expected behavior. These tests often:

- Lack meaningful assertions
- Use trivial assertions like `Assert.True(true)`
- Over-mock dependencies to the point of not testing anything real
- Simply exercise code paths without verifying outcomes

## Why This Matters

Coverage-only tests create technical debt:
- **False confidence**: High coverage numbers mask untested behavior
- **Maintenance burden**: Tests require upkeep but provide no value
- **Slow builds**: More tests = longer CI times with no quality benefit
- **Cognitive load**: Developers must understand useless tests during debugging

## Getting Started

### Prerequisites

- Access to Engineering Copilot (`code-search` MCP server)
- Repository context configured in Octane

### Available Prompts

| Prompt | Purpose |
|--------|---------|
| `/Octane.CoverageAnalyzer.Analyze` | Analyze a single test file or specific test |
| `/Octane.CoverageAnalyzer.Batch` | Analyze an entire directory or test suite |
| `/Octane.CoverageAnalyzer.Report` | Generate shareable markdown report |

## Sample Workflow

### 1. Understand Repository Context

```
Using Engineering Copilot, let me know what this repo is about
```

### 2. Locate Specific Test

```
Help me find ChannelTests, more specifically, TestConnectionStatusReporter
```

### 3. Analyze Test Value

```
/Octane.CoverageAnalyzer.Analyze TestConnectionStatusReporter
```

### 4. Generate Shareable Report

```
/Octane.CoverageAnalyzer.Report
```

## Value Scoring Scale

Tests are rated 1-5:

| Score | Rating | Action |
|-------|--------|--------|
| 1 | Delete Immediately | Test provides zero value, remove it |
| 2 | Needs Rewrite | Core concept valid but implementation useless |
| 3 | Marginal Value | Provides some coverage but weak assertions |
| 4 | Acceptable | Reasonable test with room for improvement |
| 5 | High Value | Well-designed test that catches real bugs |

## Detection Heuristics

The analyzer looks for these common coverage-only patterns:

### No Assertions
```csharp
[Test]
public void TestMethod()
{
    var obj = new MyClass();
    obj.DoSomething();  // No verification!
}
```

### Trivial Assertions
```csharp
[Test]
public void TestAlwaysPasses()
{
    Assert.True(true);
    Assert.NotNull(new object());
}
```

### Over-Mocking
```csharp
[Test]
public void TestWithAllMocks()
{
    var mockA = new Mock<IA>();
    var mockB = new Mock<IB>();
    mockA.Setup(x => x.GetB()).Returns(mockB.Object);
    // Only testing mock behavior, not real code
}
```

### Self-Referential Checks
```csharp
[Test]
public void TestInputEqualsOutput()
{
    var input = "test";
    var result = PassThrough(input);
    Assert.Equal(input, result);  // Trivial if PassThrough just returns input
}
```

### Exception Swallowing
```csharp
[Test]
public void TestDoesNotThrow()
{
    try { riskyOperation(); }
    catch { }  // Swallows everything, test always passes
}
```

## Custom Agent

This scenario includes the **CoverageAnalyzer** agent, a Senior QA Engineer persona specializing in:

- Test smell detection
- Assertion quality analysis
- Test value assessment
- Honest, constructive criticism

## MCP Servers Used

- **code-search** (Engineering Copilot): Deep code understanding, test discovery, and repository context

## Related Scenarios

- [Test Analysis](../test-analysis/README.md) - General test quality assessment
- [Flaky Test Fix](../flaky-test-fix/README.md) - Identify and fix flaky tests
