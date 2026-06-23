# Engineering Docs Scenario

**Full documentation lifecycle for any codebase — scaffold, generate, write, review, sync knowledge, and maintain.**

## Overview

The Engineering Docs scenario provides AI-assisted workflows for the complete documentation lifecycle. Whether you're starting from scratch, documenting an existing codebase, or maintaining living documentation, this scenario has a workflow for you.

**Key Features:**
- **Scaffold** — Set up DocFX site infrastructure with structured directory layout
- **Generate** — Create comprehensive baseline docs from code analysis
- **Write** — Hand-craft individual docs interactively (tutorial, how-to, reference, explanation)
- **Review** — Audit docs for accuracy against source code and improve quality
- **KnowledgeSync** — Sync organizational knowledge from enterprise data sources + structured team interviews
- **Update** — Make surgical edits to existing documentation

## When to Use

- **New repo** — scaffold a docs site, then generate or hand-write content
- **Existing repo, no docs** — generate baseline documentation from code
- **Existing repo, stale docs** — review for accuracy, sync team knowledge
- **Knowledge capture** — sync team knowledge into docs before rotations
- **Ongoing maintenance** — update docs when code changes

## Quick Start

```shell
# 1. Install the scenario
octane install --scenario eng-docs

# 2. Scaffold a documentation site
/Octane.EngDocs.Setup

# 3. Generate baseline docs from code
/Octane.EngDocs.Generate

# 4. Review for accuracy
/Octane.EngDocs.Review

# 5. Hand-craft a specific doc
/Octane.EngDocs.Write howto How to configure authentication
```

## Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `/Octane.EngDocs.Setup` | Scaffold docs site (dirs, DocFX, pipeline) | `/Octane.EngDocs.Setup` |
| `/Octane.EngDocs.Generate` | Generate baseline docs from code | `/Octane.EngDocs.Generate` or `/Octane.EngDocs.Generate src/Services/Auth` |
| `/Octane.EngDocs.Write` | Write a single doc interactively | `/Octane.EngDocs.Write howto How to deploy` |
| `/Octane.EngDocs.Review` | Audit accuracy + improve quality | `/Octane.EngDocs.Review` or `/Octane.EngDocs.Review architecture.md` |
| `/Octane.EngDocs.KnowledgeSync` | Sync org knowledge + team interviews | `/Octane.EngDocs.KnowledgeSync` or `/Octane.EngDocs.KnowledgeSync auth-service` |
| `/Octane.EngDocs.Update` | Surgical edit to existing doc | `/Octane.EngDocs.Update auth-service add gotcha: tokens expire silently` |
| `/Octane.EngDocs.GenerateWithFleet` | Generate docs via Copilot CLI fleet mode | `/Octane.EngDocs.GenerateWithFleet` or `/Octane.EngDocs.GenerateWithFleet src/Services/Auth` |

## Workflows

### 1. New Repository — Full Setup

```shell
/Octane.EngDocs.Setup                    # Create site infrastructure
/Octane.EngDocs.Generate                 # Generate docs from code
/Octane.EngDocs.Review                   # Audit for accuracy
```

### 2. Write Specific Documentation

```shell
/Octane.EngDocs.Write tutorial Getting started with the API
/Octane.EngDocs.Write explanation About the caching architecture
/Octane.EngDocs.Write reference Configuration reference
/Octane.EngDocs.Write howto How to add a new data pipeline
```

Each `Write` session is iterative — the AI asks one question at a time and builds the doc section by section.

### 3. Review Existing Documentation

```shell
# Review all docs
/Octane.EngDocs.Review

# Review a specific file
/Octane.EngDocs.Review architecture.md
```

Review combines accuracy audit (are claims true?) with quality refinement (is it useful?).

### 4. Sync Team Knowledge

```shell
/Octane.EngDocs.KnowledgeSync
```

KnowledgeSync has two phases:
1. **Automated discovery** — searches WorkIQ, ES Chat, and ADO for design docs, team discussions, and official terminology
2. **Team interview** — asks you targeted questions to capture tribal knowledge (design rationale, gotchas, production learnings)

