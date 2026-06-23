---
description: 'Documentation types — the four documentation categories, when to use each, structural rules.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# Documentation Types

Organize documentation into four categories. Each type has a distinct purpose, tone, and structure. A document should know which type it is and stay focused.

## The Four Types

| Type | Purpose | Reader's mode | Tone |
|------|---------|--------------|------|
| **Tutorial** | Learning-oriented lesson | Studying, building confidence | First-person plural: "We will..." |
| **How-to Guide** | Problem-oriented solution | Working, needs to accomplish a goal | Imperative: "To do X, do Y" |
| **Reference** | Information-oriented description | Working, needs a specific fact | Declarative, neutral, factual |
| **Explanation** | Understanding-oriented discussion | Studying, needs to understand why | Explanatory: "The reason for..." |

## Type-Specific Rules

### Tutorials

- Title pattern: "Your First..." or "Getting Started with..."
- Step-by-step with clear, sequential instructions
- Must produce visible results at each major step
- Minimize abstract explanation — link to explanation docs instead
- Focus on concrete actions, not concepts

### How-to Guides

- Title pattern: "How to [specific goal]"
- Focus on a specific goal or problem
- Provide executable, practical steps
- Assume the reader has basic knowledge
- Adapt to real-world complexity and variations

### Reference

- Title pattern: "[Component] Reference"
- Accurate, complete, and current
- Neutral — no explanation or opinion
- Mirror the system structure
- Use consistent formatting: tables, definition lists

### Explanation

- Title pattern: "About [Topic]" or "Understanding [Concept]"
- Provide context, history, rationale, trade-offs
- No step-by-step instructions (link to how-to guides instead)
- Connect ideas and illuminate relationships

## Directory Structure (Recommended)

```
docs/
├── index.md              # Landing page
├── tutorials/            # Learning-oriented
├── how-to-guides/        # Problem-solving
├── reference/            # Technical specs
├── explanation/          # Conceptual
└── assets/images/        # Media files
```

Cross-cutting docs like `overview.md`, `architecture.md`, and `getting-started.md` live at the docs root or under the appropriate Diátaxis category (e.g., `getting-started.md` is a tutorial, `architecture.md` is explanation).

Not every repo needs all directories. Create them as content warrants it.

## Identifying Existing Doc Types

When reviewing or enriching existing docs that don't follow these categories:
- Don't force-restructure. Work with the existing structure.
- When creating *new* docs alongside existing ones, use these categories for the new content.
- If a page mixes types (half tutorial, half reference), note it as an improvement opportunity but don't restructure during review/enrich phases.
