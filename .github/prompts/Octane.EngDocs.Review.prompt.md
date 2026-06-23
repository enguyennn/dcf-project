---
description: 'Review documentation for accuracy — audits claims against source code, fixes errors'
argument-hint: 'Optional: specific file to review (e.g., architecture.md). Omit to review all docs.'
model: Claude Opus 4.6 (copilot)
---

# Review Documentation

Audit documentation for factual accuracy. Verify every claim against source code, fix errors, and flag anything that needs human judgment.

## Instructions

@instructions/Octane.UserKnowledge.instructions.md
@instructions/Octane.DocQuality.instructions.md
@instructions/Octane.Review.instructions.md
@instructions/Octane.BluebirdTools.instructions.md

## Inputs

- `Target` (string, optional): A specific file to review. If omitted, review all docs in `${config:eng-docs.output-path}` (default: `docs/`).

## Workflow

Present the following steps as **trackable todos**:

1. **Inventory docs**
   - If `Target` is specified, review that one file
   - Otherwise, list all `.md` files in `${config:eng-docs.output-path}` (default: `docs/`) (excluding `.meta/`)
   - Track status per page: unreviewed → needs_fixes / verified / flagged

2. **Verify each page against source code**
   For each page:
   - Check that named classes, methods, interfaces exist
   - Verify behavioral descriptions match the code
   - Confirm file/directory references are real
   - Test that relative links resolve
   - Flag any hallucinated content

3. **Fix issues in place**
   - Correct inaccurate statements
   - Remove fabricated content
   - Fix broken links
   - After fixing inaccuracies, make high-impact quality improvements where obvious (restructure mixed-purpose pages, deepen shallow sections, cut filler)

4. **Report results**
   ```
   ## Review Summary
   - Pages reviewed: N
   - Issues found and fixed: N
   - Pages flagged for human review: N
   ```

## Rules

- **Accuracy first.** Don't improve a page that has hallucinated content — fix correctness before anything else.
- **Code is ground truth.** When docs and code disagree, fix the docs.
