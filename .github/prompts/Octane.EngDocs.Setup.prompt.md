---
description: 'Scaffold a repository for documentation — creates directory structure, DocFX config, build pipeline'
model: Claude Opus 4.6 (copilot)
---

# Scaffold Documentation Site

Set up the documentation infrastructure for this repository. This creates the site structure, build configuration, and CI pipeline — not the documentation content itself.

## Instructions

@instructions/Octane.DocTypes.instructions.md
@instructions/Octane.Docfx.instructions.md

## Inputs

No explicit inputs. Configuration is read from `config/octane.yaml`.

## Workflow

1. **Determine the docs directory**
   The default is `docs/` (configured in `config/octane.yaml` under `eng-docs.output-path`). Read that file if it exists. Ask the user to confirm or override.

2. **Check for existing docs**
   - If the docs directory already exists, report what's there and offer to add only missing infrastructure
   - If existing `.md` files are found, preserve them — scaffold around them

3. **Create directory structure**
   Run the `doc-scaffold` skill:

   ```powershell
   pwsh skills/doc-scaffold/scripts/Scaffold-Docs.ps1 `
     -TargetRepo "<repo-root>" `
     -OutputPath "docs"
   ```

   This creates `tutorials/`, `how-to-guides/`, `reference/`, `explanation/`, `toc.yml`, `index.md`, and `.gitignore`.

4. **Check site engine preference**
   Read `${config:eng-docs.site-engine}` (default: `docfx`) from config. If `docfx`, continue to steps 5–6. If `none`, skip to step 7.

5. **Create DocFX configuration** (if `site_engine: docfx`)
   Run the `docfx-config` skill:

   ```powershell
   pwsh skills/docfx-config/scripts/Write-DocfxConfig.ps1 `
     -DocsRoot "<repo-root>/docs"
   ```

   This creates `docfx.json` and build scripts (`build.cmd`, `build_docs.sh`).

6. **Create build pipeline** (if `site_engine: docfx`)
   Run the `build-pipeline` skill:

   ```powershell
   pwsh skills/build-pipeline/scripts/Write-Pipeline.ps1 `
     -TargetRepo "<repo-root>" `
     -DocsPath "docs"
   ```

   This creates `.pipelines/documentation-pr.yml` that validates docs on PRs.

7. **Report what was created**
   List all files created. Suggest next steps:
   > "Documentation site scaffolded. Next steps:
   > - Run `/Octane.EngDocs.Generate` to create baseline documentation from code
   > - Run `/Octane.EngDocs.Write tutorial Getting started` to hand-craft your first doc
   > - Commit the new files and set up the PR pipeline"

## Rules

- **Idempotent** — safe to run multiple times. All scripts skip existing files.
- **No content generation** — this creates infrastructure, not documentation. Use other commands for content.
- **Respect existing structure** — if docs already exist in a different layout, create the standard dirs alongside, don't reorganize.
