---
name: build-outcome-classification
description: Classify a local build/test run into exactly one of three buckets so the Improve phase knows whether to revert edits, retry, or hand off to cloud validation.
---

# Build Outcome Classification

Every local build/test run in the Improve phase must end in exactly one of three buckets. A failed local build does NOT mean the edits are wrong — diagnose first, react second.

## The Three Buckets

| Bucket | Definition | Action |
|--------|------------|--------|
| `LOCAL_BUILD_OK` | Build completed; every originally-passing test still passes. | Continue to stress validation. |
| `LOCAL_BUILD_FAILED_BY_EDIT` | Compile error or test failure references an edited file (compile error in modified file, or assertion failure in a method whose body was changed). | Revert offending edit, re-build, re-classify. Iteration cap: **3 attempts total**. |
| `LOCAL_BUILD_BLOCKED` | Build failed but failure is independent of the edits (see indicators below). | Make ONE recovery attempt; if it fails, keep edits, set `Cloud validation: required`, continue. |

## `LOCAL_BUILD_BLOCKED` Indicators (non-exhaustive)

- `Could not find MSBuild.exe on the PATH` — environment not initialized in current shell.
- `Failed to move directory ... QLocal\cmd for deletion` / file-lock errors — stale daemon or VS handle.
- `No ready builder for action execution` — local QuickBuild builder pool unavailable.
- `CloudBuild.json was invalid` / `CloudBuild environment is set to 'NONE'` — local mode misconfiguration.
- Compile errors in files **not** modified by this run.
- Network / package-restore failures (`error NU1100`, timeouts).
- Build never started (timed out before producing target output).

## `LOCAL_BUILD_FAILED_BY_EDIT` — Revert Loop Rules

1. Revert ONLY the specific finding(s) implicated by the failing file path; keep clean edits.
2. Re-build and re-classify.
3. **Skip set is monotonic** — a finding reverted in attempt N must NOT be re-applied in attempt N+1.
4. Hard cap: **3 attempts**. Exit conditions:
   - **Success exit**: `LOCAL_BUILD_OK` reached — proceed to stress validation.
   - **Drafts-preserved abort exit**: 3 attempts reached without success — STOP iterating. Preserve current working-tree state as developer draft:
     - Mark each unbuilt file `drafted-build-broken`.
     - Set `Hardening status: aborted`, `Working tree: drafted-edits-present`, `Cloud validation: not-required`.
     - Emit developer-action: *"Drafted edits are in your working tree but the build is broken. Inspect `git diff`, fix the remaining build error, run the build/tests yourself, then submit a PR manually. To discard, run `git checkout -- <file>`."*
     - Do NOT hand off to Submit.
   - **Blocked exit**: failure no longer references edited files — reclassify as `LOCAL_BUILD_BLOCKED` and continue.

## Decision Rule When Uncertain

Compare error file paths against the `git diff --stat` output from the edit step:
- ANY error references an edited file → `LOCAL_BUILD_FAILED_BY_EDIT`.
- NO error references an edited file → `LOCAL_BUILD_BLOCKED`.

Never silently treat `_BLOCKED` as `_OK`. The RunSummary must state which it was.
