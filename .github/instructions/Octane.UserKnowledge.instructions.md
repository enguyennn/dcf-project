---
description: 'Injects project-specific knowledge from config/octane.yaml into documentation workflows'
applyTo: '**/docs/**/*.md'
---

# User Knowledge

Before generating, writing, updating, or reviewing documentation, check for project-specific knowledge in `config/octane.yaml` under `eng-docs.knowledge`.

## How to apply

1. Read `config/octane.yaml` (if it exists)
2. Look for `eng-docs.knowledge` — a list of strings
3. Treat each entry as a binding constraint that applies to **all** documentation output in this session

If the file doesn't exist or `knowledge` is empty/missing, skip this step silently — do not ask the user about it.

## What goes in knowledge entries

These are project-specific notes the user wants every doc prompt to respect:

- **Terminology**: internal names, acronyms, preferred phrasing
- **Exclusions**: components or directories to skip
- **Conventions**: formatting rules, link patterns, required sections
- **Context**: deployment model, architecture decisions, tech stack details
- **Audience**: who reads these docs, what they already know

## Rules

- Knowledge entries override general documentation conventions (terminology, audience, structure, exclusions) when they conflict
- Knowledge entries do NOT override what the code actually does — if code contradicts a knowledge entry about behavior, trust the code and flag the discrepancy to the user
- Do not echo the knowledge entries back to the user — just apply them
