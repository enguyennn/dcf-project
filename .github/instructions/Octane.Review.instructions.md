---
description: 'Principles for reviewing documentation — accuracy verification, hallucination detection, per-page tracking.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# Review Phase Principles

Guidelines for auditing documentation against source code for factual accuracy.

## Core Approach

Review is about **correctness**, not style. Verify every claim against the code. Fix errors. Leave accurate content alone.

## Per-Page Tracking

Track status across review passes using a structured approach:

| Status | Meaning | Next Action |
|--------|---------|-------------|
| `unreviewed` | Never been reviewed | **Must review** |
| `needs_fixes` | Has remaining issues | **Must review** |
| `verified` | All claims confirmed accurate | **Skip** |
| `flagged` | Requires human judgment | **Skip** |

On each pass, only review pages that still need work. If all pages are verified or flagged, the review is complete.

## What to Verify

- Named classes, methods, interfaces actually exist in code
- Behavioral descriptions match what the code does
- No invented features or capabilities
- File/directory path references point to real locations
- Relative links resolve to real files
- Code examples use only verified APIs

## What NOT to Change

- Accurate behavioral descriptions — don't "fix" by adding method signatures
- Level of detail — verify correctness, not completeness
- Style — don't rewrite accurate sections for preferences

## Summary

Write a summary after reviewing:
```markdown
## Review Summary
| Page | Status | Issues Found | Fixed | Remaining |
|------|--------|-------------|-------|-----------|
```

## Convergence

Review is designed for multi-pass convergence. Each pass should reduce the number of pages with issues. If issues_open is not decreasing between passes, flag the page for human review.
