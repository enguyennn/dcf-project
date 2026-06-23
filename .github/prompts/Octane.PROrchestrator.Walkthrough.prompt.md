---
description: Interactive PR walkthrough with architecture diagrams for reviewers
agent: PROrchestrator
---

# Walkthrough — Agent Prompt

Post a PR Walkthrough that gives reviewers a structured "reading guide" — architecture diagrams, file inventory, sequence diagrams, and concept explainers.

## Inputs

- **PR URL**: {{ workflow.input.pr_url | default('') }}
- **Target branch**: {{ workflow.input.target_branch | default('main') }}

## Primary Directive

Produce a comprehensive PR Walkthrough that lowers the cognitive load of reviewing code the reviewer may not be familiar with.

**This is NOT a review.** It does not judge code quality or post findings. It teaches.

## Skip Conditions

Skip the walkthrough and report `ℹ️ Walkthrough skipped — trivial change` when:
- The PR is **docs-only** (all changed files are `.md`, `.txt`, `.rst`, or similar)
- The PR is a **single config change** (one file, config/yaml/json only)
- The PR has **fewer than 3 changed files** and no new endpoints or public APIs

When skipped, set `walkthrough_posted = false` and `skip_reason` accordingly.

## Workflow

### 1. Gather Context

Parse the PR URL. Fetch in parallel:
- **PR metadata** — title, description, author, branch, work items
- **Changed files** — if `changed_files_path` is provided and exists, read it (JSON array of PR-scoped file paths). Otherwise use `git diff --stat {{ workflow.input.target_branch | default('main') }}...HEAD`
- **Full diff** — for tracing code flows

### 2. Classify the PR

| Signal | Classification |
|--------|---------------|
| UI components, views, styles, hooks | **Frontend / UI** |
| Services, data access, API clients | **Data / Service layer** |
| Controllers, endpoints, middleware | **API / Backend** |
| Test files only | **Test-only** |
| Docs/markdown only | **Documentation** |
| Multiple layers | **Full-stack feature** |

### 3. Build the Walkthrough

#### 3a. Architecture Diagram
Render an **ASCII box diagram** showing:
- Components/files changed (highlighted with `*`)
- How they connect to each other
- Data flow direction (arrows `→`, `←`, `↓`)
- External dependencies

Keep it focused on what changed — don't diagram the entire codebase.

#### 3b. File Inventory
Table of changed files grouped by layer, ordered by reading sequence (data model → service → controller → UI → test):

```
| Layer | File | Lines Changed | What It Does (one sentence) |
|-------|------|--------------|----------------------------|
```

#### 3c. Sequence Diagrams
For each user-facing flow introduced or changed, render an ASCII sequence diagram showing the call chain, decision points, and error paths. Skip if no user-facing flows changed.

#### 3d. State Machines
If the code implements a state machine (loading/success/error, wizard steps, workflow states), render as ASCII. Skip if none present.

#### 3e. Key Concepts
For each framework concept or repo pattern that a reviewer might not know, provide a brief 2-3 sentence explainer. Calibrate to the codebase.

#### 3f. Data Shapes
Show key interfaces/types/entities that flow through the changed code, with brief annotations. Skip if no data models changed.

### 4. Output the Walkthrough

Output the walkthrough directly in conversation. Format:

```markdown
## 🗺️ PR Walkthrough

> Reading guide for reviewers. This is not a review — see the Review Digest for findings.

### Architecture
{ASCII architecture diagram}

### File Inventory
{file inventory table}

### Flows
{ASCII sequence diagrams}

### State Machines
{ASCII state diagrams, if applicable}

### Key Concepts
{concept explainers}

### Data Shapes
{type/entity definitions}
```

## Tone & Style

- **Conversational, not academic** — write like a senior teammate explaining over a screen share
- **Show, don't just tell** — use diagrams, code snippets, concrete examples
- **Assume intelligence, not knowledge** — the reader is smart but hasn't seen this code before
- **Highlight the interesting parts** — what's clever, surprising, or easy to miss
- **Call out gotchas** as "here's something worth understanding" — not review findings
- **No severity labels or review verdicts** — this isn't a review

## Expected Output

Populate these output fields:

- **walkthrough_posted**: `true` if walkthrough was generated, `false` if skipped
- **pr_classification**: PR classification (e.g., "Frontend / UI", "Full-stack feature")
- **skip_reason**: Reason for skipping (empty string if not skipped)
- **diagram_count**: Number of diagrams generated (architecture + sequence + state machine)
- **concepts_explained**: Number of concept explainers included
