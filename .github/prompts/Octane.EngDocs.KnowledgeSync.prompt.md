---
description: 'Sync organizational knowledge into documentation — searches enterprise data, then conducts a structured team interview'
argument-hint: 'Optional: specific component to target (e.g., auth-service). Omit to sync knowledge across all docs.'
model: Claude Opus 4.6 (copilot)
---

# Knowledge Sync

Sync organizational knowledge into existing documentation — design rationale, official terminology, platform context, team knowledge, and production learnings that cannot be found in source code.

## Instructions

@instructions/Octane.UserKnowledge.instructions.md
@instructions/Octane.DocQuality.instructions.md
@instructions/Octane.KnowledgeSync.instructions.md
@instructions/Octane.WorksourcesTools.instructions.md
@instructions/Octane.BluebirdTools.instructions.md

## Inputs

- `Target` (string, optional): A specific component or file to target. If omitted, sync knowledge across all docs.

## Workflow

Present the following steps as **trackable todos**:

### Phase 1: Automated Knowledge Discovery

1. **Inventory existing docs**
   Read the documentation to understand current state and identify knowledge gaps:
   - Undefined acronyms or jargon
   - Components mentioned without context
   - Missing "why" behind design decisions
   - No cross-references to related services
   - Areas where tribal knowledge would add the most value

2. **Search organizational knowledge** (if MCP tools available)
   Use WorkIQ, ES Chat, and ADO tools to research:
   - Design reviews and tech specs for components
   - Architecture discussions in Teams/email
   - Official terminology and platform names
   - Team ownership and area paths
   - Related documentation on Engineering Hub

3. **Apply high-confidence findings**
   For each candidate:
   - Classify confidence (high / medium / low per KnowledgeSync principles)
   - Apply only high-confidence findings directly
   - Log all candidates with rationale (applied or deferred)
   - Flag medium-confidence candidates for Phase 2 verification

### Phase 2: Team Knowledge Interview

4. **Transition to interview**
   After automated discovery (or immediately if no MCP tools are available):
   > "I've synced what I could find from organizational data sources.
   > Ready to capture team knowledge? I'll ask targeted questions one at a time
   > to fill in what tools can't find — design rationale, gotchas, and production learnings."

   If medium-confidence candidates were flagged, start by verifying those:
   > "I also found some information I'd like to verify with you before adding it."

5. **Conduct structured interview** (if accepted)
   Ask questions **one at a time**, wait for answers, and adapt follow-ups based on responses. Select from:

   **Design Rationale:**
   - "What was the hardest technical decision here? What were the alternatives?"
   - "If you were starting over, what would you do differently?"
   - "Why was [specific technology/pattern] chosen over alternatives?"

   **Edge Cases & Gotchas:**
   - "What's the most confusing part of this code for new developers?"
   - "Are there any non-obvious behaviors that surprise people?"
   - "What assumptions does this code make that aren't documented?"

   **Production Experience:**
   - "What was the worst bug or incident involving this component?"
   - "What monitoring or alerts did you wish you had earlier?"
   - "What scaling or performance issues have come up?"

   **Dependencies & Integration:**
   - "What happens when [key dependency] fails or is slow?"
   - "Which downstream consumers are most sensitive to changes here?"

   **Technical Debt:**
   - "What would you refactor if you had a week?"
   - "Are there any known risks the team is accepting?"

6. **Synthesize and apply**
   Organize interview responses into the appropriate doc sections:
   - Design Decisions → explanation docs
   - Gotchas / Warnings → how-to guides or inline callouts
   - Production Learnings → reference or explanation docs
   - Performance Characteristics → reference docs

7. **Report**
   > "Knowledge sync complete:
   > - N findings applied from organizational data (M candidates deferred)
   > - N insights captured from interview
   > - Updated files: [list]
   > - Suggested follow-ups: [any medium-confidence items still unverified]"

## Rules

- **Certainty above all.** Never add information you cannot justify with a specific source or team confirmation.
- **Interview is always available.** Even without MCP tools, the interview captures valuable knowledge.
- **Adapt, don't script.** Use the question bank as a starting point — follow up on what the interviewee says, don't just run through the list mechanically.