### 5. Fleet Mode (Advanced)

For full-repo parallel documentation using the Copilot CLI:

```shell
/Octane.EngDocs.GenerateWithFleet
/Octane.EngDocs.GenerateWithFleet src/Services/Auth
```

This launches a Copilot CLI fleet session for faster parallel doc generation. Requires Copilot CLI installed.

## Document Types

This scenario organizes documentation into four categories, inspired by the [Diátaxis framework](https://diataxis.fr/):

| Type | Purpose | Title Pattern | Example |
|------|---------|---------------|---------|
| **Tutorial** | Learning-oriented lesson | "Your First..." | "Getting Started with the SDK" |
| **How-to Guide** | Problem-solving instructions | "How to..." | "How to Configure Authentication" |
| **Reference** | Technical specification | "[Component] Reference" | "API Configuration Reference" |
| **Explanation** | Conceptual understanding | "About..." | "About the Caching Architecture" |

Not every repo needs all four categories. Create them as content warrants it.

## Prerequisites

### Required

- **VS Code** with GitHub Copilot
- **Octane** CLI or extension installed

### Optional (enhances experience)

| Prerequisite | Required For | Without It |
|-------------|-------------|------------|
| **Code Search MCP** (Bluebird) | Faster code discovery in Generate, Review | Falls back to workspace search |
| **WorkIQ MCP** | Automated knowledge discovery from SharePoint, Teams, email | KnowledgeSync uses interview only |
| **MS Learn MCP** | Official Microsoft doc references | Works without references |
| **Copilot CLI** | `/Octane.EngDocs.GenerateWithFleet` parallel generation | Use `/Octane.EngDocs.Generate` instead |

## Configuration

Configure in `config/octane.yaml` after installation:

```yaml
eng-docs:
  output-path: ./docs/           # Where docs are created
  site-engine: docfx             # "docfx" or "none" (plain markdown)
  include-diagrams: true         # Include Mermaid diagrams
  diagram-syntax: azure-devops   # "azure-devops" or "github"

  # Project-specific knowledge injected into every doc prompt
  knowledge:
    - "We call our API gateway 'Frontdoor' internally"
    - "Skip documentation for test fixtures and mock utilities"
    - "Deployments use EV2 — always link to the EV2 runbook"
```

Knowledge entries work like `copilot-instructions.md` but scoped to documentation. Every Generate, Write, Update, Review, and KnowledgeSync prompt reads them and applies them as context. Add terminology, exclusions, conventions, or architectural context that should color all generated docs.

## Skills

| Skill | Purpose |
|-------|---------|
| `copilot-fleet` | Launch/manage fleet sessions via Copilot CLI |
| `doc-scaffold` | Create documentation directory structure |
| `docfx-config` | Generate DocFX configuration files |
| `toc-manager` | Create/update toc.yml navigation files |
| `build-pipeline` | Generate PR build pipeline for DocFX |
| `doc-quality-eval` | Evaluate documentation quality (structured report) |
| `doc-templates` | Starter templates per document type |

## Quality Standards

All documentation produced by this scenario follows these principles:

1. **Actionable** — readers can *do* something after reading, not just *know* something
2. **Grounded in code** — every claim traceable to source files
3. **Durable** — no brittle references (line numbers, absolute paths, hard counts)
4. **Scannable** — headers, short paragraphs, bold key terms, code formatting
5. **Right level of detail** — behavioral descriptions over API listings, depth over breadth

## Related Scenarios

- [Living Documentation](../living-documentation/README.md) — the predecessor to this scenario (single-component doc creation). **eng-docs supersedes living-documentation** with expanded coverage across the full documentation lifecycle. If you're using living-documentation, consider migrating to eng-docs for broader workflow support.
- [Doc Reviewer](../doc-reviewer/README.md) — multi-agent document review via Conductor
- [Repository Overview](../repository-overview/README.md) — high-level repo summary for context hydration

