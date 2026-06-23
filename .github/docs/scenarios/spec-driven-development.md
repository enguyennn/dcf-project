# Spec-Driven Development (SDD)

A complete Requirements → Plan → Implement → Review workflow that guides teams
through structured software development using requirements documents, product
specifications (PRDs), test-first implementation, and scope-compliant code
review. Powered by the scenario's `SddPlanner` and `SddCoder`
agents.

## When to Use

- Feature development with clear requirements
- Team collaboration with structured specs
- Ensuring implementation matches specifications
- Maintaining documentation throughout development
- Code review automation against a known specification

## Prerequisites

- **MCP Servers**:
  - `code-search` — code analysis and implementation grounding (registered as
    `code-search` in [`artifacts/shared/mcp.json`](../../shared/mcp.json) for
    the VS Code extension; declared inline in this scenario's
    [`.mcp.json`](./.mcp.json) for the Copilot CLI plugin)
  - `ms-learn` — Microsoft Learn documentation lookup (registered as
    `ms-learn` in [`artifacts/shared/mcp.json`](../../shared/mcp.json); also
    declared inline in [`.mcp.json`](./.mcp.json))
- Understanding of requirements-driven development and PRD/requirements
  documentation

### Copilot CLI only — `code-search` environment variables

The VS Code extension resolves the `code-search` connection by prompting the
user. The Copilot CLI does not support that prompt syntax, so this scenario's
[`.mcp.json`](./.mcp.json) reads the target repository from shell environment
variables instead. Export these before launching the CLI (point them at the
repository you want `code-search` to ground against):

```bash
export ADO_ORGANIZATION="<your-ado-org>"
export ADO_PROJECT="<your-ado-project>"
export ADO_REPOSITORY="<your-repo-name>"
export ADO_BRANCH="<your-branch>"   # e.g. main
```

On Windows PowerShell:

```powershell
$env:ADO_ORGANIZATION = "<your-ado-org>"
$env:ADO_PROJECT      = "<your-ado-project>"
$env:ADO_REPOSITORY   = "<your-repo-name>"
$env:ADO_BRANCH       = "<your-branch>"   # e.g. main
```

## Workflows

The four skills below compose the end-to-end SDD pipeline. Each is a standalone
slash command; run them in sequence or invoke any phase independently.

### Requirements

Generate a structured Requirements (REQ) document capturing user stories,
acceptance criteria, assumptions, and alternative interpretations before any
planning begins.

**Skill:** [`octane-planner-requirements`](./skills/octane-planner-requirements/SKILL.md) — owns codebase grounding, assumption surfacing, and REQ drafting.
**Agent:** [`SddPlanner`](./agents/Octane.SddPlanner.agent.md) — carries the declared model, `code-search/*` allow-list, and planning-quality guarantees.

**Steps:** review the purpose → high-level + deep codebase analysis → surface
assumptions (`ASM-`/`ALT-` IDs) → draft and self-review the `.req.md`.

#### Invocation

```text
/octane-planner-requirements
/octane-planner-requirements migrate to redis from in-memory cache
```

### Plan

Generate a Product Requirements Document (PRD): an executable implementation
plan with architecture, design decisions, epics/items, a Files Affected
section, and a Simplicity Rationale.

**Skill:** [`octane-planner-plan`](./skills/octane-planner-plan/SKILL.md) — owns deep research, plan drafting, and self-review.
**Agent:** [`SddPlanner`](./agents/Octane.SddPlanner.agent.md).

**Steps:** review purpose/`.req.md` → deep code analysis → draft the PRD →
self-review.

#### Invocation

```text
/octane-planner-plan
/octane-planner-plan redis-migration/redis-migration.req.md
```

### Implement

Implement a feature from the PRD, one epic at a time, using a test-first flow
and surgical, fully-traced changes.

**Skill:** [`octane-coder-implement`](./skills/octane-coder-implement/SKILL.md) — owns test-first implementation, the surgical-changes constraint, and per-epic commits.
**Agent:** [`SddCoder`](./agents/Octane.SddCoder.agent.md) — carries the "Think Before Coding" + "Simplicity First" guardrails.

**Steps:** PRD review → write failing tests → implement until green → update
PRD status → commit per epic → sub-agent review.

#### Invocation

```text
/octane-coder-implement redis-migration/redis-migration.prd.md EPIC-001
```

### Review

Review implementation changes against the PRD and generate a comprehensive
`.review.md` validation report with requirement traceability, scope-compliance
tracking, gap analysis, and a pass/fail verdict.

