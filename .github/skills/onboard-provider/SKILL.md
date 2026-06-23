---
name: onboard-provider
description: |
  Onboard a new test provider to the Azure Test Platform via AI-guided interview.
  Collects system details, queries, failure patterns, and generates provider toolkit files
  (provider.md, and optionally test type files) that teach @AzureTestEngineer how to work with the new system.
  Use when: onboarding a new test system (flat or typed), adding a new test type to an existing typed provider.
user-invocable: true
---

# Onboard Provider

AI-guided interview that generates toolkit files for a new test provider. The output teaches `@AzureTestEngineer` how to observe and diagnose for the new system (with build, run, and report sections collected for future use).

## Inputs

- `provider_name` (string, optional): Name of the test system being onboarded. Must match `^[a-zA-Z0-9_-]+$` (alphanumeric, hyphens, underscores). If omitted, ask. If the name contains path separators, dots, or special characters, reject it and ask for a valid name.
- `docs` (string, optional): Path to the provider's docs repo, wiki, or doc files. If provided, the AI extracts information from these before asking questions.

## Output Files

1. `skills/azure-test-toolkit/references/{provider}/provider.md` — based on `skills/azure-test-toolkit/references/provider.template.md` (always generated)
2. `skills/azure-test-toolkit/references/{provider}/{test_type}.md` — one per test type, based on `skills/azure-test-toolkit/references/test-type.template.md` (typed providers only)

## Before You Start

1. Read `skills/azure-test-toolkit/references/provider.template.md` — understand every field you need to collect
2. Read `skills/azure-test-toolkit/references/test-type.template.md` — understand every primitive section you need to populate (typed providers only)
3. Read `.config/octane.yaml` — get the current primitives list from `azure-test-platform.primitives`
4. Read `skills/azure-test-toolkit/SKILL.md` — understand the contract (methods, auth, passthrough rules, **platform primitives inheritance**)

## Docs-First Mode

If `docs` input is provided:

1. **Read the provider's docs** — scan the repo/files for:
   - Kusto cluster URLs, database names, table names
   - KQL queries and query patterns
   - Failure modes, error codes, troubleshooting guides
   - Build/launch mechanisms (pipelines, scripts, commands)
   - Authentication methods
   - Portal URLs
   - Test types and modes
   - Any onboarding guides or getting-started docs

2. **Present what you found** — organize by interview topic and say:
   > "I read your docs and extracted the following. Please confirm or correct each section."

3. **Fill gaps** — for anything not found in the docs, ask the provider directly

4. **Continue with the interview flow below** — but skip topics where docs already provided sufficient answers

## Interview Flow

Ask one topic at a time. After each answer, **summarize what you captured in a clear table** so the provider can see exactly what you understood. Don't just say "captured" — show the data.

If docs were provided, pre-fill answers and ask for confirmation instead of asking from scratch.

**Important:** Do NOT ask about developer settings as a separate topic. Settings are DERIVED from the workflow answers (Topics 3-7). At the end, compile the settings table from what was mentioned.

### Topic 0 — Docs (ask first!)

Ask:
- Do you have a docs repo, wiki, or documentation I can scan?
- If yes: provide the path and I'll extract what I can before asking questions

### Topic 1 — Provider Identity

Ask:
- What is the name of the test system?
- One-line description of what it does

### Topic 1.5 — Provider Mode

Ask:
> Does your test system have multiple distinct testing modes (e.g., functional vs. performance vs. stress)?
> Or is it a single unified system where all tests work the same way?

- If multiple modes → **typed provider**. Continue to Topic 2 (Test Types).
- If single mode → **flat provider**. Skip Topic 2 entirely. All primitives will go in provider.md.
  Set `Available Test Types: none` in the NAVIGATION sentinel.

Summarize: "I'll set this up as a {flat|typed} provider."

### Topic 2 — Test Types (typed providers only)

> Skip this topic if provider mode is flat.

Ask:
- What modes of testing does this system support?
- Which is the most common / default?
- Where does the test content (definitions, scripts, configs) live?

### Topic 3 — How does a developer build their code?

Ask naturally — not about config keys:
- Is it an ADO pipeline, a script, a command, or something else?
- What triggers it — PR, manual queue, schedule?
- What parameters does the developer provide?

