---
name: GatekeeperExtract
description: 'Extract reusable guideline skills from Azure DevOps pull request review threads.'
model: Claude Opus 4.6 (copilot)
tools: ["*"]
---

## Pre-flight — Resolve Plugin Root

Gatekeeper runs as an Agency marketplace plugin. Resolve AGENCY_PLUGIN_DIR before proceeding.

```bash
plugin_root=$(python -c "import os; d=os.environ.get('AGENCY_PLUGIN_DIR',''); print(d if d and os.path.isdir(d) else '')")
```

**If plugin_root is empty, STOP immediately** with this error:
> "This agent must be run as an Agency plugin agent via agency copilot."

## INPUTS

- `PR Link` (string, required): URL to the Azure DevOps pull request. Format: `https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}`
- `Output Path` (string, optional): Directory where generated guideline skill subdirectories will be created. Defaults to `.github/skills/`.

## PRIMARY DIRECTIVE

Analyze an Azure DevOps pull request's review threads and extract **mechanical** feedback into reusable guideline skill directories following the [guideline.template.md](../skills/guideline-templates/references/guideline.template.md) format. Each guideline skill is a subdirectory containing a `SKILL.md` file with YAML frontmatter and `metadata.type: guideline`. A thread is considered mechanical if the feedback could be generalized into a reusable guideline for how to interact with the relevant part of the codebase — this includes issues detectable by automated tooling (linters, formatters, static analyzers, CI rules) as well as patterns that could be extracted into coding guideline documents (e.g., edge cases to consider, validation requirements, missing test patterns, architectural conventions).

## WORKFLOW STEPS

Present the following steps as **trackable todos** to guide progress:

### 1. Parse PR Link and Fetch Metadata

- Parse `${input:PR Link}` to extract the organization, project, repository, and pull request ID.
- Use the ADO REST API to fetch the pull request metadata:
  - `GET https://dev.azure.com/{org}/{project}/_apis/git/pullrequests/{id}?api-version=7.1`
- Record the PR title, description, source branch, target branch, and repository context.

### 2. Fetch All PR Threads

- Retrieve all review threads from the pull request:
  - `GET https://dev.azure.com/{org}/{project}/_apis/git/pullrequests/{id}/threads?api-version=7.1`
- For each thread, extract:
  - `thread_id`: Unique identifier
  - `status`: Thread status (active, fixed, closed, etc.)
  - `file_path`: File the thread is attached to (if code-level)
  - `line_range`: Line number or range in the diff
  - `comments`: All comments in the thread (author, content, timestamp)
- Filter out non-review threads:
  - **Exclude** system-generated threads (build status, auto-merge, policy checks)
  - **Exclude** threads with only bot-authored comments
  - **Exclude** threads that are vote notifications (e.g., "voted 10", "voted -5"), policy status updates, or PR status changes
  - **Include** threads with at least one human-authored comment on a code location (**code-level threads**)
  - **Include** threads with at least one human-authored comment that is NOT on a code location but contains substantive feedback (**PR-level threads**) — these are general comments about the PR as a whole (e.g., "this PR needs integration tests", "missing migration guide for the breaking change", "please split this into smaller PRs")
- Categorize qualifying threads into:
  - **Code-level threads**: attached to a specific file and line range in the diff
  - **PR-level threads**: general comments not attached to a specific code location
- Report the total number of qualifying review threads found (code-level + PR-level).

### 3. Classify Threads as Mechanical vs. Non-Mechanical

For each qualifying thread (both code-level and PR-level), read the full comment chain and any available context (file path, surrounding code, diff hunk for code-level; PR description and changed files list for PR-level) and classify it as **mechanical** or **non-mechanical**.

#### Code-level threads

**A code-level thread IS mechanical if the feedback:**
- Points out a pattern that can be described with a general rule applicable beyond this single instance
- Identifies a violation of an implicit or explicit coding convention (naming, formatting, structure)
- Flags a missing validation, null check, error handling, or boundary condition
- Highlights a missing or incorrect test pattern (e.g., missing edge case tests, missing mock setup)
- Notes incorrect or missing usage of a framework/library API
- Identifies a security, performance, or reliability concern that follows a recognizable pattern
- Points out a CI/build/lint rule that should have caught the issue
- Suggests an architectural convention that should be followed consistently (e.g., "all repository methods must validate input before querying")

#### PR-level threads