**Skill:** [`octane-coder-review`](./skills/octane-coder-review/SKILL.md) — owns the traceability matrix, scope-compliance checks, and the mandatory report template.
**Agent:** [`SddCoder`](./agents/Octane.SddCoder.agent.md).

**Steps:** parse PRD → analyze scope → deep implementation review →
requirements/quality validation → generate `.review.md`.

#### Invocation

```text
/octane-coder-review redis-migration/redis-migration.prd.md 9faf8ab..289682e
/octane-coder-review redis-migration/redis-migration.prd.md workspace
```

## Quality Principles

This scenario incorporates [Andrej Karpathy's four LLM coding principles](https://github.com/forrestchang/andrej-karpathy-skills)
as built-in quality gates:

- **Think Before Coding** — `octane-planner-requirements` surfaces assumptions
  (`ASM-` IDs with confidence/impact) and alternative interpretations (`ALT-`
  IDs) before drafting, ensuring ambiguity is resolved early.
- **Simplicity First** — the PRD template (`octane-planner-plan`) includes a
  Simplicity Rationale section requiring every epic to trace to a requirement
  and every new abstraction to be justified, with a "could this be simpler?"
  checkpoint.
- **Surgical Changes** — `octane-coder-implement` constrains every changed line
  to trace to a plan item, with no drive-by improvements allowed.
- **Goal-Driven Execution** — `octane-coder-implement` follows a test-first
  flow: define done via tests, then implement until tests pass.

`octane-coder-review` adds a **Scope Compliance** section that tracks untraced
changes, files outside PRD scope, and drive-by modifications.

## Custom Agents

### SddPlanner

Senior Technical Lead specializing in technical planning and development task
breakdown. Creates requirements documents and PRDs. Defined in
[`agents/Octane.SddPlanner.agent.md`](./agents/Octane.SddPlanner.agent.md). This is
a scenario-local copy of the shared `Planner` agent, vendored so the plugin is
fully self-contained when installed via the Copilot CLI (no dependency on the
`octane-shared` plugin).

### SddCoder

Senior Software Engineer specializing in implementing features from detailed
task specifications and requirements. Enforces "Think Before Coding" (problem
decomposition before implementation) and "Simplicity First" (minimal
abstractions, no premature optimization) guardrails. Defined in
[`agents/Octane.SddCoder.agent.md`](./agents/Octane.SddCoder.agent.md).

## Expected Output

| Workflow Step | Output |
|---------------|--------|
| Requirements | A `.req.md` document with user stories, acceptance criteria, assumptions, and alternative interpretations |
| Plan | A `.prd.md` document with architecture, design decisions, implementation plan (epics/items), and simplicity rationale |
| Implement | Code changes with tests, committed per epic/item, following test-first flow |
| Review | A `.review.md` report validating implementation against requirements with scope-compliance tracking |

## Configuration

These settings are defined in [`config/octane.yaml`](./config/octane.yaml) under
the `spec-driven-development` namespace. Because this scenario is installable at
both workspace and user level, every setting has an inline default that the
planning skills fall back to when the config file is not deployed (user-level
installs).

| Setting | Description | Default |
|---------|-------------|---------|
| `spec-driven-development.artifacts.requirements` | Directory where `octane-planner-requirements` saves generated `.req.md` documents | `docs/projects/` |
| `spec-driven-development.artifacts.prd` | Directory where `octane-planner-plan` saves generated `.prd.md` documents | `docs/projects/` |

## Tips and Best Practices

- **Start with requirements** for ambiguous work — the `ASM-`/`ALT-` surfacing
  catches misunderstandings before they propagate into the plan.
- **Implement one epic at a time** — pass the specific `EPIC-00X` to
  `octane-coder-implement` to keep changes surgical and reviewable.
- **Review against the exact scope** — pass a commit range or `workspace` so
  the traceability matrix maps only the changes you intend.

## Related Scenarios

### Research-First Development

If your work item is complex, ambiguous, or involves multiple stakeholders,
consider using **Research-First Development** before SDD. It gathers context
from ADO, M365, EngHub, and the codebase to ensure you fully understand the
problem before writing specs.

| Scenario | Best For |
|----------|----------|
| **Spec-Driven Development** | Clear requirements, well-scoped features |
| **Research-First Development** | Complex/ambiguous work items, stakeholder alignment needed |
| **Both (full-dev-workflow preset)** | End-to-end workflow from ambiguous ticket to merged PR |

**Install both**: `octane install --preset full-dev-workflow`

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version history and migration notes.
The `1.x → 2.0` entry documents the prompt → skill plugin migration.
