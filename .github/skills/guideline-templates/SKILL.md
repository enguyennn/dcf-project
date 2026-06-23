---
name: guideline-templates
description: Reference templates for authoring guideline skills and violation reports. Use these templates when generating new guideline skill directories or formatting review results.
---

# Guideline Templates Skill

Reference templates for authoring guideline skills and formatting violation reports used by the Gatekeeper pipeline.

- [`guideline.template.md`](references/guideline.template.md) — Template for authoring new guideline skill `SKILL.md` files (includes frontmatter and directory structure)
- [`guideline.report.template.md`](references/guideline.report.template.md) — Template for formatting violation reports

## When to Use

Use this skill when generating new guideline skills via the `Octane.GatekeeperGenerator` agent, when converting existing guideline files via `Octane.GatekeeperConvertOrchestrator`, or when formatting code review violation reports.

## Steps

### 1. Authoring a New Guideline Skill

1. Read [`guideline.template.md`](references/guideline.template.md) to understand the required directory structure, YAML frontmatter fields, and body sections
2. Create a new directory under the skills root with a kebab-case name (e.g., `blocking-call-in-async-method/`)
3. Create a `SKILL.md` file inside with YAML frontmatter: `name` (kebab-case matching directory), `description` (human-readable), and `metadata` containing `type: guideline`, `severity`, `category`, `scope`.
4. Fill in each body section (Detection Instructions, Negative Example, Positive Example) with specific, actionable content. Do NOT include a `# Title` heading or `## Scope` section — the title goes in `description` and scope goes in `metadata.scope`.
5. Optionally add an `## Additional Details` section at the end for impact, remediation, references, or other context.
6. Ensure detection instructions use the exact syntax `**It is not a violation**` and `**It is a violation**`, with non-violation cases listed before violation cases

### 2. Formatting a Violation Report

1. Read [`guideline.report.template.md`](references/guideline.report.template.md) for the required report structure
2. For each violation, populate the Location, Detection, Suggested Fix, and Risk sections with precise file paths, line numbers, and code snippets
3. Include a Summary table at the top with total violation and affected file counts
