---
description: Validate triage findings against code and apply fixes for review feedback
agent: PROrchestrator
---

# Fix Feedback — Agent Prompt

Validate triaged review comments against actual code, apply fixes, commit, and push. This agent receives pre-triaged thread data from the `triage_feedback` script agent — it does NOT triage threads itself.

This is a loop-aware agent — it may be re-invoked across iterations until all actionable feedback is addressed or the iteration limit is reached.

## Inputs

### Triage Results (from triage_feedback script)

Use the triage output as-is. Do NOT re-triage, re-fetch threads, or reclassify verdicts.

{% if triage_feedback is defined and triage_feedback.output and triage_feedback.output.stdout %}
```json
{{ triage_feedback.output.stdout }}
```
{% else %}
> No triage output available. Exit with `all_addressed = true, comments_addressed = 0`.
{% endif %}

The triage JSON has this structure:
- `actionable[]` — threads requiring attention, each with `thread_id`, `verdict` (`must_fix` | `should_consider`), `file`, `line`, `body`, `author`
- `skipped[]` — threads filtered out, each with `thread_id` and `reason`
- `summary` — `{ total, actionable, skipped }`

### PR and Branch Info

- **PR URL**: {{ workflow.input.pr_url }}
- **Source branch**: Run `git branch --show-current` to determine
- **Max iterations**: {{ workflow.input.max_iterations | default(5) }}

### Previous Iteration State (Self-Loop)

{% if fix_feedback is defined and fix_feedback.output %}
This agent is being re-invoked. Resume from current state — do NOT re-process already-addressed comments.

- **Previous iteration**: {{ fix_feedback.output.iteration }}
- **Cumulative comments addressed**: {{ fix_feedback.output.comments_addressed }}
- **Comments remaining**: {{ fix_feedback.output.comments_remaining }}
- **Cumulative fix commits**: {{ fix_feedback.output.fix_commits | json }}
- **Cumulative addressed details**: {{ fix_feedback.output.addressed_details | json }}
- **CI status after last fixes**: {{ fix_feedback.output.ci_status }}

Increment the iteration counter. The `fix_commits`, `comments_addressed`, and `addressed_details` fields are cumulative — include all previous data plus new entries.
{% endif %}

## Safety Rails

- **Never force-push** — always `git push`, never `git push --force`
- **Never merge the PR** — only push fix commits
- **Stop on conflicts** — if `git push` fails after one rebase retry, stop and report
- **Respect iteration limits** — do not exceed `max_iterations`

## Workflow

### 1. Setup

Detect platform:
```powershell
$scriptPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\detect-platform.py"
python $scriptPath
```

Ensure you are on the source branch with latest code:
```bash
git checkout {source_branch}
git pull origin {source_branch}
```

{% if fix_feedback is defined and fix_feedback.output %}
Set `iteration = {{ fix_feedback.output.iteration }} + 1`.
{% else %}
Initialize `iteration = 1`.
{% endif %}

### 2. Parse Triage Input

Parse the triage JSON. Extract `actionable` and `skipped` arrays.

**Early exit** — if `actionable` is empty:
- Set output: `all_addressed = true`, `comments_addressed = {cumulative or 0}`, `comments_remaining = 0`
- Exit immediately.

{% if fix_feedback is defined and fix_feedback.output %}
Filter out threads whose `thread_id` already appears in previous `addressed_details`.
{% endif %}

### 3. Validate Findings Against Code

For each actionable thread:
1. **Read the referenced code** (±10 lines context)
2. **Validate the concern** — real bug or misread?
3. **Refine verdict**: Must fix → apply | Should consider → apply | Invalid → auto-resolve with explanation | Ambiguous → note for human

### 4. Apply Fixes

Process ALL actionable threads in one pass — do NOT commit after each individual fix.

For each approved fix:
1. Apply the minimal change
2. Verify the edit took effect
3. Track `thread_id`, `file`, `finding_summary`

After ALL fixes: reply to each addressed thread with `✅ Fixed in commit {sha}: {summary}`, then mark as Fixed/Resolved. For invalid comments, auto-resolve with explanation.

### 5. Commit and Push

One commit for ALL fixes in this iteration:
```bash
git add -A
git commit -m "fix(pr-orchestrator): address review feedback (iteration {iteration}/{max_iterations})

Fixes applied ({N} of {M} actionable threads):
- {summary of each fix}"
git push origin {source_branch}
```

If push fails: attempt one rebase, then push again. If rebase fails, stop and report.

## Expected Output

- **iteration**: Current iteration number (cumulative)
- **comments_addressed**: Cumulative total across ALL iterations
- **comments_remaining**: Actionable comments still unresolved
- **fix_commits**: Cumulative list of ALL fix commit SHAs
- **addressed_details**: Cumulative array with `thread_id`, `file`, `finding_summary`, `commit_sha` per comment
- **ci_status**: `passed`, `failed`, `running`, or `unknown`
- **all_addressed**: `true` if all actionable comments resolved
