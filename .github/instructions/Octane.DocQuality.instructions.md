---
description: 'Core documentation quality standards — actionability, grounding, durability. Referenced by all documentation agents and prompts.'
applyTo: '**/*.doc.md,**/docs/**/*.md'
---

# Documentation Quality Standards

Every documentation page must meet these quality standards. When an agent-specific instruction conflicts with this file, **this file wins**. For document type classification (tutorial, how-to, reference, explanation), defer to `doc-types.instructions.md`.

## 1. Audience

Documentation exists so a **new engineer can understand the system and start working with it**.

## 2. Actionable by Default

When documenting a component, start with *how a developer interacts with it* — not its internal architecture.

**Passive (avoid):**
> RequestRouter manages incoming HTTP requests. It examines the request path and headers to determine the target service.

**Actionable (prefer):**
> RequestRouter directs incoming HTTP requests to backend services. To add a new route, register a path pattern and target in `RoutingConfig`. For header-based routing, add a `HeaderRule` — see `src/Routing/Rules/` for examples.

What "actionable" means depends on the document type: a tutorial produces a working result, a how-to solves a problem, a reference enables lookup, an explanation builds understanding for future decisions.

## 3. Grounded in Code

Every claim must be traceable to source files, configs, or existing docs. No invented features, no speculative descriptions, no aspirational statements. When docs and code disagree, **code is the source of truth** — fix the docs.

## 4. Right Level of Detail

### Prefer Behavioral Descriptions Over API Listings

Describe *what a component does, why it exists, and how developers work with it* rather than listing method signatures. API details go stale quickly and are high-risk for hallucination.

### Depth Over Breadth

Detailed coverage of important components beats shallow coverage of everything. If a component is minor, a single sentence in a parent page is better than a dedicated stub.

### No Stubs

Every file must have substantive content. If there isn't enough to say, merge it into a parent page.

## 5. Scannable

- Use headers, short paragraphs, and lists
- Bold key terms and commands on first use
- Use `code formatting` for anything the reader would type or look for in code
- Put the most important information first in each section

## 6. Durability — Minimize Maintenance Burden

### No Brittle References

- **No line numbers** — stale on the next commit
- **No standalone file path metadata** — no `**Source:** \`src/Foo.cs\`` lines. Weave directory-level references into prose instead.
- **No local/absolute paths** — use repo-relative paths only
- **Directory-level references are fine** — `src/Services/Prediction/` as navigational aid in prose

### No Brittle Numbers

Avoid hard counts ("35+ pipelines", "13 endpoints"). Use soft language ("dozens of", "several") unless the count adds genuine clarity.

### No Unverifiable Performance Claims

Don't state latency targets, SLAs, or throughput numbers unless they appear explicitly in code or config.
