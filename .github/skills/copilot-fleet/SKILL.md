---
name: copilot-fleet
description: >
  Launch a Copilot CLI fleet session to generate documentation.
  Spawns copilot in a new console window with a /fleet prompt.
  Used by the Octane.EngDocs.GenerateWithFleet prompt.
compatibility: Requires Copilot CLI (copilot --version). Windows (PowerShell 7+) or Linux.
metadata:
  author: Azure Build Health
  version: "2.0"

---

# Copilot Fleet Skill

Launch a fleet session via the Copilot CLI for parallel documentation generation.

## Prerequisites

Copilot CLI must be installed and on PATH:
```powershell
copilot --version
```

## Usage

Run the Start-FleetSession script with a working directory and a `/fleet` prompt:

```powershell
pwsh scripts/Start-FleetSession.ps1 `
  -WorkingDirectory "C:/repos/my-service" `
  -Prompt "/fleet Generate docs for this repo. Output to docs/. @.github/instructions/doc-quality.instructions.md @.github/instructions/generate.instructions.md"
```

Parameters:
- `-WorkingDirectory`: The repo root where the session runs
- `-Prompt`: The full `/fleet` prompt including `@` instruction references

The launcher normalizes workspace artifact references such as `@instructions/...` to explicit installed paths such as `@.github/instructions/...` before starting Copilot CLI.

The script spawns `copilot --interactive --allow-all-tools` in a new console window (required for `/fleet` to be processed as a slash command) and returns the process ID. The fleet session runs asynchronously.

## Troubleshooting

See [troubleshooting guide](references/troubleshooting.md) for common issues.
