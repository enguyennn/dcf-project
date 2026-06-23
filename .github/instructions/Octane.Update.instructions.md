---
description: 'Principles for incremental documentation updates — triage rules, surgical edits, drift-closing mindset.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# Update Phase Principles

Guidelines for making targeted edits to existing documentation. Updates are surgical — change the minimum text needed to keep docs accurate and useful.

## Mindset

- **Targeted, not sweeping.** Change one section, add one insight, fix one inaccuracy.
- **Preserve existing structure.** Don't reorganize a doc when adding a gotcha.
- **Format consistently.** Match the existing section style — bullet format, emoji conventions, table rows.

## Update Types

| Type | Target Section | Example |
|------|---------------|---------|
| `insight` | Key Insights | Performance characteristic, edge case |
| `decision` | Design Decisions | Why JWT over session cookies |
| `gotcha` | Gotchas / Warnings | Redis connections timeout silently after 30s |
| `scenario` | Common Scenarios | New use case walkthrough |
| `troubleshooting` | Troubleshooting | Solution to a common problem |
| `performance` | Performance | Load test findings |
| `production` | Production Learnings | Incident postmortem insight |

## Rules

1. **Never regenerate entire document** — only modify the target section
2. **Preserve formatting** — match existing style and conventions
3. **Ask for details** — if an update needs more context (like decision rationale), ask
4. **Confirm changes** — report what was added and where
