---
description: 'Generate comprehensive baseline documentation for a repository or subsystem'
argument-hint: 'Optional: specific subsystem to document (e.g., src/Services/Auth). Omit for full repo.'
model: Claude Opus 4.6 (copilot)
---

# Generate Baseline Documentation

Create comprehensive documentation for this repository from scratch. A new engineer should be able to understand the system — what it does, how it's built, how components interact — without reading source code.

## Instructions

@instructions/Octane.UserKnowledge.instructions.md
@instructions/Octane.DocQuality.instructions.md
@instructions/Octane.DocTypes.instructions.md
@instructions/Octane.Generate.instructions.md
@instructions/Octane.Frontmatter.instructions.md
@instructions/Octane.Diagrams.instructions.md
@instructions/Octane.CodeInDocs.instructions.md
@instructions/Octane.BluebirdTools.instructions.md

## Inputs

- `Scope` (string, optional): A specific directory or subsystem to document. If omitted, document the entire repository.

## Workflow

Present the following steps as **trackable todos**:

1. **Discover Repository Structure**
   Explore the repo thoroughly: entry points, existing READMEs, config files, directory structure, build files.
   Identify subsystem boundaries (services, libraries, components).

2. **Check for Existing Docs**
   - If `${config:eng-docs.output-path}` (default: `docs/`) has existing docs, read them to understand current state
   - Preserve hand-written docs — fill gaps, don't overwrite
   - If no docs exist, generate everything from scratch

3. **Generate Documentation**
   Follow the strategy and structure in `generate.instructions.md`:
   - Document each subsystem, then create cross-cutting docs (overview, architecture, getting-started, glossary)
   - Place docs in the Diátaxis directory layout per `doc-types.instructions.md`
   - Verify all claims against source code

4. **Build Navigation**
   - Create `README.md` as navigable table of contents linking to all docs
   - Use the `toc-manager` skill to generate/update `toc.yml` files

5. **Self-Review**
   Verify per the Definition of Done in `generate.instructions.md`.

6. **Report Results**
   > "Generated documentation for N subsystems at `${config:eng-docs.output-path}` (default: `docs/`).
   > Run `/Octane.EngDocs.Review` to audit for accuracy."

## Output Location

- `${config:eng-docs.output-path}/` (default: `docs/`)

## Rules

- Every claim must be traceable to source code
- No stubs — every file must have substantive content
- Mark unknown sections with `[TODO: needs team input]` rather than guessing
