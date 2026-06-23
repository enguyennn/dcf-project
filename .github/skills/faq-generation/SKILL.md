---
name: faq-generation
description: Use when generating or updating a FAQ document based on categorized support thread data
---

# FAQ Generation

Create or update a comprehensive FAQ document from analyzed support threads.

## When to Use

Use this skill after support threads have been analyzed and categorized. It transforms common customer questions into well-structured FAQ entries.

## Mandatory Execution Steps

### Step 1: Read Existing FAQ

If a FAQ file already exists at the configured path:
- Parse all existing questions
- Note the format, heading structure, and style conventions
- Build a list of already-covered topics to avoid duplication

If no FAQ exists, you will create one from scratch.

### Step 2: Identify Top Questions

From the categorized support threads, identify FAQ candidates:
- Questions asked **3 or more times** across different threads
- Questions where the answer involves non-obvious steps
- Questions where the existing docs don't clearly address the issue
- Questions that required a senior team member to answer

### Step 3: Draft FAQ Entries

For each FAQ candidate, write an entry:

```markdown
### [Clear, specific question as a customer would ask it]

[Concise answer — 2-5 sentences max]

[Code example or step-by-step if needed]

> **See also:** [Link to relevant doc page if applicable]
```

**Rules:**
- Write questions in the customer's voice, not internal jargon
- Answers should be self-contained — a reader shouldn't need to click away to solve their problem
- Include code snippets or commands when the resolution involves specific steps
- Keep answers concise — if the answer needs more than a paragraph, link to a dedicated doc page instead

### Step 4: Group by Section

Organize FAQ entries into topic sections matching the support thread categories:

```markdown
## Authentication & Identity
### How do I configure Managed Identity for...?
...

## Setup & Installation
### What are the prerequisites for...?
...
```

Order sections by thread frequency — most common topics first.

### Step 5: Merge with Existing FAQ

If an existing FAQ was found in Step 1:
- Add new sections after existing sections (or merge into matching sections)
- Never remove or modify existing entries
- Add a comment or note at the top indicating the update source:

```markdown
<!-- FAQ entries below generated from support channel analysis ([date range]) -->
```

### Step 6: Validate

Before writing the file:
- Confirm no duplicate questions (same question phrased differently)
- Verify all "See also" links point to real doc pages
- Check that the format matches the existing FAQ style (if one existed)

## Quality Criteria

- Every FAQ entry must trace back to at least one real support thread
- No fabricated questions or hypothetical scenarios
- Answers must reflect the resolution actually provided by team members
