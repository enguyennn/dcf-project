---
agent: TestHardening
description: Apply minimal, surgical hardening edits to test code based on a Test Hardening Audit report. Test files only — production code is never modified.
model: Claude Opus 4.6 (copilot)
tools: [vscode, read, edit, search, execute/runInTerminal, execute/getTerminalOutput, agent, 'deflaker/*', todo]
---

# Test Hardening — Apply Edits

## Goal

Apply the findings from a previously generated **Test Hardening Audit** report to the target test files, with minimal diff and zero production-code changes. Every existing assertion must be preserved or replaced with a strictly stronger equivalent. Every existing test method must remain present and pass after the edits.

## Inputs

- A previously generated **Test Hardening Audit** report from the Audit prompt.
- (Optional) `category filter` — if provided, only apply findings whose category matches (e.g., `assertion-strength,stability-by-design`).

If you do not have a Test Hardening Audit report, you cannot proceed. Stop and request it.

## WORKFLOW STEPS

### Todo List Template

Create your todo list from the template below. Do not add, rename, or reorder items.

```
Todo 1:  Create todo list strictly from this template.
Todo 1b: Pre-flight `git status --porcelain` -- if non-empty, stop and request stash/commit.
Todo 2:  Parse audit report into worklist; drop `requires-production-change`, confidence < 7, and any outside `category filter`.
Todo 3:  Sanity-check every worklist entry is a test file (no production paths). Abort on violation.
Todo 4:  Apply each finding per the Per-Finding Application Protocol below.
Todo 5:  `git diff --stat` -- every changed path must be a test file. Revert any production file.
Todo 6:  Verify test count is unchanged and every original assertion is preserved or strictly strengthened.
Todo 7:  Build per `build-and-test`; classify per `build-outcome-classification`.
Todo 8:  If `stability-by-design` edits exist, run `stress-validation-protocol`.
Todo 9:  Emit RunSummary v1 + per-finding diffs + skipped-findings list per the Completion Protocol below.
```

## Per-Finding Application Protocol

For each finding in the worklist:

1. Apply the audit's ready-to-apply suggested edit verbatim when present. Deviate only when the snippet would not compile in-context (e.g., a referenced symbol is shadowed). Record the deviation reason.
2. Do not batch unrelated changes into a single edit.
3. Run three checks after each edit:
   - **Parse check**: re-read the file; the surrounding code must still parse.
   - **Gap-close check**: verify the edit closes the detection gap stated in the Audit finding's Bug Gate answer. Cross-check against the reproduction trace when present. If the edit does not address the specific incorrect behavior, revert and skip with reason `edit-does-not-close-gap`.
   - **Assertion-preservation check**: the edit must not remove or weaken any existing assertion. The replacement must verify at least the same property with equal or greater specificity.
4. Proportionality check: if the diff for a single finding exceeds 20 changed lines, pause. A 20+ line edit usually means the approach is wrong. Prefer a simpler approach or skip with reason `non-minimal-diff`.

## Stress Validation Protocol

When Todo 8 is triggered, follow `../skills/stress-validation-protocol/SKILL.md`. It defines the pass-rate target, the partial-revert rules, and the RunSummary fields to set on stress failure.

## Completion Protocol (Todo 9)

The Todo 9 output must satisfy:

1. **RunSummary v1 block first**, then per-file before/after diffs for each applied finding, then the skipped-findings list with reasons.
2. **Completeness invariant**: `applied + skipped = total audit findings`. If any finding is missing from both lists, stop and reconcile. Silent drops are not acceptable.
3. **All-blocked-by-production detection**: if `applied=0` and every skip reason is `requires-production-change`, set `Hardening status: blocked-by-production-dependencies`, `Next action: production-refactor-required`, and emit a developer-action paragraph listing each production seam needed. End2End does not call Submit in this case.
4. **Cloud Validation Required**: set `Cloud validation: required` whenever the build outcome is `LOCAL_BUILD_BLOCKED`, stress validation was deferred, or stress validation failed.

## Build Outcome Classification

