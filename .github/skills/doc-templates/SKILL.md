---
name: doc-templates
description: >
  Provides starter templates for each documentation type (tutorial,
  how-to guide, reference, explanation). Use when creating a new document
  via /Octane.EngDocs.Write to get the correct structure and frontmatter.
metadata:
  author: Azure Build Health
  version: "1.0"
---

# Documentation Templates Skill

Provides starter file templates for each document type. These templates include the correct YAML frontmatter, section skeleton, and type-specific formatting guidance.

## When to Use

- The `/Octane.EngDocs.Write` prompt is creating a new document and needs a starter structure
- A user asks to create a specific type of documentation

## Available Templates

| Type | Template | Title Pattern |
|------|----------|---------------|
| Tutorial | [tutorial.template.md](assets/tutorial.template.md) | "Your First..." / "Getting Started with..." |
| How-to Guide | [howto.template.md](assets/howto.template.md) | "How to [specific goal]" |
| Reference | [reference.template.md](assets/reference.template.md) | "[Component] Reference" |
| Explanation | [explanation.template.md](assets/explanation.template.md) | "About [Topic]" / "Understanding [Concept]" |
| Overview | [overview.template.md](assets/overview.template.md) | "[Component/System Name]" |

## Usage

Read the template for the requested doc type and use it as the starting structure. Fill in the `__PLACEHOLDERS__` based on user input.

Templates define section order and formatting but contain no real content — content comes from the user and codebase.
