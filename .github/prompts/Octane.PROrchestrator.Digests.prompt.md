---
description: Generate business logic and test coverage digests for changed files
agent: PROrchestrator
---

# Digests — Agent Prompt

Analyze the changed files on the current branch and produce structured digests.

## Instructions

1. **Get the changed file list.** If `changed_files_path` is provided and the file exists, read it — it contains a JSON array of file paths scoped to this PR. Use exactly that list as the changed files. Only fall back to `git diff --name-only origin/{{ workflow.input.target_branch | default('main') }}...HEAD` if the file is missing or unreadable.
2. Locate and read `skills/change-digest/SKILL.md` (search `**/skills/change-digest/SKILL.md` if needed).
3. Follow the skill's instructions. It produces two digests:
   - **Business Logic Digest** — endpoint inventory, service call flows, key business rules, entity/model schema changes
   - **Test Coverage Digest** — production-to-test file mapping, public method coverage matrix, gap summary
4. Produce BOTH digests. If a digest should be skipped (e.g., no controller files), document the skip reason.

## Expected Output

- **business_logic_digest**: Full business logic digest as structured markdown (or skip reason)
- **test_coverage_digest**: Full test coverage digest as structured markdown (or skip reason)
