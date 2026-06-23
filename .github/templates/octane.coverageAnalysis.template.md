# Coverage-Only Test Analysis Report

**Generated**: [Date]  
**Repository**: [Repository name]  
**Scope**: [Files/directories analyzed]  
**Analyzer**: Coverage-Only Test Analysis (Octane)

---

## Prompt Summary

> [Original request that initiated this analysis]

This report identifies tests that exist solely for coverage metrics without providing meaningful validation of code behavior. The goal is to improve test suite quality by eliminating or improving low-value tests.

---

## Executive Summary

[2-3 sentence summary of key findings, worst offenders, and overall health of the test suite]

### Key Metrics

| Metric | Value |
|--------|-------|
| Total Tests Analyzed | X |
| Coverage-Only Tests Found | X (Y%) |
| Recommended for Deletion | X |
| Recommended for Rewrite | X |
| Estimated CI Time Recoverable | X minutes |

### Score Distribution

| Score | Rating | Count | % |
|-------|--------|-------|---|
| 1 | Delete Immediately | X | Y% |
| 2 | Needs Rewrite | X | Y% |
| 3 | Marginal Value | X | Y% |
| 4 | Acceptable | X | Y% |
| 5 | High Value | X | Y% |

---

## Analysis Results

### Summary Table

| # | Test | File | Issue Type | Score | Action |
|---|------|------|------------|-------|--------|
| 1 | [TestName] | [path/to/file.cs] | [No Assertions] | 1/5 | Delete |
| 2 | [TestName] | [path/to/file.cs] | [Trivial Assert] | 1/5 | Delete |
| 3 | [TestName] | [path/to/file.cs] | [Over-Mocking] | 2/5 | Rewrite |
| ... | ... | ... | ... | ... | ... |

---

## Detailed Findings

### 🚩 Score 1: Delete Immediately

#### [Test Name]

**File**: `path/to/test/file`  
**Method**: `TestMethodName`  
**Score**: 1/5 — Delete Immediately

**What This Test Does**:
[Brief description of the test's apparent purpose]

**Issues Found**:

```[language]
// Problematic code
[Code snippet showing the issue]
```

**Why This Is a Problem**:
[Explanation of why this test provides zero value]

**Recommendation**: Delete this test. It provides no validation and only inflates coverage metrics.

---

#### [Next Test Name]
[Repeat structure for each Score 1 test]

---

### ⚠️ Score 2: Needs Rewrite

#### [Test Name]

**File**: `path/to/test/file`  
**Method**: `TestMethodName`  
**Score**: 2/5 — Needs Rewrite

**What This Test Does**:
[Brief description]

**Issues Found**:

```[language]
// Problematic code
[Code snippet]
```

**Why This Is a Problem**:
[Explanation]

**How To Improve**:
```[language]
// Suggested improvement
[Improved code snippet or pseudocode]
```

**Recommendation**: Rewrite with meaningful assertions that verify actual behavior.

---

### 📝 Score 3: Marginal Value

#### [Test Name]

**File**: `path/to/test/file`  
**Method**: `TestMethodName`  
**Score**: 3/5 — Marginal Value

**What This Test Does**:
[Brief description]

**Issues Found**:
[List of minor issues]

**How To Improve**:
[Specific improvements that would raise this to Score 4-5]

**Recommendation**: Consider adding edge cases and strengthening assertions.

---

## Recommendations

### 🔴 Immediate Actions (This Sprint)

1. **Delete these tests** (zero value):
   - `TestName1` in `file1.cs`
   - `TestName2` in `file2.cs`
   
2. **Create backlog items** for rewriting Score 2 tests

### 🟡 Short-Term Actions (Next 2 Sprints)

1. **Rewrite** tests with Score 2:
   - [List with brief description of what needs to change]
   
2. **Improve** tests with Score 3:
   - [List with specific improvements]

### 🟢 Long-Term Actions (Process Improvements)

1. **Add test quality checklist** to PR review process:
   - [ ] Test has meaningful assertions
   - [ ] Test verifies behavior, not just coverage
   - [ ] Test name describes expected behavior
   
2. **Consider tooling**:
   - Add linting rules for minimum assertion count
   - Add mutation testing to validate test effectiveness
   
3. **Schedule regular audits**:
   - Quarterly coverage-only test analysis
   - Review tests older than 2 years

---

## Scoring Legend

| Score | Rating | Description | Action |
|-------|--------|-------------|--------|
| 1 | Delete Immediately | Zero value, pure coverage inflation | Remove from codebase |
| 2 | Needs Rewrite | Valid concept but useless implementation | Complete rewrite required |
| 3 | Marginal Value | Some coverage value but weak assertions | Add assertions/edge cases |
| 4 | Acceptable | Reasonable test with improvement room | Optional improvements |
| 5 | High Value | Well-designed test that catches real bugs | Keep as-is |

---

## Appendix: Tests Not Analyzed

[Optional: List of tests that were skipped and why (e.g., already high-value, integration tests excluded, etc.)]

---

*Report generated using [Octane Coverage-Only Test Analysis](https://github.com/azure-core/octane)*
