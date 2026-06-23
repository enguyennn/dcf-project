---
name: octane-planner-plan
description: >-
  Generate a Product Requirements Document (PRD) — a detailed, executable
  implementation plan with architecture, design decisions, epics, items, and
  a simplicity rationale — from a requirements file or a raw purpose. Use when
  the user says "create a PRD", "make a plan", "plan <feature>", or has a
  `.req.md` file and wants the next phase of Spec-Driven Development.
metadata:
  type: operational
  agent: SddPlanner
  version: "1.0"
---

# Generate PRD (Implementation Plan)

Produce a machine-readable, deterministic **Product Requirements Document
(PRD)** for a feature or change. This is the planning phase of the
Spec-Driven Development (SDD) workflow: Requirements → Plan → Implement →
Review.

## When to Use

- The user says "create a PRD", "make a plan", or "plan <feature>"
- The user has a `.req.md` requirements file and wants a detailed
  implementation plan with epics and items
- The agent should be `SddPlanner` (see
  [agents/Octane.SddPlanner.agent.md](../../agents/Octane.SddPlanner.agent.md));
  it carries the declared model, tool allow-list, and planning-quality
  guarantees this skill depends on. If a different agent is active, this
  skill will delegate — see [Agent Delegation](#agent-delegation-mandatory).

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `PlanPurpose` | Yes | A clear, concise description of the feature, change, or initiative the PRD should address, or a link to a `.req.md` file containing the requirements. |

If `PlanPurpose` is missing, stop and ask. Do not provide an example request
— just state that the input is required.

## Agent Delegation (MANDATORY)

This skill is designed to run under the `SddPlanner` agent (see
[agents/Octane.SddPlanner.agent.md](../../agents/Octane.SddPlanner.agent.md)),
which carries the model declaration, the `code-search/*` tool allow-list,
and the step-compliance + planning-quality guarantees the SDD workflow
assumes.

**Before executing any step below, check the active agent:**

- **If the active agent IS `SddPlanner`** → proceed to `## Primary Directive`.
- **If the active agent is NOT `SddPlanner`** → you MUST delegate this skill's
  execution to `SddPlanner` instead of running it yourself. Use the host's
  agent-switching mechanism:
  - **VS Code Copilot Chat**: instruct the user to re-invoke under the
    target agent (e.g., `@SddPlanner /octane-planner-plan …`) and stop.
  - **Copilot CLI**: re-invoke with `--agent SddPlanner` (e.g.,
    `copilot --agent SddPlanner -p "/octane-planner-plan …"`) or launch
    `SddPlanner` as a sub-agent for this task and pass through the inputs.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch to
    `SddPlanner` as a sub-agent and forward `PlanPurpose`.

Do **not** silently execute the workflow under a generic or unrelated agent
— the planning quality contract assumes the `SddPlanner` tool allow-list and
step-compliance guarantees, and running it elsewhere may produce an
ungrounded or non-executable plan.

## Primary Directive

Generate a **Product Requirements Document (PRD)** for the initiative
described in `${input:PlanPurpose}`. The PRD must be:

- **Compliant** with all template format, structure, and guidelines
- **Machine-readable** and structured for autonomous execution by AI systems
  or human teams
- **Deterministic**, with no ambiguity or placeholder content

## Steps

Present the following steps as **trackable todos** to guide progress.

1. **Purpose Review**
   - If a requirements file (e.g., `.req.md`) is provided, read and analyze
     it.
   - Extract key goals, constraints, and success criteria to inform all
     subsequent steps.

2. **Deep Research**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Use the `code-search/*` tools to perform deep code analysis.
     - Validate the design within the context of the existing codebase.
     - Review important files and components that may be affected by the
       implementation.
     - Identify any potential challenges or dependencies.
     - Respond with all relevant context for drafting the plan.

3. **Draft the Plan**
   - Create a complete PRD with all required sections, tables, metadata, and
     guidance from the
     [`octane-prd-authoring-standards.md`](references/octane-prd-authoring-standards.md)
     reference.
   - Ensure it is ready for execution and review.

4. **Review and Refine**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Critically review the drafted implementation plan.
     - Ensure the plan is comprehensive, clear, and actionable.
     - Validate that all aspects of the design have been addressed.
     - Make necessary adjustments based on self-review.

## File Naming Convention

- Save all PRDs under `${config:spec-driven-development.artifacts.prd}`, which defaults to
  `docs/projects/`.
- If based on a `.req.md` file:
  - Save as `.prd.md` in the same directory.
- If not:
  - Use format: `[purpose]-[component]/[purpose]-[component].prd.md`
  - Valid prefixes: `upgrade`, `refactor`, `feature`, `data`,
    `infrastructure`, `process`, `architecture`, `design`
  - Examples:
    - `upgrade-system-command/upgrade-system-command.prd.md`
    - `feature-auth-module/feature-auth-module.prd.md`

## Example

```text
/octane-planner-plan redis-migration/redis-migration.req.md
```

Produces a `redis-migration/redis-migration.prd.md` document with solution
architecture, design decisions, an Implementation Plan (epics/items), a
Files Affected section, and a Simplicity Rationale.

## Output

A `.prd.md` document compliant with
[`octane-prd-authoring-standards.md`](references/octane-prd-authoring-standards.md),
ready for the implementation phase.

## Next Steps

After completing the PRD, present the following next steps to the user:

**Your PRD has been created. Here are your next steps:**

1. **Review the PRD** — Validate the implementation plan with stakeholders.
2. **Start implementation** — Implement the first epic from the PRD:
   ```text
   /octane-coder-implement <path-to-your-prd.md> EPIC-001
   ```
3. **Continue with additional epics** as needed:
   ```text
   /octane-coder-implement <path-to-your-prd.md> EPIC-002
   ```
