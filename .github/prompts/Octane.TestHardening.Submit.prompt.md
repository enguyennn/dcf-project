---
agent: TestHardening
description: Push the hardening branch and open a pull request (ADO via MCP, GitHub via `gh` CLI) for the changes produced by the Improve prompt.
model: Claude Opus 4.6 (copilot)
tools: [vscode, read, execute/runInTerminal, execute/getTerminalOutput, agent, ado-stdio/repo_create_pull_request, ado-stdio/repo_get_repo_by_name_or_id, ado-stdio/wit_link_work_item_to_pull_request, todo]
---

## Workflow

### 0. Detect Repository Platform

Run `git remote get-url origin` and classify:

| Remote URL contains | Platform | PR mechanism |
|---------------------|----------|--------------|
| `dev.azure.com` or `visualstudio.com` | `ADO` | `ado-stdio/repo_create_pull_request` MCP tool |
| `github.com` | `GitHub` | `gh pr create` CLI |
| anything else / unable to determine | `unknown` | stop and emit Submit skipped (Step 7 template) |

Record the platform; Steps 1-3 are platform-agnostic, Step 4 branches on it.

### 1. Save Changes and Push Branch

Follow `../../../shared/skills/save-branch-and-push/SKILL.md` with `$phaseTag = "harden"`. Pre-push: `git diff --stat` must show test files only -- production file in the diff means stop and report. Do not improvise git commands.

### 2. Generate PR Title and Description

Read `../skills/pr-description/SKILL.md` and `../skills/pr-description/references/pr-template.md`. Adapt for hardening with these required sections (others stay verbatim from the template):

- `## Test Hardening`
- `### Hardening Categories Applied` -- every category from the audit that produced an edit.
- `### Audit Findings Applied` -- one bullet per finding: `[impact/confidence/failure-mode] file:line range -- category -- before/after summary`.
- `### Production Code Changed` -- value `None -- hardening scope is test code only.` (always present).
- `### Cloud Validation Required` -- include **only** when the Improve summary reported `Cloud validation: required`. List what could not run locally (compile, per-method pass, stress for stability-by-design edits, stress-failing method when applicable). In this case the PR must be created as **Draft**.

Use real newlines, never escaped `\n`. The same title and description body are used for both ADO and GitHub.

### 3. Detect Default Branch

Follow `../../../shared/skills/detect-default-branch/SKILL.md`.

### 4. Create Pull Request

Dispatch on `platform` recorded in Step 0.

#### 4a. ADO

Use the `repo_create_pull_request` MCP tool. Resolve `repositoryId` via `repo_get_repo_by_name_or_id` with `${input:ado_project}` and `${input:ado_repository}`. `sourceRefName` = branch from Step 1; `targetRefName` = branch from Step 3; `title` and `description` from Step 2; `isDraft = true` when the Improve summary reported `Cloud validation: required` OR `Stress validation: stress-failed`.

**Recovery on failure** (any reason: network, auth, existing PR for the same source ref, payload validation): do NOT retry. The branch is already pushed. Emit the recovery block below, then emit the prepared PR title and description in fenced code blocks for manual paste. Skip Steps 5 and 6.

```
PR creation failed.
  Platform:           ADO
  Branch (pushed):    [source branch name]
  Target branch:      [default branch name]
  Failure reason:     [exact error from MCP response]
  Manual create URL:  https://msazure.visualstudio.com/${input:ado_project}/_git/${input:ado_repository}/pullrequestcreate?sourceRef=[source]&targetRef=[target]
  Next action:        developer-create-pr-from-pushed-branch
```

#### 4b. GitHub

Pre-flight: confirm `gh` is installed and authenticated.

```pwsh
gh --version       # must succeed
gh auth status     # must report "Logged in to github.com"
```

If either check fails, do NOT retry. The branch is already pushed. Emit the recovery block below and skip Steps 5 and 6.

```
PR creation failed.
  Platform:           GitHub
  Branch (pushed):    [source branch name]
  Target branch:      [default branch name]
  Failure reason:     gh-cli-unavailable (`gh` not installed or not authenticated; run `gh auth login`)
  Manual create URL:  https://github.com/[owner]/[repo]/compare/[target]...[source]
  Next action:        developer-create-pr-from-pushed-branch
```

Otherwise create the PR. Write the body from Step 2 to a temp file (preserves real newlines through the CLI), then invoke `gh pr create`:

