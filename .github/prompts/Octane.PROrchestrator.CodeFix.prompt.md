---
description: 'Auto-fix mechanical findings from code review — apply fixes, commit, verify build'
agent: PROrchestrator
---

# Code Fix — Agent Prompt

Auto-fix mechanical findings from the code review.

## Context

The `code_review` agent produced findings organized by severity (critical, important, suggestion). Each finding is classified as **mechanical** (unambiguous code fix) or **human-judgment** (needs design decision).

Your job: fix all **mechanical** findings at any severity. Leave **human-judgment** findings for the reviewer.

## Input Findings

The code review findings are provided below as JSON. Do NOT re-run code review. If the findings below are empty, missing, or say "No output", set `done: true` with `fixes_applied: 0` and exit.

```json
{{ load_findings.output.stdout }}
```

## Continuation

If continuing from a prior pass, check which findings have already been fixed (listed in `fix_commits`) and only fix remaining ones. Set `done: true` when all mechanical findings are addressed.

## Instructions

For each mechanical finding (Critical first, then Important, then Suggestion):

1. **Read the affected file** at the referenced line numbers
2. **Apply the minimal fix** that addresses the finding
3. **Verify** the fix doesn't break anything — run the build if needed

**Time & Iteration Budget:**
- You have approximately 90 minutes total. Budget your time accordingly.
- Run only **targeted tests** (for the files you changed) after each fix, not the full test suite.
- Run the full test suite **at most once**, at the end before committing — and only if sufficient time remains.
- If a specific finding's fix causes test failures after **2 attempts**, skip it — mark it as remaining for human review.
- If you are running low on time, **commit what you have** and report remaining findings. Partial progress is better than a timeout with nothing committed.
- The `max_fix_iterations` input is {{ workflow.input.max_fix_iterations }} — do not exceed this many fix-test cycles.

**Progress Reporting:**
- Set `made_progress: true` if you fixed at least one new finding this pass.
- Set `made_progress: false` if you attempted fixes but none succeeded (stall condition — the workflow will exit).

**After all fixes:**

- The allowlist of files you may modify is **the `file` field of every finding** in the input.
- Before committing, run `git status --porcelain` and confirm every modified file is in that allowlist. If not, abort and report the violation.
- Stage only the specific finding files. Never use `git add -A`, `git add .`, or a project-wide formatter/fixer.

```bash
git add -- <file1> <file2> ...
git commit -m "fix: address code review findings (auto-fix)

{list of findings fixed, one per line}"
```

Do NOT fix findings marked as **human-judgment**, changes to public API contracts, or anything requiring business context.

## Expected Output

- **fixes_applied**: Cumulative number of findings auto-fixed (0 if none)
- **fix_commits**: Cumulative list of commit SHAs for auto-fix commits (empty array if none)
- **findings_remaining**: Findings left for human review (human-judgment + suggestions)
- **done**: `true` when all mechanical fixes are applied