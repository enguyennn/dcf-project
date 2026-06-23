---
name: toc-manager
description: >
  Create or regenerate toc.yml files to ensure all markdown files have
  navigation entries. Use after creating, moving, or deleting documentation
  files. Ensures DocFX navigation stays in sync with content.
compatibility: Requires PowerShell 7+. Windows or Linux.
metadata:
  author: Azure Build Health
  version: "1.0"
---

# TOC Manager Skill

Scans a documentation directory and updates `toc.yml` files to ensure every `.md` file has a navigation entry.

## When to Use

- After `/Octane.EngDocs.Generate` creates new documentation files
- After `/Octane.EngDocs.Write` creates a new document
- After manually adding or removing documentation files
- When DocFX build reports missing navigation entries

## Usage

```powershell
pwsh scripts/Update-Toc.ps1 `
  -DocsRoot "C:/repos/my-service/docs"
```

Parameters:
- `-DocsRoot`: Path to the documentation root directory

## Behavior

- Scans all directories for `.md` files
- Creates `toc.yml` in directories that have `.md` files but no `toc.yml`
- Adds entries for new `.md` files not yet in existing `toc.yml`
- Preserves existing entry order and names
- Uses 2-space indentation (DocFX strict requirement)
- Derives display names from filename or H1 heading
- Places `index.md` first, `glossary.md` last

## Rules

- **Never remove entries** — only add missing ones
- **Preserve existing names** — don't rename entries the user has customized
- **2-space indentation** — strict DocFX requirement
- All `.md` files must appear in a `toc.yml`
- Subdirectories with `.md` files are referenced with trailing slash
