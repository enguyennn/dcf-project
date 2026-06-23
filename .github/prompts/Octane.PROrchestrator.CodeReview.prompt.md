---
description: 'Code review — dispatch Gatekeeper review'
agent: PROrchestrator
---

# Code Review — Agent Prompt

## Step 1 — Always Attempt Gatekeeper First

### Tier 1 — Gatekeeper via `task` tool

```
task(
  agent_type: "octane-gatekeeper:Octane.Gatekeeper",
  name: "code-review",
  description: "Gatekeeper code review",
  prompt: "Review code changes on current branch against main.

IMPORTANT — Review ONLY the diff output. Do NOT read full files.

Steps:
1. If `changed_files_path` is provided and exists, read it for the PR-scoped file list.
2. Run: git diff main...HEAD — but only review files in the changed file list.
3. Review ONLY the changed lines (+ and - lines)
3. For each finding: severity, file, line, description, fix, mechanical vs human-judgment.

Do NOT open or read any files individually. Work exclusively from the diff output.",
  mode: "sync"
)
```

If the call succeeds, parse findings and set your output. Done.

### Tier 1b — Gatekeeper via shell (if `task` fails)

```powershell
$gkAgent = Get-ChildItem "$env:USERPROFILE\.copilot" -Recurse -Filter "Octane.Gatekeeper.agent.md" | Select-Object -First 1
if ($gkAgent) { Write-Output "Gatekeeper found at: $($gkAgent.FullName)" }
else { Write-Output "Gatekeeper not installed" }
```

If found, dispatch as a `general-purpose` task with the same diff-only review prompt. If this also fails, report that no review engine is available: set `code_review_findings` to `{"findings": {}, "review_engine": "Unavailable"}` and `done` to `true`.

ONE attempt per tier. Tier 1 → Tier 1b. Don't retry a tier. If both fail, output the unavailable marker.

## Classification: Mechanical vs Human-Judgment

**Mechanical** — unambiguous fix, no design decision:
- Applying a pattern already used elsewhere in the same file/PR
- Missing null checks, error handling with obvious correct behavior
- Consistency fixes (e.g., using `JsonSerializer.Serialize()` like adjacent values)
- Missing documentation entries for changes already made

**Human-judgment** — requires intent, downstream impact, or design tradeoffs:
- Breaking changes where downstream consumer behavior is unknown
- Architectural decisions (different data structures, API shapes)
- Performance tradeoffs with no clear winner

Default to mechanical. Only classify as human-judgment when you genuinely cannot determine the correct fix without business context.

## Expected Output

- **code_review_findings**: Findings by severity. Include `"tier": "1"` for Gatekeeper results, or emit the unavailable marker when no review engine is available.
- **review_engine**: `"Gatekeeper"` when Gatekeeper produces findings, or `"Unavailable"` when no review engine is available.
- **done**: `true`

Every finding must include: `id`, `file`, `line`, `description`, `recommended_fix`, `category` (mechanical or human-judgment), `mechanical` (bool).

For human-judgment findings, also include: `code_context` (what the code does), `why_not_auto_fixed` (why it needs a human), `decision_guide` (what to check to decide).