Todo 7 must classify the build result into exactly one of three buckets per `../skills/build-outcome-classification/SKILL.md`. That skill defines the three buckets, the `LOCAL_BUILD_BLOCKED` indicators, the 3-attempt revert loop, the monotonic skip-set rule, and the decision rule when uncertain. A failed local build does NOT necessarily mean the edits are wrong — classify first, react second.

## Hardening Recipe

Apply edits per the recipes in `../skills/hardening-recipes/SKILL.md` (improve view). The skill is the source of truth for how each category translates to an actual edit. Highlights you must respect when applying:

- **Search before applying**: confirm every helper, abstraction, or API exists in the project by searching the codebase. If a helper is missing, mark the finding `requires-helper` and skip. Do not invent helpers.
- **No new sleeps**: replacing one sleep with another is not stability-by-design.
- **Preserve every assertion**: replacements must be strictly stronger -- verify at least the same property with equal or greater specificity.
- **Mock saturation deferral**: if reducing mock setup would require production seams, mark `requires-production-change: true` and skip.

## Rules of Engagement

Universal invariants live in `../skills/hardening-guardrails/SKILL.md` (always loaded). Improve-specific enforcement:

- **Search before applying.** Verify every helper / API exists in the project before referencing it. Missing helper -> mark `requires-helper` and skip; never invent.
- **External dependency boundary.** Nondeterminism caused by infrastructure (network, missing DLL, package restore, builder pool) -> classify `LOCAL_BUILD_BLOCKED` or skip with reason `external-dependency`. Do not change test behavior to work around it.
- **No PR creation here.** This prompt outputs edits and validation only; the Submit prompt creates the PR.
- **Stop if uncertain.** A wrong edit weakens the test -- skip and report instead.

### Phase-Unique Skill Files

Universal skills (`hardening-guardrails`, `run-summary`) are loaded automatically per the agent file. Improve-unique references:

| Skill | Path | Purpose |
|-------|------|---------|
| hardening-recipes | `../skills/hardening-recipes/SKILL.md` | Category definitions and apply recipes. |
| build-and-test | `../skills/build-and-test/SKILL.md` | Build the test project and run tests. |
| build-outcome-classification | `../skills/build-outcome-classification/SKILL.md` | Classify the build result into OK / FAILED_BY_EDIT / BLOCKED. |
| stress-test | `../skills/stress-test/SKILL.md` | Stress-test runner mechanics. |
| stress-validation-protocol | `../skills/stress-validation-protocol/SKILL.md` | When to stress, pass-rate target, partial-revert rules. |

## Output Format

Follow `../skills/run-summary/SKILL.md` for the Improve-phase emission template (`Schema: RunSummary v1 | Phase: Improve`). Emit the header block verbatim, then the per-finding diffs and the skipped-findings list. Use `n/a` for fields that do not apply. The Submit prompt and the End2End orchestrator parse this block.

### Improve-phase field rules

- `Working tree: drafted-edits-present` is set only when the iteration cap was hit with `LOCAL_BUILD_FAILED_BY_EDIT`. In that case `Hardening status: aborted` and `Next action: developer-finish-manually` are mandatory.
- `Working tree: clean` is the normal outcome for `LOCAL_BUILD_OK` and for `LOCAL_BUILD_BLOCKED`.
- `Stress validation: stress-failed` requires `Cloud validation: required`. Submit creates the PR as Draft and the description includes a `### Cloud Validation Required` section listing the stress-failing test method.
- `Hardening status: blocked-by-production-dependencies` requires `applied=0`, every skip reason `requires-production-change`, and `Next action: production-refactor-required`. End2End does not call Submit in this case.
- `Next action: developer-finish-manually` triggers a developer-action paragraph: *"Drafted edits are in your working tree but the build is broken. Inspect the diff (`git diff`), fix the remaining build error, then submit a PR manually. To discard, run `git checkout -- <file>`."*
- `Next action: production-refactor-required` triggers a developer-action paragraph: *"No test-only hardening was possible -- every audit finding requires a production-code change first. Production seams needed: <list>. Once the seams exist, re-run @Octane.TestHardening.End2End to harden the test."*
