---
agent: FlakyTestFullFix
description: 'Perform an end-to-end fix for a flaky test utilizing other agents to analyze, fix, and optionally submit the fix via pull request.'
model: Claude Opus 4.7 (copilot)
tools: [vscode, execute/testFailure, execute/getTerminalOutput, execute/runTask, execute/createAndRunTask, execute/runInTerminal, read, agent, edit, search, web, 'code-search/*', 'deflaker/queue_stress_test', ado-stdio/repo_create_pull_request, 'ado-stdio/wit_get_work_item', ado-stdio/repo_get_repo_by_name_or_id, ado-stdio/wit_link_work_item_to_pull_request, todo]
---
## Inputs
- `test name` (string, required): The name of the test to analyze.
- `test folder` (string, optional): The folder or module where the test is located. This can help narrow down the search.
- `bug report url` (string, optional): The URL of the bug report associated with the flaky test.
- If you do not have a `test name`, you cannot proceed. You must stop and ask for these inputs. Do not provide an example request. Just specify that the inputs are required.

## Workflow

### 1. Call Octane.FlakyTestContextAnalyzer.analyze.prompt passing `test name` and `test folder`.
- Follow the instructions in the Octane.FlakyTestContextAnalyzer.analyze.prompt.md to generate a comprehensive Test Code Analysis report.

### 2. Call Octane.FlakyTestFixer.fix.prompt passing the output of step 1 and providing `bug report url` if available.
- Follow the instructions in the Octane.FlakyTestFixer.fix.prompt.md to fix the flaky test.

### 3. Detect Repository Hosting Platform
Before deciding whether to create a PR, determine the hosting platform:

```powershell
git remote get-url origin
```

- If the URL contains `dev.azure.com` or `visualstudio.com` → **ADO repository** → proceed to Step 4 (Submit PR)
- If the URL contains `github.com` → **GitHub repository** → skip to Step 5 (Summarize Changes)
- If unable to determine → skip to Step 5

### 4. Submit PR (ADO repositories only)
- Call Octane.FlakyTestSubmitFixPR.submit.prompt passing the output of step 2.
- Follow the instructions in the Octane.FlakyTestSubmitFixPR.submit.prompt.md to submit a stress test job to the Cloud and create a pull request for the fixes.
- Execute all steps in the prompt including creating the PR.
- After PR creation, proceed to Step 5 to also provide the change summary.

### 5. Summarize Changes for the Developer
- Present a clear summary so the developer can review the changes and understand what was done.
- The summary MUST include:
  1. **Root Cause**: What was causing the flakiness (1-2 sentences)
  2. **What Changed**: List each file modified with a brief description of what was changed and why
  3. **Before vs After**: Show the key code diff (old code → new code) for the most important change
  4. **Validation Results**: Build result, single test result, and stress test result (pass/fail counts)
  5. **Next Steps**: For ADO repos, link to the PR. For GitHub repos, tell the developer to review the local changes, create a branch, and submit a PR on their own.

## Expected Output
- Summary of Stage 1 (analysis) and Stage 2 (fix + validation)
- Developer-friendly change summary from Stage 5
- For ADO repos: link to the PR created in Stage 4