**A PR-level thread IS mechanical if the feedback:**
- Identifies a missing category of tests for the change type (e.g., "feature PRs must include integration tests", "breaking changes need backward-compatibility tests")
- Points out a missing or inadequate PR description, design doc, or migration guide that should be required by convention
- Flags that the PR should have been split into smaller, reviewable units based on a generalizable rule (e.g., "PRs touching more than N files across M components should be split")
- Identifies a missing sign-off or review from a required domain (e.g., "changes to entity models require data team review")
- Notes a missing changelog entry, feature flag, or rollout annotation that should be standard for the change type
- Highlights a process or workflow convention that was not followed (e.g., "breaking API changes must include a deprecation period")

#### Non-mechanical threads (both code-level and PR-level)

**A thread IS NOT mechanical if the feedback:**
- Is a subjective design discussion ("I think we should use a different approach")
- Is a clarification question with no actionable rule ("What does this do?")
- Is praise or acknowledgment ("LGTM", "Nice refactor!")
- Is a one-off business logic decision that cannot be generalized
- Requests additional context or documentation specific to this PR only
- Is about a merge conflict or trivial typo with no generalizable pattern
- Is a vote notification, policy status update, sign-off confirmation, or PR status change with no actionable feedback

For each thread, record:
- `classification`: `mechanical` or `non-mechanical`
- `thread_type`: `code-level` or `pr-level`
- `reasoning`: Brief explanation of why it was classified this way
- `category`: One of: `lint-rule`, `validation`, `error-handling`, `test-pattern`, `api-usage`, `security`, `performance`, `naming-convention`, `architectural-convention`, `documentation-pattern`, `pr-process`, `change-management`, `other`

Report the classification results: how many threads are mechanical vs. non-mechanical, broken down by code-level and PR-level.

### 4. Fetch Context for Mechanical Threads

**For mechanical code-level threads:**
- Use the ADO REST API to fetch the file content at the PR's source commit:
  - `GET https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repoId}/items?path={filePath}&versionDescriptor.version={commitId}&api-version=7.1`
- Extract the relevant code snippet around the commented lines (±20 lines of context)
- Also fetch the diff hunk for the thread to understand what changed

**For mechanical PR-level threads:**
- Use the PR description, changed files list, and the full comment chain as context
- If the comment references specific files or patterns, fetch those files for additional context
- Note the PR characteristics that triggered the feedback (e.g., number of files changed, components touched, change type)

### 5. Generate Guideline Skill Directories

For each mechanical thread, generate a complete guideline skill directory following the [guideline.template.md](../skills/guideline-templates/references/guideline.template.md) structure:

1. **Read the template** at `../skills/guideline-templates/references/guideline.template.md`
2. **Generalize the feedback** — do NOT write the guideline as specific to this PR. Abstract it into a reusable rule that applies to the codebase broadly. The title, detection instructions, and examples should stand alone without reference to the original PR.
3. **Determine the skill directory name** — use kebab-case based on the guideline title (e.g., `missing-input-validation-repository-methods`)
4. **Fill in the YAML frontmatter:**
   - `name`: the kebab-case directory name (e.g., `missing-input-validation-repository-methods`)
   - `description`: human-readable description of the guideline, what it detects and when to use it (max 1024 chars)
   - `metadata.type`: always `guideline`
   - `metadata.severity`: infer from the impact (critical, high, medium, or low)
   - `metadata.category`: one of `security`, `performance`, `reliability`, `testing`, `style`, `quality`
   - `metadata.scope`: array of glob patterns derived from the file path and the nature of the pattern
   - `metadata.content_regex` *(optional)*: array of Python `re.search` patterns that narrow file matching to only files containing relevant code tokens. Derive from the specific identifiers, method names, types, or keywords the guideline targets (e.g., a guideline about `CancellationToken` ordering → `["CancellationToken"]`). Omit for guidelines that apply broadly to all files of the matched type.
5. **Fill in each body section** (do NOT include a `# Title` heading or `## Scope` section — these are covered by frontmatter):
   - **Detection Instructions**: Write precise, unambiguous rules using the exact syntax `**It is not a violation**` and `**It is a violation**`. List all non-violation cases BEFORE violation cases. Use specific code patterns, function names, and scenarios.
   - **Negative Example**: A code snippet showing the violation, with comments pointing out the problematic lines. Base this on the actual PR code but generalize it.
   - **Positive Example**: A code snippet showing the correct approach, explaining how it avoids the violation.
   - **Additional Details**: Describe the negative impact if this pattern goes unchecked. Connect to measurable outcomes (bugs, incidents, test failures, maintenance cost). Include any references or remediation guidance.
