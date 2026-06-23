---
description: 'Principles for generating documentation from scratch — subsystem discovery, parallel generation, synthesis.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# Generate Phase Principles

Guidelines for creating comprehensive documentation for a repository from scratch.

## Strategy

- **Explore before writing.** Spend time understanding the repo: entry points, existing READMEs, config files, directory structure.
- **Scope by natural boundaries.** Use the repo's own directory structure (services, libraries, components) to define subsystems.
- **Adapt to the repo.** The structure below is a starting point, not a mandate. Skip what doesn't apply, add what's unique.
- **Depth over breadth.** Detailed docs for the most important components beat shallow coverage of everything.
- **Preserve existing docs.** If hand-written documentation already exists, don't overwrite it — fill gaps around it.
- **Review your own output.** After generation, verify files have real content, links resolve, and nothing major is missing.

## Subsystem Documentation

Each major subsystem gets its own section or directory under `${config:eng-docs.output-path}`:
- `README.md` — purpose, key components, usage, dependencies
- Additional pages for complex components as needed

## Cross-Cutting Synthesis

After all subsystems are documented, create:
- **README.md** — navigable table of contents linking to everything
- **overview.md** — whole-system purpose, team, repo structure, tech stack (explanation type)
- **architecture.md** — how subsystems connect, include Mermaid diagrams if configured (explanation type)
- **getting-started.md** — prerequisites, build, test, IDE setup (tutorial type)
- **glossary.md** — domain terms and acronyms (reference type)

## Documentation Structure

Generated docs should use the Diátaxis directory layout when it exists (see `doc-types.instructions.md`):

```
<docs-dir>/
├── README.md              # Navigation index
├── overview.md            # Purpose, team, structure, tech stack
├── architecture.md        # System architecture, data flow
├── getting-started.md     # Prerequisites, build, test, IDE setup
├── glossary.md            # Domain terms and acronyms
│
├── tutorials/             # Learning-oriented
├── how-to-guides/         # Problem-solving
├── reference/             # Technical specs
└── explanation/           # Conceptual
```

Create subsystem subdirectories under `reference/` or `explanation/` when a repo has many components — not as top-level peers to the Diátaxis categories.

## Definition of Done

- Every identified subsystem has documentation
- Cross-cutting docs reflect the full system
- `README.md` exists as a navigable index
- A new engineer can answer: what does this do, how do I build it, how do I contribute
- Every doc is grounded in actual code
- All cross-references use working relative links
