---
name: octane-tester-test-analysis
description: >-
  Analyze a scope of code for test coverage, reliability, and best practices,
  then produce a structured Test Analysis report with per-assessment scores and
  prioritized recommendations. Use when a developer says "analyze these tests",
  "review test coverage", "assess test quality", or "analyze tests for this
  file/commit".
metadata:
  type: operational
  agent: Tester
  version: "1.0"
---

# Test Analysis — Tester Session

Analyze a provided scope of code, locate the tests that cover it, and evaluate
those tests against the configured assessments (test coverage, reliability, and
best practices). This is one of the two canonical entrypoints for the
`test-analysis` scenario.

## When to Use

- The user says "analyze these tests", "review test coverage", "assess test
  quality", or "analyze tests for this file/commit".
- The user provides a `Scope` (code files, unit tests, or a Git commit) they
  want assessed.
- The agent should be `Tester` (see
  [agents/Octane.Tester.agent.md](../../agents/Octane.Tester.agent.md)); it
  carries the declared model, the `code-search/*` tool allow-list, and the
  step-compliance guarantees this skill depends on. If a different agent is
  active, this skill will delegate — see
  [Agent Delegation](#agent-delegation-mandatory).

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `Scope` | Yes | What to analyze: `CodeFiles`, `UnitTests`, or `GitCommit` (a path, area, feature, or commit SHA). If missing, stop and ask. |

If `Scope` is missing, you cannot proceed. Stop and ask for it. Do not provide
an example request — just state that the input is required.

## Assessments

Evaluate the tests against `${config:test-analysis.analysis.assessments}` from the
scenario [config/octane.yaml](../../config/octane.yaml). If no assessments are
configured, use these defaults:

1. **test_coverage** — Determine whether all critical paths and edge cases are
   covered; highlight missing scenarios; suggest additional tests.
2. **reliability** — Detect flaky or unstable tests; recommend changes that
   improve consistency and determinism.
3. **best_practices** — Review test structure, naming, and clarity; ensure
   alignment with recognized testing standards; suggest maintainability and
   readability improvements.

## Agent Delegation (MANDATORY)

This skill is designed to run under the `Tester` agent (see
[agents/Octane.Tester.agent.md](../../agents/Octane.Tester.agent.md)), which
carries the model declaration, the `code-search/*` tool allow-list, and the
step-compliance + quality guarantees this skill assumes.

**Before executing any step below, check the active agent:**

- **If the active agent IS `Tester`** → proceed to `## Primary Directive`.
- **If the active agent is NOT `Tester`** → you MUST delegate this
  skill's execution to `Tester` instead of running it yourself. Use the
  host's agent-switching mechanism:
  - **VS Code Copilot Chat**: instruct the user to re-invoke under the target
    agent (e.g., `@Tester /octane-tester-test-analysis …`) and stop.
  - **Copilot CLI**: re-invoke with `--agent Tester` (e.g.,
    `copilot --agent Tester -p "/octane-tester-test-analysis …"`) or
    launch `Tester` as a sub-agent for this task and pass through the
    inputs.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch to
    `Tester` as a sub-agent and forward the `Scope` input.

Do **not** silently execute the workflow under a generic or unrelated agent —
the assessment scoring and mandatory template assume the `Tester` tool
allow-list and step-compliance contract, and running them elsewhere may
fabricate results or skip required steps.

## Primary Directive

Analyze the provided `${input:Scope}`, identify the relevant code sections,
review the tests covering them against the configured assessments, and compile
a Test Analysis report that strictly follows the mandatory template below.

## Steps

Present the following steps as **trackable todos** to guide progress.

### 1. Code Review

Read and understand the `${input:Scope}`. Identify the modules or features it
covers and the intended functionality.

### 2. Perform Deep Code Analysis

Use the `code-search/*` tools to:

- Understand the code, its key logic branches, and edge cases.
- Find the tests that are already in place for the code.

### 3. Branch on Test Presence

- **If tests ARE NOT found**:
  - Establish a test plan outlining the key scenarios to test, expected
    outcomes, and the testing approach.
  - Observe similar code patterns and existing tests in the codebase for
    guidance.
  - Present the test plan and offer to implement it.
- **If tests ARE found**:
  - Identify the key scenarios being tested, including edge cases and error
    conditions.
  - Map these scenarios to the relevant code paths and logic branches.

### 4. Test Assessment

Use the assessments to evaluate the tests and compile findings into a summary
report that strictly follows the mandatory template.

### 5. Next Steps

- Offer to assist with implementing the recommended changes to the tests and
  codebase.
- After receiving confirmation, make the agreed-upon changes.
- You MUST validate the changes by running the tests and ensuring they pass
  successfully.

## Template Guidance

- Match all **section headers** exactly (case-sensitive).
- Ensure **each section is populated** with specific, actionable content.
- Format content using **structured formats** (tables, lists, key-value blocks).
- Ensure tables contain **all required columns** with no omissions.
- Eliminate all **placeholder text** from final deliverables.

## Mandatory Template

```markdown
# Test Analysis

## Overview

This section provides an overview of the testing process, including the objectives, scope, and key stakeholders involved in the testing efforts.

**System Under Test (SUT)**

[path/to/system/under/test.cs (use a bullet list if multiple files)]

**Test Suite**

[path/to/test/file.cs (use a bullet list if multiple files)]

**Strategy**

[Briefly describe the overall testing strategy found in the test suite]

## Scoring

| Assessment | Score (1-10) | Comments |
|------------|--------------|----------|
| Assessment 1 | 5/10 | Detailed comments on the reasoning for the score. |

## Assessments

1. Assessment 1
    - Score: 5/10
    - Strengths:
        - [Identify specific strengths of the tests]
    - Weaknesses:
        - [Identify specific weaknesses of the tests based on the assessment criteria]
    - Recommendations:
        - [Provide actionable recommendations to improve the tests based on the assessment]
2. Assessment 2
    - Score: 7/10
    - Strengths:
        - [Identify specific strengths of the tests]
    - Weaknesses:
        - [Identify specific weaknesses of the tests based on the assessment criteria]
    - Recommendations:
        - [Provide actionable recommendations to improve the tests based on the assessment]

## Recommended Actions

1. High Priority
    a. [List high priority actions to be taken]
2. Medium Priority
    a. [List medium priority actions to be taken]
3. Low Priority
    a. [List low priority actions to be taken]
```

## Example

```text
/octane-tester-test-analysis UserRepositoryTests.cs
```

The Tester reviews `UserRepositoryTests.cs` and the code under test, scores each
configured assessment, and returns the Test Analysis report with prioritized
recommendations.

## Output

A Markdown **Test Analysis** report following the mandatory template: an
overview of the system under test and strategy, a per-assessment scoring table,
detailed strengths/weaknesses/recommendations per assessment, and a prioritized
list of recommended actions.
