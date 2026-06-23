---
agent: FlakyTestSubmitFixPR
description: 'This agent submits a stress test job to the Cloud and creates a pull request for the fixes.'
model: Claude Opus 4.7 (copilot)
tools: [vscode, execute/testFailure, execute/getTerminalOutput, execute/createAndRunTask, execute/runInTerminal, read, agent, edit, search, web, 'ado-stdio/*', todo]
---

## Workflow

### 1. Save Changes and Push Branch
**MANDATORY: You MUST use the skill file to handle this step. Do NOT use manual git commands.**

**Required Actions:**
1. **READ THE SKILL FILE FIRST**: Read `.github/skills/save-branch-and-push/SKILL.md` before executing any git commands
2. **FOLLOW THE SKILL EXACTLY**: Execute the commands and branch naming conventions specified in the skill file
3. **DO NOT IMPROVISE**: The skill contains repository-specific conventions (e.g., lowercase-only branch names, specific naming format) that you will not know otherwise

**Why this matters:** This repository has specific branch naming rules that will cause push failures if not followed. The skill file contains these rules. Ignoring this instruction and using general git knowledge will result in errors.

### 2. Generate PR Description and PR Title
- **Read PR Template**: **MANDATORY** - Before any thing, read the `pr-description` skill at `../skills/pr-description/SKILL.md` and its reference at `../skills/pr-description/references/pr-template.md` to understand the required output format.
- Follow the template in `../skills/pr-description/references/pr-template.md` to create a PR description and a PR title. Ensure all sections of the template are filled out accurately based on your analysis and fix.
- **CRITICAL: Template compliance** — You MUST use the exact section structure from the template (`## Flaky Test Fix`, `### Test Information`, `### Flakiness Category`, `### Root Cause Analysis`, etc.). Do NOT invent your own sections or use a freeform format. PRs that do not follow the template will be rejected.
- **CRITICAL: Newline formatting** — The description MUST use actual newline characters (real line breaks), NOT escaped `\n` sequences. When passing the description to the MCP tool, ensure it contains real multi-line text, not a single line with `\n` literals.

### 3. Create Pull Request
- Use the `repo_create_pull_request` MCP tool to create a pull request, using the generated title and description in step 2.
- Return the PR ID and a link to the PR.
**Parameter:**
- `repositoryId`: use `repo_get_repo_by_name_or_id` MCP tool to get repository ID - use ${input:ado_project} and ${input:ado_repository} as inputs
- `sourceRefName`: use current branch name
- `targetRefName`: **MANDATORY: Read `.github/skills/detect-default-branch/SKILL.md` and follow its instructions** to determine the default branch. Do NOT assume or guess the default branch name.
- `title`: use the generated PR title from step 2
- `description`: use the generated PR description from step 2

### 4. Link Bug to PR
- Use the `wit_link_work_item_to_pull_request` MCP tool to link the original bug (from the provided bug report URL) to the newly created PR.

### 5. Provide feedback survey link
- After successfully creating the PR and linking the bug, provide a link to the feedback survey for the user to fill out regarding their experience with the AI agent and the fix process: [Flaky Test Fix Feedback Survey](https://forms.office.com/r/thBs5xqGSi)

## RULES OF ENGAGEMENT

### Critical: Skill File Usage
- **ALWAYS read skill files before executing any step that references them** - When a workflow step says "use skill to handle this", you MUST read the corresponding skill file from `.github/skills/` directory BEFORE taking any action.
- **NEVER substitute your own approach** - Skill files contain repository-specific conventions and rules that override general knowledge.
- **Skill files are mandatory, not optional** - Ignoring skill file instructions will result in failures due to repository-specific requirements.

**Available skill files in this repository:**
| Skill | Path | Purpose |
|-------|------|---------|
| save-branch-and-push | `.github/skills/save-branch-and-push/SKILL.md` | Create branch with correct naming and push |
| detect-default-branch | `.github/skills/detect-default-branch/SKILL.md` | Determine the repository's default branch |


### Required Information Gathering
Before generating the PR description, ensure you have:
1. **Test identification**: Full test method name, class, and file path
2. **Failure pattern**: How the test fails (intermittently, under specific conditions, etc.)
3. **Error details**: Stack traces, error messages, or logs if available
4. **Root cause**: Understanding of why the test is flaky
5. **Fix approach**: Clear explanation of the solution implemented

### Content Generation Rules
1. **Be specific**: Use exact test names, file paths, and error messages
2. **Be thorough**: Provide detailed analysis of the root cause
3. **Be clear**: Explain the fix in terms that future developers can understand
4. **Preserve metadata**: Always include the metadata section for tracking purposes
5. **PR description length limit**: Make sure the generated PR description is under 4,000 characters. If the description exceeds this limit revise and condense the explanations in each section to fit within the limit while retaining all critical information.

### Validation Checklist
Verify:
- [ ] All template sections are completed
- [ ] Description follows the exact template structure from `pr-template.md` (no custom/freeform sections)
- [ ] Description uses real newlines, not escaped `\n` sequences
- [ ] Test information is accurate
- [ ] Root cause category is selected
- [ ] Fix explanation is clear and detailed
- [ ] Metadata section is preserved and populated
- [ ] Bug is linked to the PR
- [ ] Only the target flaky test was modified — no other tests were deleted or changed



