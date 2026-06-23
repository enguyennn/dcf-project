---
name: change-digest
description: |
  Produce Business Logic Digest and Test Coverage Digest for changed files.
  Analyzes endpoints, service call flows, business rules, and test coverage mapping.
  Use when: pre-validating changes to understand what changed and what's tested.
---

# Change Digest

> Analyze changed files to produce structured digests of business logic and test coverage.

> **Attribution**: Adapted from [pr-lifecycle pr-review](https://github.com/agency-microsoft/playground/tree/main/plugins/pr-lifecycle) Steps 1.5 and 1.6.

## Execution Rules

- You MUST produce **both** digests (or document why one was skipped)
- Launch both analyses in parallel — they are independent
- Failures in either digest do not prevent the rest of the pipeline

## Inputs

- Changed file list — use the pre-computed list from `changed_files_path` if provided (JSON array of file paths scoped to the PR). Only fall back to `git diff --name-only` if no pre-computed list is available.
- Project context (language, framework)

## Step 1 — Business Logic Digest

**Skip if**: No controller, service, or API files are in the changed set (docs-only, test-only, config-only PRs). Document the skip reason.

Analyze all changed production files and produce:

1. **Endpoint Inventory** — Table of every controller action added or modified:

   | Method | Route | Auth | Feature Flag | Description |
   |--------|-------|------|--------------|-------------|

2. **Service Call Flow Maps** — For each endpoint, trace the request through the stack:
   ```
   POST /api/Resource
     → Controller.Create()
       → service.CreateAsync(request, ct)
         → dbContext.Resources.AddAsync(entity)
     ← 201 Created
   ```
   Annotate each step with what it does and what happens on failure.

3. **Key Business Rules** — Concrete rules the code enforces, with file:method citations.

4. **Entity & Model Schema** — New/modified data shapes with validation rules and key field descriptions.

## Step 2 — Test Coverage Digest

**Skip if**: No production code files (only tests, docs, or config) are in the changed set. Document the skip reason.

Analyze changed test files and their production counterparts:

1. **Production ↔ Test File Mapping**:

   | Production File | Test File(s) | Status |
   |----------------|--------------|--------|
   | `Services/FooService.cs` | `Tests/FooServiceTests.cs` | ✅ Has tests |
   | `Controllers/BarController.cs` | — | ❌ Missing tests |

   Status: ✅ Has tests / ❌ Missing tests / ⚪ Model only (may not need tests)

2. **Public Method Coverage Matrix** — For each changed production class:

   | Class | Method | Unit Test? | Scenarios Covered |
   |-------|--------|-----------|-------------------|

3. **Gap Summary** — Concise coverage health:
   - Production files with tests: X/Y (N%)
   - Public methods with unit tests: X/Y (N%)
   - Critical gaps: list of untested methods/endpoints

## Output

Both digests as structured markdown. These feed into:
- **Test Generation** — coverage digest prioritizes which files need tests
- **Code Review** — both digests provide context for reviewers
- **Risk Classification** — business logic digest provides blast radius info
- **PR Description** — digest summaries included in collapsible sections
- **Review Digest** — digest analysis referenced in posted comment
