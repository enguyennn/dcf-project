---
description: 'Generate documentation using Copilot CLI fleet mode — launches a parallel fleet session for faster full-repo doc generation'
argument-hint: 'Optional: specific subsystem to document (e.g., src/Services/Auth). Omit for full repo.'
model: Claude Opus 4.6 (copilot)
---

# Generate with Fleet

Generate documentation for this repository using the Copilot CLI `/fleet` command for parallel processing.

## Instructions

@instructions/Octane.UserKnowledge.instructions.md
@instructions/Octane.DocQuality.instructions.md
@instructions/Octane.DocTypes.instructions.md
@instructions/Octane.Generate.instructions.md
@instructions/Octane.Diagrams.instructions.md
@instructions/Octane.CodeInDocs.instructions.md
@instructions/Octane.Frontmatter.instructions.md
@instructions/Octane.BluebirdTools.instructions.md

## Inputs

- `Scope` (string, optional): A specific directory or subsystem to document (e.g., `src/Services/Auth`). If omitted, documents the entire repository.

## Prerequisites

Copilot CLI must be installed. Run:
```
copilot --version
```

If not found, tell the user:
> "Copilot CLI is required for fleet mode. Install it from https://aka.ms/copilot-cli
> You can use `/Octane.EngDocs.Generate` instead — it does the same thing without fleet mode."

## Workflow

1. **Check Copilot CLI** — run `copilot --version`. If it fails, stop and suggest `/Octane.EngDocs.Generate`.

2. **Determine scope** — use the user's input or default to full repo.

3. **Run the fleet session** using the `copilot-fleet` skill:

The output directory defaults to `docs/` (configured in `config/octane.yaml` under `eng-docs.output-path`). Read that file if it exists to check for overrides.

```powershell
pwsh skills/copilot-fleet/scripts/Start-FleetSession.ps1 `
  -WorkingDirectory "<repo-root>" `
  -Prompt "/fleet Generate documentation for this repository. Scope: <scope>. Output directory: docs/. @.github/instructions/user-knowledge.instructions.md @.github/instructions/doc-quality.instructions.md @.github/instructions/doc-types.instructions.md @.github/instructions/generate.instructions.md @.github/instructions/diagrams.instructions.md @.github/instructions/code-in-docs.instructions.md @.github/instructions/frontmatter.instructions.md @.github/instructions/bluebird-tools.instructions.md"
```

4. **Report results** — the script launches the fleet session in a new window and returns the PID. Tell the user the session is running, where to find the output when it finishes, and suggest `/Octane.EngDocs.Review` as a next step.

## Rules

- Only generate documentation — never modify source code
- If Copilot CLI is not available, stop and recommend `/Octane.EngDocs.Generate`