→ This populates `<!-- PRIMITIVE:Build -->` and derives build-related settings

### Topic 4 — How does a test get launched?

Ask:
- How do developers launch a test? (PowerShell cmdlet, portal, API, MCP tool, ADO extension?)
- What parameters are needed? (subscription, tenant name, template path, schedule name?)
- Is launch separate from build, or implicit?
- What auth is needed to launch? (AME/SAW, Corp, managed identity?)
- What PowerShell module/cmdlets are used? What version is required?
- Does the provider support scheduled/recurring launches? If so, how?
- What is the ADO Pipeline Extension name (if applicable)?

→ This populates `<!-- PRIMITIVE:Run -->` and derives launch-related settings

### Topic 5 — Where are results and how do you check them?

Ask:
- Where are test results stored? (Kusto, REST API, MCP, portal?)
- If Kusto: cluster URL, database, key tables?
- What functions or queries show pass/fail?
- How would the AI find the most recent run if no ID is provided?
- Is there a portal URL?
- How does the developer authenticate to query results?
- What is the execution hierarchy? (e.g., TestPass → RunSet → Run → Action)
- What are the terminal status values?
- Is there an error records system? How are errors categorized?

→ This populates `<!-- PRIMITIVE:Observe -->` and Common Metadata in provider.md

### Topic 6 — When something fails, how do you figure out why?

Ask:
- What's the first thing a developer checks?
- Did the **launch itself** fail vs a **test action** failed — how do you tell the difference?
- What data sources are available for diagnosis?
- What are 3-5 common failure patterns? For each: symptom, root cause, fix
- Are there cascading failures?
- Any environment checks to verify first?
- How does failure handling work? (Stop, Cancel, Continue, Ignore?)
- How are resources cleaned up on failure?
- How does the provider handle permissions/access errors during diagnosis?

→ This populates `<!-- PRIMITIVE:Diagnose -->` with Query Flow, Failure Patterns, Cascade Rules

### Topic 7 — Reporting

Ask:
- Is a standard summary (what passed, what failed, root cause, fix) sufficient?
- Any custom sections needed?

→ This populates `<!-- PRIMITIVE:Report -->`

### Topic 8 — MCP Servers (optional)

Ask:
- Does your team have or plan to have an MCP server?
- If yes: what data does it return?
- Would you prefer MCP for any primitives instead of direct queries?

### Topic 9 — Platform Primitives (typed providers with multiple test types)

Ask (only if the provider is typed and has 2+ test types):
- Which queries/patterns are shared across ALL test types vs. specific to each?
- For shared content: inherit (use as-is) or extend (add test-type additions)?

→ Determines `## Platform Primitives` section and inheritance markers

### Topic 10 — Operational Details

Ask:
- How do developers cancel a running test?
- How does resource cleanup work? What GC policies are available?
- Is there a dashboard or monitoring tool?
- What is the support model? (MS Teams, Stack Overflow, email, ICM?)
- How do developers manage permissions and access?

→ This populates `## Provider Notes` in provider.md

### Compile Settings (after all topics)

Compile the Required Settings and Optional Settings tables by reviewing everything mentioned across Topics 3-10. Categorize each setting by which primitives need it.

## Output Generation

After the interview:

1. **Generate provider.md** — fill in template, set Available Test Types to `none` for flat providers or comma-separated list for typed providers. Add Platform Primitives if shared content identified (typed) or all primitive sentinels (flat). Populate Provider Notes with operational context, verify NAVIGATION sentinel.
2. **(Typed providers only) Generate test type file(s)** — fill in primitives, set inheritance markers, verify all sentinels present, include `**Schema:** 1` header
3. **Show the generated files** — ask: "Review these files. Want to change anything?"
4. **Write to disk** — create `skills/azure-test-toolkit/references/{provider}/` directory and save files
5. **Summarize** — list what was created, remind to run dev-setup, remind to add a row to the Onboarded Providers table in README

## Rules

- Ask one topic at a time — don't overwhelm with all questions at once
- Summarize what you captured after each topic before moving on
- If the provider doesn't know an answer, mark it as `{PENDING}` in the output
- If a topic doesn't apply, skip it
- Never invent KQL queries — use exactly what the provider gives you
- The output must pass the toolkit contract defined in `skills/azure-test-toolkit/SKILL.md`
