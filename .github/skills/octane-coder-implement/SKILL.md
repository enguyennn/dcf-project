---
name: octane-coder-implement
description: >-
  Implement a feature from a PRD's Implementation Plan, one epic at a time,
  using a test-first flow and surgical, fully-traced changes. Use when the
  user says "implement this PRD", "build EPIC-001", "implement <feature>", or
  has a `.prd.md` file and wants to move from plan to code in the Spec-Driven
  Development workflow.
metadata:
  type: operational
  agent: SddCoder
  version: "1.0"
---

# Implement Feature from PRD

Implement features from a Product Requirements Document (PRD), focusing on a
specific epic, using a test-first flow with surgical, traceable changes. This
is the implementation phase of the Spec-Driven Development (SDD) workflow:
Requirements → Plan → Implement → Review.

## When to Use

- The user says "implement this PRD", "build EPIC-001", or
  "implement <feature>"
- The user has a `.prd.md` file with an Implementation Plan and wants to turn
  epics/items into code
- The agent should be `SddCoder` (see
  [agents/Octane.SddCoder.agent.md](../../agents/Octane.SddCoder.agent.md)); it
  carries the declared model, tool allow-list, and the "Think Before Coding"
  + "Simplicity First" guardrails this skill depends on. If a different agent
  is active, this skill will delegate — see
  [Agent Delegation](#agent-delegation-mandatory).

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `PRD` | Yes | A link to a PRD file (e.g. `.prd.md`) that contains the Implementation Plan with epics and items. |
| `Epic` | Optional | The specific epic within the PRD that contains the item you will be implementing. If omitted, all epics are in scope. |

If `PRD` is missing, stop and ask. Do not provide an example request — just
state that the input is required.

## Agent Delegation (MANDATORY)

This skill is designed to run under the `SddCoder` agent (see
[agents/Octane.SddCoder.agent.md](../../agents/Octane.SddCoder.agent.md)), which
carries the model declaration, the `code-search/*` tool allow-list, and the
"Think Before Coding" + "Simplicity First" + surgical-changes guarantees this
workflow assumes.

**Before executing any step below, check the active agent:**

- **If the active agent IS `SddCoder`** → proceed to
  `## Primary Directive`.
- **If the active agent is NOT `SddCoder`** → you MUST delegate this
  skill's execution to `SddCoder` instead of running it yourself. Use the
  host's agent-switching mechanism:
  - **VS Code Copilot Chat**: instruct the user to re-invoke under the target
    agent (e.g., `@SddCoder /octane-coder-implement …`) and stop.
  - **Copilot CLI**: re-invoke with `--agent SddCoder` (e.g.,
    `copilot --agent SddCoder -p "/octane-coder-implement …"`) or launch
    `SddCoder` as a sub-agent for this task and pass through the inputs.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch to
    `SddCoder` as a sub-agent and forward `PRD` and `Epic`.

Do **not** silently execute the workflow under a generic or unrelated agent
— the implementation quality contract (test-first flow, surgical changes)
assumes the `SddCoder` tool allow-list and guardrails, and running it
elsewhere may introduce scope creep or untested changes.

## Primary Directive

Implement features from the `${input:PRD}` document. Focus on the specific
epic identified by `${input:Epic}`. If no epic is provided, consider all
epics to be in scope.

## Steps

Present the following steps as **trackable todos** to guide progress.

1. **PRD Review**
   - Review in detail the provided `${input:PRD}` document. Epics that are
     marked as DONE are out of scope.
   - Review the `Files Affected` section to identify which files will be
     created, modified, or deleted.

2. **Implementation**
   - For each epic that is in scope, use the `agent` tool to invoke a
     sub-agent that will:
     - Thoroughly review the epic details.
     - Use the `code-search/*` tools to perform deep code analysis to
       identify all relevant code, identify dependencies, and understand
       coding patterns.
     - Create a logical plan for implementing the epic.
     - **Write tests first** that define the success criteria for each ITEM
       in the epic. Run them and confirm they fail (they define what "done"
       looks like before code exists).
     - Make the necessary code changes until the tests pass.
     - Fix any errors, bugs, or issues that arise during implementation.
     - Ensure all changes adhere to best practices and coding standards.
     - Update the `${input:PRD}` document to reflect the completion of the
       epic.
     - Create a git commit with a clear and descriptive message summarizing
       the changes made for the epic. The commit message should start with
       the epic ID (e.g., "EPIC-001: Implement feature X").

   **Surgical changes constraint**: Every changed line MUST trace directly
   to a TASK or ITEM in the current epic. Do NOT:
   - "Improve" adjacent code, comments, or formatting outside the epic's
     scope
   - Refactor code that is not broken or specified for change in the PRD
   - Add type hints, docstrings, or style changes to code you did not
     functionally modify
   - Add error handling for scenarios not specified in the PRD's failure
     modes
   - Add abstractions, configurability, or flexibility not explicitly
     required

   If you notice unrelated issues (dead code, style inconsistencies,
   potential bugs), mention them in the implementation notes — do not fix
   them.

3. **Review**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Conduct a thorough review of all code changes made.
     - Use the `code-search/*` tools to perform deep code analysis to
       identify all updated and impacted code.
     - Ensure that the implementation:
       - Meets all requirements outlined in the PRD
       - Is free of bugs and errors
       - Includes appropriate tests and documentation
       - Strictly follows best practices and coding standards
     - If any issues are found, create a detailed list of required fixes and
       improvements, then return to the main agent.

## Example

```text
/octane-coder-implement redis-migration/redis-migration.prd.md EPIC-001
```

Implements EPIC-001 from the PRD using a test-first flow, updates the PRD's
epic status to DONE, and creates a git commit prefixed with the epic ID.

## Output

Code changes committed per epic/item, with passing tests and updated plan
status markers in the PRD.

## Next Steps

After completing the implementation, present the following next steps to the
user:

**Implementation complete. Here are your next steps:**

1. **Implement the next epic** (if more epics remain in the PRD):
   ```text
   /octane-coder-implement <path-to-your-prd.md> EPIC-00X
   ```
2. **Review all changes** — Validate implementation against the PRD:
   ```text
   /octane-coder-review <path-to-your-prd.md> <commit-range-or-branch-or-stagedOrUnstagedFiles>
   ```
3. **Commit your changes** — Stage and commit the implementation.
