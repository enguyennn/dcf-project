---
description: 'Structured template for the Phase 1 Pre-Validation Report. Fill in each section with evidence from workflow steps.'
---

## Pre-Validation Report

### Business Logic Digest
*(Omit if Step 1.5a was skipped)*
{endpoint inventory table}
{service call flow maps}
{key business rules}
{entity & model schema summary}

### Test Coverage Digest
*(Omit if Step 1.5b was skipped)*
{production ↔ test file mapping}
{public method coverage matrix}
{gap summary with critical gaps highlighted}

### Risk Classification
| Level | Signals | Review Requirement |
|-------|---------|-------------------|
| {🟢 Low / 🟡 Medium / 🔴 High} | {signals} | {requirement} |

### AI Code Review
| Severity | Count | Details |
|----------|-------|---------|
| Critical | {count} | {summary} |
| High | {count} | {summary} |
| Medium | {count} | {summary} |
| Low | {count} | {summary} |

{expanded findings grouped by file, then severity}

### Deterministic Gates
| Gate | Status | Details |
|------|--------|---------|
| Lint | ✅ Pass / 🔴 Fail | {summary} |
| Build | ✅ Pass / 🔴 Fail | {summary} |
| Tests | ✅ Pass / 🔴 Fail | {pass}/{total} passed |
| Security | ✅ Pass / 🔴 Fail | {summary} |

### AI Advisory Findings
| Check | Status | Findings | Severity |
|-------|--------|----------|----------|
| 🛡️ Security Patterns | {verdict} | {count} findings | {max_severity} |
| 🔄 Breaking Changes | {verdict} | {count} detected | {max_severity} |
| 📝 Docs Sync | {verdict} | {count} suggestions | {max_severity} |
| 🧪 Test Coverage | {verdict} | {count} suggestions | {max_severity} |

### Auto-Generated Tests
| File | Tests Created | Tests Passing | Coverage Delta |
|------|--------------|---------------|----------------|
| {source_file} | {test_file} | {pass}/{total} | +{delta}% |
*(Omit this section if Step 2 was skipped)*

### Details
{expanded details for each advisory finding, using the governance-toolkit output formats above}

## Verdict Classification

- `❌ Failed` — critical/error/vulnerability found
- `⚠️ Warning` — warning/potential issue found
- `ℹ️ Suggestion` — improvement recommendation
- `✅ Passed` — no issues found
