This template defines the structure for guideline skill `SKILL.md` files used by the Gatekeeper pipeline. Each guideline skill is a directory containing a `SKILL.md` file.

## Directory Structure

```
{skills-directory}/
  {skill-name}/
    SKILL.md          # Contains YAML frontmatter + guideline content
    references/       # Optional: golden test files, example violations
```

## SKILL.md Template

```markdown
---
name: {kebab-case-directory-name}
description: >
  {Human-readable description of the guideline including what it detects and when to use it. Max 1024 chars.}
metadata:
  type: guideline
  severity: {critical|high|medium|low}
  category: {security|performance|reliability|testing|style|quality}
  scope:
    - "{glob_pattern_1}"
    - "{glob_pattern_2}"
  content_regex:              # optional — narrows matched files by content
    - "{python_re_pattern_1}"
---

## Detection Instructions

[
    Create clear, unambiguous and precise detection instructions that tells an agent how to find the described code pattern in a codebase or code snippet. Feel free to ask the user on details about the guideline so you can craft better detection instructions

    - **MANDATORY**: Use exact syntax format: `**It is not a violation**` and `**It is a violation**`
    - **REQUIRED ORDER**: List all `**It is not a violation**` cases BEFORE `**It is a violation**` cases
    - **SPECIFICITY**: Include exact code patterns, function names, and scenarios
    - **AVOID**: Vague terms like "inappropriate", "bad", "should not" - use specific technical criteria
]

## Negative example
[
    Generate a negative example of a violation using code snippets. Add comments to point the problematic lines and why it is an issue.
]

## Positive example
[
    Generate a positive example of a corrected implementation using code snippets. Explain how this solution solves the violation
]

## Additional Details
[
    Optional extensible section for supplementary information:
    - **Impact**: Describe what is the negative impact the violation can cause if it gets checked in and why it is important to catch it. Connect it to measurable metrics.
    - **Remediation**: Step-by-step instructions for fixing violations.
    - **References**: Links to documentation, standards, or related guidelines.
    - **Notes**: Any other context that helps humans or agents understand this guideline.
]
```

## Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Lowercase kebab-case, must match the parent directory name (e.g., `blocking-call-in-async-method`) |
| `description` | Yes | Human-readable description of the guideline, max 1024 characters. Should describe what the guideline detects and when to use it. |
| `type` | Yes | Must be `guideline` for Gatekeeper to discover it (under `metadata:`) |
| `severity` | Yes | One of: `critical`, `high`, `medium`, `low` (under `metadata:`) |
| `category` | Yes | One of: `security`, `performance`, `reliability`, `testing`, `style`, `quality` (under `metadata:`) |
| `scope` | Yes | Array of glob patterns defining which files this guideline applies to (under `metadata:`) |
| `content_regex` | No | Array of Python `re.search` patterns. When present, only files whose content matches at least one pattern (AND with scope globs) are considered. Omit when glob is sufficient (under `metadata:`). |
