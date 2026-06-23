---
name: doc-improvement
description: Use when improving existing documentation pages based on support thread analysis. Also contains the improvement report template.
---

# Doc Improvement

Enhance existing documentation pages by cross-referencing them against real customer support threads.

## When to Use

Use this skill after support threads have been analyzed and categorized. It identifies which existing doc pages need improvement and makes targeted additions.

## Mandatory Execution Steps

### Step 1: Map Threads to Doc Pages

For each doc page in the repository:
- Identify which support thread categories relate to it
- Count how many support threads are relevant to the page's topic
- Sort pages by relevance (most related support threads first)

Skip doc pages with zero related support threads — they don't need support-driven updates.

### Step 2: Analyze Each Page

For each relevant doc page (highest thread count first):

1. **Read the full page** — understand its current content, structure, and tone
2. **Identify what's missing** relative to support threads:
   - Common errors or failure modes not mentioned
   - Troubleshooting steps that team members repeatedly provide but aren't documented
   - Prerequisites or configuration steps that customers frequently miss
   - Edge cases or gotchas that cause support threads
3. **Note the page's style** — heading levels, code block format, callout style, link conventions

### Step 3: Draft Improvements

For each doc page, add one or more of these content types as appropriate:

**Troubleshooting section** (if common errors are undocumented):
```markdown
## Troubleshooting

### [Error message or symptom]

**Cause:** [Why this happens]

**Solution:** [Step-by-step fix based on real support resolutions]
```

**Common pitfalls callout** (if customers frequently misconfigure something):
```markdown
> **⚠️ Common Pitfall:** [Brief description of what goes wrong and how to avoid it]
```

**Examples** (if customers struggle with usage):
```markdown
### Example: [Specific use case from support threads]

[Code or configuration example based on the real resolution]
```

**Prerequisites addition** (if customers miss setup steps):
```markdown
> **Prerequisites:** Before proceeding, ensure you have:
> - [Requirement customers frequently miss]
```

### Step 4: Apply Changes

When modifying a doc page:
- **Add to existing sections** where possible (e.g., add a troubleshooting entry to an existing troubleshooting section)
- **Create new sections** only when no appropriate section exists
- **Place new content logically** — troubleshooting at the end, prerequisites at the top, examples near related content
- **Match the exact style** of the existing page — same heading levels, same callout format, same code block language tags
- **Never remove correct existing content** — only add or clarify

### Step 5: Track Changes

For each modified doc page, record:
- File path
- What was added (brief description)
- Which support threads motivated the change (thread count)
- Number of lines added

## References

- [Improvement Report Template](references/improvement-report.md) — Use this template to structure the final summary report

## Quality Criteria

- Every addition must be motivated by real support thread data
- Additions must be factually correct — based on verified team member responses, not assumptions
- Style must be indistinguishable from the existing doc content
- Changes should be minimal and targeted — don't rewrite entire pages
