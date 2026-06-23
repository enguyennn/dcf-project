---
name: octane-planner-requirements
description: >-
  Generate a structured Requirements (REQ) document for a feature or change,
  capturing user stories, acceptance criteria, assumptions, and alternative
  interpretations before any planning begins. Use when the user says
  "create requirements", "draft a REQ", "write requirements for <feature>",
  or wants to start the Spec-Driven Development workflow from a raw idea.
metadata:
  type: operational
  agent: SddPlanner
  version: "1.0"
---

# Generate Requirements Document

Produce a machine-readable, deterministic **Requirements Document** for a
feature, change, or initiative. This is the first phase of the Spec-Driven
Development (SDD) workflow: Requirements → Plan → Implement → Review.

## When to Use

- The user says "create requirements", "draft a REQ", or "write requirements
  for <feature>"
- The user has a feature idea or initiative and wants to capture user needs,
  scope, and constraints before planning
- The agent should be `SddPlanner` (see
  [agents/Octane.SddPlanner.agent.md](../../agents/Octane.SddPlanner.agent.md));
  it carries the declared model, tool allow-list, and planning-quality
  guarantees this skill depends on. If a different agent is active, this
  skill will delegate — see [Agent Delegation](#agent-delegation-mandatory).

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `Purpose` | Yes | A clear, concise description of the feature, change, or initiative the requirements should address. |

If `Purpose` is missing, stop and ask. Do not provide an example request —
just state that the input is required.

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
    target agent (e.g., `@SddPlanner /octane-planner-requirements …`) and stop.
  - **Copilot CLI**: re-invoke with `--agent SddPlanner` (e.g.,
    `copilot --agent SddPlanner -p "/octane-planner-requirements …"`) or launch
    `SddPlanner` as a sub-agent for this task and pass through the inputs.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch to
    `SddPlanner` as a sub-agent and forward `Purpose`.

Do **not** silently execute the workflow under a generic or unrelated agent
— the requirements quality contract assumes the `SddPlanner` tool allow-list
and step-compliance guarantees, and running it elsewhere may produce
shallow or ungrounded requirements.

## Primary Directive

Generate a **Requirements Document** for the initiative described in
`${input:Purpose}`. The requirements must be:

- **Compliant** with all template format, structure, and guidelines
- **Machine-readable** and structured for autonomous execution by AI systems
  or human teams
- **Deterministic**, with no ambiguity or placeholder content

## Steps

Present the following steps as **trackable todos** to guide progress.

1. **Understand the Request**
   - Thoroughly review the `${input:Purpose}` document or instructions.
   - Identify and note all key features, requirements, and constraints
     outlined in the purpose.

2. **High-Level Review of Codebase**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Read the project overview doc or README.md to understand
       the system architecture and relevant modules.
     - Perform a high-level review of the codebase using the `code-search/*`
       tools to identify existing functionality related to the requested
       change.
     - Identify the key components, services, or modules that will be
       affected by the proposed change.
     - Respond to the main agent with all relevant context for drafting the
       requirements.

3. **Deep Code Analysis**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Analyze the identified components, services, or modules in detail
       using the `code-search/*` tools.
     - Identify all related components and dependencies within the codebase
       that may impact the new requirements.
     - Gather insights and details on the existing implementation and all
       related code.
     - Respond to the main agent with all relevant context for drafting the
       requirements.

4. **Synthesize Information**
   - Combine insights from the `${input:Purpose}`, high-level review, and
     deep code analysis.
   - Create a comprehensive understanding of the feature or change,
     including scope, constraints, and dependencies.

5. **Surface Assumptions and Interpretations**
   - Identify every assumption you are making that is not explicitly stated
     in the `${input:Purpose}`. Be thorough — silent assumptions compound
     downstream.
   - Where the purpose is ambiguous, document each alternative interpretation
     you considered and explain which one you chose and why.
   - Assess the confidence level of each assumption and the impact if it
     turns out to be wrong.
   - These will be captured in the Assumptions and Interpretations section
     of the requirements document, giving reviewers a clear opportunity to
     catch misunderstandings before planning begins.

6. **Draft the Requirements Document**
   - Complete the requirements document with all required sections, tables,
     metadata, and guidance from the
     [`octane-req-authoring-standards.md`](references/octane-req-authoring-standards.md)
     reference.

7. **Review and Refine**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Critically review the drafted requirements document.
     - Ensure the document is comprehensive, clear, and actionable.
     - Validate that all aspects of the purpose have been addressed.
     - Make necessary adjustments based on self-review.

## File Naming Convention

- Save the requirements document under
  `${config:spec-driven-development.artifacts.requirements}`, which defaults to
  `docs/projects/`.
- Use the following naming convention:
  `[purpose]-[component]/[purpose]-[component].req.md`
- Examples:
  - `upgrade-database-v2/upgrade-database-v2.req.md`
  - `add-user-authentication/add-user-authentication.req.md`

## Example

```text
/octane-planner-requirements migrate to redis from in-memory cache
```

Produces a `redis-migration/redis-migration.req.md` document with user
stories, acceptance criteria, an Assumptions and Interpretations section
(`ASM-`/`ALT-` IDs), and scope/constraints grounded in the existing
codebase.

## Output

A `.req.md` document compliant with
[`octane-req-authoring-standards.md`](references/octane-req-authoring-standards.md),
ready for the planning phase.

## Next Steps

After completing the requirements document, present the following next steps
to the user:

**Your requirements document has been created. Here are your next steps:**

1. **Review the requirements** — Validate the document with stakeholders.
2. **Generate a PRD** — Create a detailed implementation plan:
   ```text
   /octane-planner-plan <path-to-your-req.md>
   ```
