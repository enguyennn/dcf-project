---
name: doc-scaffold
description: >
  Create documentation directory structure with starter files.
  Use when setting up a new documentation site for a repository.
  Activated by /Octane.EngDocs.Setup or when the orchestrator detects no docs directory.
compatibility: Requires PowerShell 7+. Windows or Linux.
metadata:
  author: Azure Build Health
  version: "1.0"
---

# Doc Scaffold Skill

Creates the directory structure and starter files for a documentation site.

## When to Use

- Setting up documentation for a new or existing repository
- The `doc-scaffold` was explicitly requested via `/Octane.EngDocs.Setup`
- The orchestrator detected no docs directory exists

## What It Creates

```
<output_path>/
├── index.md                # Landing page
├── toc.yml                 # Root navigation
├── .gitignore              # Excludes _site/, obj/
├── tutorials/
│   └── toc.yml
├── how-to-guides/
│   └── toc.yml
├── reference/
│   └── toc.yml
├── explanation/
│   └── toc.yml
└── assets/
    └── images/             # Media files
```

## What It Does NOT Create

- `docfx.json` — use the `docfx-config` skill separately
- Build scripts — use the `build-pipeline` skill separately
- Prompts, instructions, agents — these ship with the Octane scenario
- Any documentation content — use `/Octane.EngDocs.Generate` or `/Octane.EngDocs.Write`

## Usage

```powershell
pwsh scripts/Scaffold-Docs.ps1 `
  -TargetRepo "C:/repos/my-service" `
  -OutputPath "docs"
```

Parameters:
- `-TargetRepo`: Root of the target repository
- `-OutputPath`: Documentation directory name (default: `docs`)

## Behavior

- **Idempotent** — skips existing files/directories, creates only what's missing
- **Preserves existing content** — never overwrites existing files
- **Reports what was created** — lists every new file for user awareness

## Starter Content

### `index.md`
```markdown
---
title: "Documentation"
---

# Documentation

Welcome to the documentation site. Use the navigation to explore.
```

### `toc.yml` (root)
```yaml
- name: Overview
  href: index.md
- name: Tutorials
  href: tutorials/
- name: How-to Guides
  href: how-to-guides/
- name: Reference
  href: reference/
- name: Explanation
  href: explanation/
```

### `.gitignore`
```
_site/
obj/
```
