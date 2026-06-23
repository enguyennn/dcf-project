---
description: 'Write a single document interactively — tutorial, how-to, reference, or explanation'
argument-hint: '<type> <topic> — e.g., "howto How to configure authentication" or "explanation About the caching layer"'
model: Claude Opus 4.6 (copilot)
---

# Write a Document

Create a single documentation page interactively, building it section by section based on your input.

## Instructions

@instructions/Octane.UserKnowledge.instructions.md
@instructions/Octane.DocQuality.instructions.md
@instructions/Octane.DocTypes.instructions.md
@instructions/Octane.Frontmatter.instructions.md
@instructions/Octane.Diagrams.instructions.md
@instructions/Octane.CodeInDocs.instructions.md

## Inputs

- `Type` (string, optional): One of `tutorial`, `howto`, `reference`, `explanation`. If not provided, ask.
- `Topic` (string, optional): What the document is about. If not provided, ask.

## Type Detection

Parse the input for type:
- "tutorial" or "getting started" → `tutorial`
- "howto" or "how to" or "how-to" → `howto`
- "reference" or "ref" → `reference`
- "explanation" or "about" or "understanding" or "overview" → `explanation`

If ambiguous, ask: "What type of document? Options: tutorial, howto, reference, explanation"

## Workflow

1. **Initialize**
   - Determine type and topic from input (or ask)
   - Create the file with YAML frontmatter (per frontmatter instructions) and title
   - Use the `doc-templates` skill to get the starter structure for this type
   - Place the file at the appropriate location (`${config:eng-docs.output-path}` defaults to `docs/`):
     - `tutorial` → `${config:eng-docs.output-path}/tutorials/<topic-slug>.md`
     - `howto` → `${config:eng-docs.output-path}/how-to-guides/<topic-slug>.md`
     - `reference` → `${config:eng-docs.output-path}/reference/<topic-slug>.md`
     - `explanation` → `${config:eng-docs.output-path}/explanation/<topic-slug>.md`

2. **Iterative Q&A Loop**
   - Ask **one specific question** to gather content for the next section
   - Wait for the user's response
   - Update the file with the new content, formatted correctly for the doc type
   - Repeat until the document is complete

3. **Finalize**
   - Use the `toc-manager` skill to register the new file in `toc.yml`
   - Report the file path and suggest review

## Type-Specific Questions

### Tutorial
1. "What skill will this tutorial teach?"
2. "What are the prerequisites?"
3. "What is the first step?"
4. "What should the user see after this step?"
5. (repeat for each step)

### How-to Guide
1. "What specific problem does this guide solve?"
2. "What are the prerequisites?"
3. "What is the first action?" / "What is the next action?"
4. (repeat until complete)

### Reference
1. "What system or component does this reference describe?"
2. "What is the syntax or API surface?"
3. "What are the parameters/options?"
4. "Are there return values or outputs?"

### Explanation
1. "What concept needs explaining?"
2. "What is the background or history?"
3. "Why was this design chosen? What were the alternatives?"
4. "What are the trade-offs?"

## Rules

- **Do NOT generate the entire document at once.** Build section by section based on user input.
- Keep the file valid and buildable at all times.
- Match the tone rules for the selected document type.
