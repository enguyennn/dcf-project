---
description: 'YAML frontmatter schema for documentation files — required fields per document type.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# Frontmatter Standards

All documentation files SHOULD include YAML frontmatter. This enables tooling, search, and governance.

## Required Fields

```yaml
---
title: "Document Title"
author: "Author Name"
date: "YYYY-MM-DD"
status: "draft|review|approved|deprecated"
type: "tutorial|how-to-guide|reference|explanation"
---
```

## Optional Fields

```yaml
---
domain: "authentication|deployment|api|architecture|etc"
audience: "beginner|intermediate|advanced"
prerequisites: ["Item 1", "Item 2"]
tags: ["tag1", "tag2"]
version: "1.0"
---
```

## Rules

- `title` must match the document's H1 heading
- `date` uses ISO 8601 format: `YYYY-MM-DD`
- `type` determines which documentation type rules apply
- `status: draft` for AI-generated docs pending review
- `prerequisites` is recommended for tutorials and how-to guides
- Only use ONE H1 heading in the document body (the title)

## When NOT to Add Frontmatter

- Existing docs that don't use frontmatter — don't retrofit unless explicitly requested
- `README.md` files that serve as navigation indexes
- Files in `.meta/` or other tooling directories
