---
name: octane-tester-test-run
description: >-
  Identify and selectively run the unit tests impacted by a given scope (a
  file, area, feature, or Git commit), then report results in a structured Test
  Execution Results table. Use when a developer says "run impacted tests", "run
  tests for this file/commit", or "execute the affected unit tests".
metadata:
  type: operational
  agent: Tester
  version: "1.0"
---

# Test Run — Tester Session

Analyze a provided scope, identify the unit tests impacted by it, run them
selectively, and report the results. This is one of the two canonical
entrypoints for the `test-analysis` scenario.

## When to Use

- The user says "run impacted tests", "run tests for this file/commit", or
  "execute the affected unit tests".
- The user provides a `Scope` (a section/area of the codebase, a specific
  feature, or a Git commit) whose impacted tests should run.
- The agent should be `Tester` (see
  [agents/Octane.Tester.agent.md](../../agents/Octane.Tester.agent.md)); it
  carries the declared model, the `code-search/*` tool allow-list, and the
  step-compliance guarantees this skill depends on. If a different agent is
  active, this skill will delegate — see
  [Agent Delegation](#agent-delegation-mandatory).

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `Scope` | Yes | The scope of unit tests to run: a section/area of the codebase, a specific feature, or a Git commit. If missing, stop and ask. |

If `Scope` is missing, you cannot proceed. Stop and ask for it. Do not provide
an example request — just state that the input is required.

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
    agent (e.g., `@Tester /octane-tester-test-run …`) and stop.
  - **Copilot CLI**: re-invoke with `--agent Tester` (e.g.,
    `copilot --agent Tester -p "/octane-tester-test-run …"`) or launch
    `Tester` as a sub-agent for this task and pass through the inputs.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch to
    `Tester` as a sub-agent and forward the `Scope` input.

Do **not** silently execute the workflow under a generic or unrelated agent —
the test selection and execution assume the `Tester` tool allow-list and
step-compliance contract, and running them elsewhere may fabricate results or
skip required steps.

## Primary Directive

Analyze the provided `${input:Scope}`, identify the impacted tests, and run them
selectively, reporting the results in the mandatory template below.

## Steps

Present the following steps as **trackable todos** to guide progress.

### 1. Code Review

Read and understand the `${input:Scope}`. Identify the modules or features it
covers and the intended functionality.

### 2. Perform Deep Code Analysis

Use the `code-search/*` tools to:

- Understand the code, its key logic branches, and edge cases.
- Find the tests that are already in place for the code.

### 3. Run Impacted Tests

- Based on the analysis, identify and run the tests impacted by the changes in
  the scope.
- Follow the instructions in `${config:test-analysis.testing_instructions}` from the
  scenario [config/octane.yaml](../../config/octane.yaml) to execute the tests
  if present; otherwise use your best judgement.

### 4. Next Steps

- Document the results of the test runs, including any failures or issues
  encountered.
- Offer to assist with fixing any failing tests or issues identified.

## Template Guidance

- Match all **section headers** exactly (case-sensitive).
- Ensure **each section is populated** with specific, actionable content.
- Format content using **structured formats** (tables, lists, key-value blocks).
- Ensure tables contain **all required columns** with no omissions.
- Eliminate all **placeholder text** from final deliverables.

## Mandatory Template

```markdown
# Test Execution Results

[Describe the context of the test execution, including the code file analyzed and the testing approach used.]

## Scoring

| Class | Method | Result | Comments |
|-------|--------|--------|----------|
| [ClassName] | [MethodName] | [Pass/Fail] | [Provide details on the test execution, including any errors or issues encountered] |

## Recommended Actions

[List any recommended actions based on the test results, such as fixing failing tests or improving test coverage]

1. [Action Item 1]
2. [Action Item 2]
3. [Action Item 3]
```

## Example

```text
/octane-tester-test-run UserRepository.cs
```

The Tester locates the unit tests impacted by `UserRepository.cs`, runs them,
and returns the Test Execution Results table with any recommended follow-up
actions.

## Output

A Markdown **Test Execution Results** report following the mandatory template:
the execution context, a per-test results table (class, method, result,
comments), and a prioritized list of recommended actions.
