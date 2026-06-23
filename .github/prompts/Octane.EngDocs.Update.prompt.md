---
description: 'Make targeted updates to existing documentation — add insights, decisions, gotchas, or fix specific sections'
argument-hint: '<doc-name> <update> — e.g., "auth-service add gotcha: JWT tokens not validated on WebSocket reconnect"'
model: Claude Opus 4.6 (copilot)
---

# Update Documentation

Make targeted, surgical edits to an existing documentation page. This is for adding specific knowledge — an insight, a design decision, a gotcha, a troubleshooting tip — not for regenerating or restructuring.

## Instructions

@instructions/Octane.UserKnowledge.instructions.md
@instructions/Octane.DocQuality.instructions.md
@instructions/Octane.Update.instructions.md

## Inputs

- `Name` (string, required): The document to update (filename or component name)
- `Content` (string, optional): What to add — if not provided, ask

If `Name` is not provided, ask: "Which document do you want to update?"

## Workflow

1. **Find the document**
   Search `${config:eng-docs.output-path}` (default: `docs/`) for the specified document.
   - If found, read it
   - If not found, list available docs and ask user to pick
   - If multiple matches, ask user to disambiguate

2. **Determine update type**
   Parse the input or ask: "What type of update? Options: insight, decision, gotcha, scenario, troubleshooting, performance, production"

3. **Identify target section**
   Map the update type to the appropriate section per `update.instructions.md`.

4. **Ask for details if needed**
   If the update content is thin (e.g., a design decision without rationale), ask follow-up questions:
   - "What were the alternatives considered?"
   - "What trade-offs did this involve?"

5. **Apply the update**
   - Add content to the appropriate section
   - Match existing formatting and style
   - Preserve all other sections unchanged

6. **Confirm**
   > "Added [type] to [section] in `[filename]`"

## Rules

- **Never regenerate the entire document** — only modify the target section
- **Preserve formatting** — match existing style
- **Ask for details** — if context is needed, ask rather than guess
