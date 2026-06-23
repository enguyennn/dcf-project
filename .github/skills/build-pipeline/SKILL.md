---
name: build-pipeline
description: >
  Generate a PR build pipeline YAML file for DocFX documentation validation.
  Use during repo setup to create automated PR checks that build and validate
  documentation on every pull request.
compatibility: Requires PowerShell 7+. Windows or Linux.
metadata:
  author: Azure Build Health
  version: "1.0"
---

# Build Pipeline Skill

Generates a `.pipelines/documentation-pr.yml` file that validates documentation builds on pull requests.

## When to Use

- During `/Octane.EngDocs.Setup` to create CI validation
- When adding PR build checks for documentation

## Usage

```powershell
pwsh scripts/Write-Pipeline.ps1 `
  -TargetRepo "C:/repos/my-service" `
  -DocsPath "docs"
```

Parameters:
- `-TargetRepo`: Root of the target repository
- `-DocsPath`: Relative path to the docs directory (default: `docs`)

## What It Creates

```
.pipelines/
  documentation-pr.yml    # PR trigger, DocFX build, artifact publish
```

## Pipeline Behavior

- Triggers on PRs that modify files in the docs directory
- Installs DocFX
- Runs `docfx build` with warnings-as-errors
- Publishes `_site/` as a build artifact for preview
- Fails the PR if documentation has errors

## Behavior

- **Idempotent** — skips if pipeline file already exists
- **Path-aware** — configures the docs root path based on parameter
