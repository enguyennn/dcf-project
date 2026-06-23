---
description: 'Principles for syncing organizational knowledge into documentation — certainty-first, verification-heavy.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# KnowledgeSync Principles

Guidelines for syncing organizational knowledge into existing docs — context that cannot be derived from source code alone.

## Core Mindset

- **Certainty above all.** One verified enrichment is worth more than ten plausible ones.
- **Context, not content.** The documentation already exists. Sharpen it with org knowledge — don't rewrite, restructure, or expand scope.
- **External data is guilty until proven innocent.** Wiki pages may be stale. Work items may be rough notes. Every piece of external data must survive scrutiny before it enters documentation.

## The Certainty Spectrum

### High Confidence — Safe to Use

- Acronym expansions confirmed by multiple sources
- Official tool/platform names documented in Engineering Hub
- Repository metadata from ADO tools (project name, branch, URL)
- Team/area path ownership from work item area paths
- Cross-references to official documentation (verified to exist)

### Medium Confidence — Use with Caution

- Wiki content (check when last updated; >12 months needs corroboration)
- Synthesized answers from chat tools (verify against cited sources)
- Work item descriptions (often rough task notes)
- Terminology from a single source

### Low Confidence — Do Not Use

- Version-specific information from external sources
- Performance claims or SLAs from wikis
- Architecture descriptions from other teams' wikis
- Inferred relationships based on naming similarity
- Anything from deactivated or archived sources

## Enrichment Categories

1. **Terminology & Glossary** — expand acronyms, align with org standards (2+ independent sources required)
2. **Platform Context** — identify platform dependencies, add Engineering Hub links (verify URLs exist)
3. **Cross-References** — link to related repos, services, APIs (verify targets are maintained)
4. **Ownership** — add team contacts, area paths, CODEOWNERS references

## Interview Mode

After automated knowledge discovery (or if no MCP tools are available), offer to interview the user for tribal knowledge. Ask questions **one at a time** — wait for a response before the next question. See the KnowledgeSync prompt for the full question bank.

## Rules

- Every enrichment must cite its source
- If a wiki says one thing and code says another, the code wins
- Track all enrichments (applied and rejected) with rationale
