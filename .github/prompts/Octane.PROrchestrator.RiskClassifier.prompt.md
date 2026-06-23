---
description: Classify PR risk level based on file sensitivity and blast radius
agent: PROrchestrator
---

# Risk Classifier — Agent Prompt

Classify the risk level of the current code changes to determine review requirements.

## Instructions

### 1. Run the Deterministic Risk Script

Pipe `git diff` output to the classifier — this works whether or not `changed_files_path` was provided by the bootstrap and avoids template variable failures.

```powershell
$scriptPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\classify-risk.py"
git --no-pager diff --name-only main...HEAD | python $scriptPath
```

The script output is the FINAL risk level. Do NOT override it.

### 2. Report the Script Output

Return the script's `risk_level`, `signals`, and `expertise_needed` as your output. No modifications.

If the script is not found, fall back to the `risk-classification` skill (`**/skills/risk-classification/SKILL.md`).

## Expected Output

- **risk_level**: `low`, `medium`, or `high`
- **risk_signals**: List of risk signals that determined the level
- **expertise_needed**: Type of expertise needed for review (e.g., "Security", "Database"), or empty if Low risk