```pwsh
$body = @"
<full PR description body from Step 2>
"@
Set-Content -Path .\pr-body.tmp.md -Value $body -Encoding utf8

# Add --draft when Improve summary reported Cloud validation: required OR Stress validation: stress-failed
gh pr create `
  --title "<title from Step 2>" `
  --body-file .\pr-body.tmp.md `
  --base <default branch from Step 3> `
  --head <source branch from Step 1> `
  [--draft]

Remove-Item .\pr-body.tmp.md
```

`gh pr create` prints the PR URL to stdout on success (form: `https://github.com/<owner>/<repo>/pull/<NNN>`). Parse `<NNN>` as the PR number.

**Recovery on `gh pr create` failure** (auth expired mid-call, push race, existing PR for the same head, payload validation): do NOT retry. Emit the GitHub recovery block above, substituting the exact `gh` stderr into `Failure reason`. Skip Steps 5 and 6.

### 5. Link Bug to PR (optional, ADO only)

If a bug URL was passed in **and** platform is ADO, call `wit_link_work_item_to_pull_request`. GitHub or no bug URL → skip.

### 6. Provide Feedback Survey Link

On successful PR creation (ADO or GitHub) only: [Test Hardening Feedback Survey](https://forms.office.com/r/thBs5xqGSi).

### 7. Submit Skipped (unknown-platform)

If Step 0 classified the platform as `unknown`, emit the Submit-skipped template from `../skills/run-summary/SKILL.md` and stop. The branch was not pushed in this case (Step 1 was not reached).

## Rules of Engagement

Universal invariants live in `../skills/hardening-guardrails/SKILL.md` (always loaded). Submit-specific enforcement:

- **Pre-push `git diff --stat` check** enforces guardrail #1 (no production files in the diff). Production file present -> stop and report; do not push.
- **No retries on PR-creation failure** (ADO MCP or `gh` CLI). Branch is already pushed -- emit the platform-appropriate recovery block (Step 4a / 4b) and stop.
- **No survey on non-PR runs.** Skip the feedback survey when the PR was not created (Skip / Fail terminal states).
- **Description integrity.** Real newlines only; honor the 4,000-character ceiling by condensing finding bullets, not by dropping findings. The same description body is reused across ADO and GitHub paths.
- **Platform consistency.** The platform recorded in Step 0 is the only source of truth for Step 4 dispatch; do not infer platform from later steps.

### Phase-Unique Skill Files

Universal skills (`hardening-guardrails`, `run-summary`) are loaded automatically per the agent file. Submit-unique references:

| Skill | Path | Purpose |
|-------|------|---------|
| save-branch-and-push | `../../../shared/skills/save-branch-and-push/SKILL.md` | Create branch with correct naming and push (shared). |
| detect-default-branch | `../../../shared/skills/detect-default-branch/SKILL.md` | Determine the repository's default branch (shared). |
| pr-description | `../skills/pr-description/SKILL.md` | PR title/description template (adapted for hardening, see Step 2). |

### Required Information Gathering

Before generating the PR description, ensure you have:

1. Test identification: file paths and method names of every test edited.
2. Categories applied (from the Improve summary).
3. Findings applied: one bullet per applied finding with impact, confidence, failure mode, and before/after summary.
4. Findings skipped: list every finding the Improve prompt skipped, with reason.
5. Validation results: build result, single-test pass counts, stress-test pass rate.
6. Production-code confirmation: explicit `None` line.

### Validation Checklist

- Description follows the adapted template from Step 2 (no freeform sections).
- Description uses real newlines, not escaped `\n`.
- `### Production Code Changed` section is present with value `None`.
- Every applied finding is listed in `### Audit Findings Applied`.
- Every skipped finding is listed with reason.
- PR description is under 4,000 characters; if over, condense bullets -- do not drop findings.
- Only test files were modified (confirmed via `git diff --stat` in Step 1).

### Content Generation Rules

- Be specific: exact test method names, file paths, line ranges, impact, confidence score, failure mode.
- Be honest: list skipped findings; do not pretend the audit was 100% applied.
- Be concise: one bullet per finding; no narrative paragraphs.
- Preserve metadata so the scenario can be tracked.

## Output Format

Follow `../skills/run-summary/SKILL.md` for the Submit-phase emission templates (`Schema: RunSummary v1 | Phase: Submit`). Submit has three terminal states: `Submit complete.`, `Submit skipped.`, and `PR creation failed.`. Use the appropriate block based on the outcome of Steps 0-4. Use `n/a` for fields that do not apply. The End2End orchestrator parses these blocks.
