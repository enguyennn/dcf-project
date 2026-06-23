---
name: docfx-config
description: >
  Generate or update docfx.json configuration for a documentation site.
  Use when setting up DocFX for Engineering Hub deployment. Handles both
  single-project and multi-project (shared docs repo) layouts.
compatibility: Requires PowerShell 7+. Windows or Linux.
metadata:
  author: Azure Build Health
  version: "1.0"
---

# DocFX Config Skill

Generates `docfx.json`, `build.cmd`, `build_docs.sh`, and `web.config` for DocFX site building.

## When to Use

- After `doc-scaffold` has created the directory structure
- When converting existing markdown docs to a DocFX site
- When updating DocFX config for a new project layout

## Critical Rule: Source Paths = Output Paths

**NEVER use `content[].src` and `content[].dest`** to remap output paths. This causes 404 errors on Engineering Hub. Omit the `src` property entirely — DocFX defaults to current directory and output paths mirror source paths.

## Usage

```powershell
pwsh scripts/Write-DocfxConfig.ps1 `
  -DocsRoot "C:/repos/my-service/docs" `
  -SiteTitle "My Service Documentation"
```

Parameters:
- `-DocsRoot`: Path to the documentation directory
- `-SiteTitle`: Title for the site (default: inferred from directory name)

## What It Creates

| File | Purpose |
|------|---------|
| `docfx.json` | Build configuration |
| `build.cmd` | Windows build script |
| `build_docs.sh` | Linux/CI build script |
| `web.config` | IIS configuration for local serving |

## Behavior

- **Idempotent** — if `docfx.json` exists, updates it rather than replacing
- **Infers title** from README.md H1 heading, repo directory name, or parameter
- **Excludes** `_site/`, `.meta/`, `obj/` directories
