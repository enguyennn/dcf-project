---
description: 'DocFX site conventions — toc.yml rules, docfx.json configuration, build validation, Engineering Hub compatibility.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# DocFX Conventions

## The Golden Rule: Source Paths = Output Paths

The `_site/` output directory structure must mirror the source directory tree exactly. This is critical for Engineering Hub compatibility.

- **NEVER use `content[].src` and `content[].dest`** to remap output paths — this causes 404 errors on Engineering Hub
- **NEVER lowercase or transform directory names** — use exact filesystem casing
- Use direct file globs so paths flow through unchanged

## Table of Contents (`toc.yml`)

### Formatting

- **2-space indentation** (strict requirement)
- Every `.md` file must appear in a `toc.yml`
- Subdirectories referenced with trailing slash: `href: tutorials/`
- Use human-friendly display names, not filenames

### Structure

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

Each subdirectory with `.md` files must have its own `toc.yml`.

### Page Ordering

1. Overview / index first
2. Getting started / tutorials
3. Domain pages (alphabetically or by importance)
4. Glossary last (if present)

## `docfx.json` Template

```json
{
  "build": {
    "content": [
      {
        "files": ["**/*.yml", "**/*.md"],
        "exclude": ["_site/**", ".meta/**", "obj/**"]
      }
    ],
    "resource": [
      {
        "files": ["**/*.png", "**/*.jpg", "**/*.gif", "**/*.svg"],
        "exclude": ["_site/**", ".meta/**", "obj/**"]
      }
    ],
    "dest": "_site",
    "globalMetadata": {
      "_appTitle": "<site-title>",
      "_enableSearch": true,
      "_enableNewTab": true
    },
    "template": ["default"]
  }
}
```

No `src` property — let DocFX default to current directory to preserve source=output path mapping.

## Build Validation

- Run `docfx build` before committing — warnings are errors
- Verify all internal links resolve
- Ensure new files are in appropriate `toc.yml`
- Never commit `_site/` or `obj/` directories

## File Naming

- Use `kebab-case` for all filenames: `api-authentication-design.md`
- Use `.md` extension
- Relative paths only: `[text](../dir/file.md)`