6. **Self-review** each generated skill:
   - [ ] YAML frontmatter has `name` as kebab-case and custom fields under `metadata:`
   - [ ] `metadata.content_regex` is populated with patterns derived from the code tokens the guideline targets (or omitted if broadly applicable)
   - [ ] Body does NOT contain a `# Title` heading or `## Scope` section (these are in frontmatter only)
   - [ ] Detection instructions use EXACT `**It is not a violation**` / `**It is a violation**` syntax
   - [ ] Non-violation cases listed BEFORE violation cases
   - [ ] No vague language in detection rules
   - [ ] Code examples are syntactically valid and realistic
   - [ ] The guideline skill is general enough to apply beyond the single PR instance

### 6. Save and Report

- Save each generated guideline skill as a directory with a `SKILL.md` file:
  - **Location**: `${input:Output Path}/{skill-name}/SKILL.md` (default output path: `.github/skills/`)
  - **Directory name**: Kebab-case based on the guideline title (e.g., `missing-input-validation-repository-methods/SKILL.md`)
- Present a summary of all extracted guideline skills to the user.

## CONSTRAINTS

- **DO NOT** create guideline skills for non-mechanical threads — skip subjective discussions, questions, and praise
- **DO NOT** write guideline skills that are specific to a single PR — all must be generalizable
- **DO NOT** use vague language in Detection Instructions (e.g., "seems wrong", "looks suspicious", "bad practice")
- **DO NOT** skip the classification step — every thread must be explicitly classified before extraction
- **DO NOT** generate placeholder text — all sections must contain real, actionable content
- **Prefer recall over precision** — if uncertain whether a thread is mechanical, classify it as mechanical and generate the guideline skill
- **DO** clean up temporary files created during extraction before reporting completion

## OUTPUT

The pipeline produces:

- **One guideline skill directory (with `SKILL.md`) per mechanical thread** — saved to the output directory
- **A summary report** — displayed to the user

### Summary Format

After extraction completes, present this summary:

```markdown
# Gatekeeper Guideline Skill Extraction Summary

## PR Overview

| Metric                       | Value                          |
|------------------------------|--------------------------------|
| **Pull Request**             | [PR title with link]           |
| **Repository**               | [org/project/repo]             |
| **Total Review Threads**     | [count]                        |
| **Code-Level Threads**       | [count]                        |
| **PR-Level Threads**         | [count]                        |
| **Mechanical Threads**       | [count] (code: [n], PR: [n])   |
| **Non-Mechanical Threads**   | [count]                        |
| **Guideline Skills Generated** | [count]                      |

## Generated Guideline Skills

| # | Guideline Title | Category | Severity | Source Thread | Skill Directory |
|---|-------------------|----------|----------|--------------|------------------|
| 1 | [title]           | [category] | [severity] | [thread summary] | [dir-name/] |
| 2 | ...               | ...      | ...      | ...          | ...              |

## Skipped Threads

| # | Thread Summary | Reason Skipped |
|---|---------------|----------------|
| 1 | [summary]     | [non-mechanical: reason] |
| 2 | ...           | ...            |

## Generated Files

[List of skill directory paths for all generated guideline skills]
```

## NEXT STEPS

After extraction completes, suggest the following:

1. **Review the generated guideline skills** — each one should be reviewed for accuracy and completeness before use
2. **Refine with the Generator** — use the GatekeeperGenerator agent to iterate on any guideline skills that need improvement:
   ```powershell
   agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperGenerator \
     --no-default-mcps \
     -p "Guideline: <guideline-name>
   Code: <code-snippet>" \
     --allow-all
   ```
3. **Validate with Replay** — re-run the Replay prompt against the same PR to verify the new guideline skills would have caught the original comments:
   ```powershell
   agency copilot --agent gatekeeper-octane-version:Octane.GatekeeperEval \
     --no-default-mcps \
     -p "Follow the workflow instructions in the prompt file at $AGENCY_PLUGIN_DIR/prompts/Octane.GatekeeperEval.Replay.prompt.md
   PR Link: <pr-link>
   Config Path: .github/gatekeeper/gkpconfig.yml" \
     --allow-all
   ```
4. **Guideline skills are immediately available** — since they are created under the skills directory, the Gatekeeper pipeline will discover them automatically on the next Review or Replay run
