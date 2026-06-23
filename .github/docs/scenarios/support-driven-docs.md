# Support-Driven Docs

**Mine your Teams support channels, meeting transcripts, and email threads to systematically improve customer-facing documentation.**

Stop guessing what your docs are missing — let your customers tell you. This scenario analyzes your team's support channel threads, meeting transcripts (office hours, support syncs, Q&A sessions), **and** support email threads (shared mailboxes, DLs) to find documentation gaps, generate FAQ entries, and improve existing doc pages with real customer-driven content.

## When to Use This

- Your team has a busy Teams support channel with months/years of history
- You run recurring office hours or support meetings where customers ask questions verbally
- You have a shared mailbox or DL that receives support emails from customers or partner teams
- Your customer-facing docs need a refresh but you don't know where to start
- You want to identify the most common customer pain points and address them in docs
- You want to generate a comprehensive FAQ from real support interactions across channels, meetings, and email

## What It Does

1. **Scrapes support threads** — Pulls threads from your Teams support channel in date-range batches, extracting customer questions, team responses, and topic categories
2. **Analyzes meeting transcripts** — Pulls transcripts and Copilot recaps from recurring meetings (office hours, support syncs), extracting questions asked verbally, expert explanations, and action items that indicate doc gaps
3. **Analyzes support emails** — Searches shared mailboxes and DLs for support email threads, extracting formal requests, escalation patterns, detailed reproduction steps, and resolution workarounds
4. **Analyzes your docs repo** — Explores your markdown docs structure to understand what exists, what format you use, and where gaps are
5. **Generates FAQ entries** — Creates or updates a FAQ document based on the most frequently asked real customer questions from all three sources, grouped by topic
6. **Improves existing docs** — Cross-references each doc page against support history from channels, meetings, and emails, adding missing troubleshooting tips, examples, and clarifications

## Why Meetings Matter

Meetings capture support signals that channels miss:

- **Verbal questions never get typed** — Customers ask complex questions in office hours that they wouldn't write in a channel. These are often the hardest problems with the worst doc coverage.
- **Richer expert explanations** — A 5-minute verbal walkthrough contains far more detail than a channel reply. Meeting transcripts capture the full explanation.
- **Recurring patterns across sessions** — When the same question comes up in office hours week after week, that's a documentation gap. Analyzing across meeting occurrences reveals systemic issues.
- **Action items = unresolved gaps** — Meeting action items like "we should document this" often never get done. Extracting them surfaces forgotten doc debt.
- **Copilot recaps provide pre-structured data** — Meeting summaries, topic segments, and action items are already categorized, making analysis faster.

## Why Emails Matter

Emails capture a different class of support signal:

- **Formal problem reports** — Customers who email tend to include detailed reproduction steps, error messages, stack traces, and config snippets that channel messages lack.
- **Escalation depth** — Long email threads (5+ replies) represent the hardest problems. The back-and-forth troubleshooting often contains exactly the content your docs need.
- **External reach** — Partners, customers outside the org, and cross-team engineers who can't access your Teams channel send email instead. These perspectives are invisible to channel-only analysis.
- **Azure SR / IcM threads** — Support cases forwarded to team mailboxes contain structured problem descriptions and resolution steps that make excellent doc content.
- **Complementary signal** — Channels show breadth (how many people hit an issue), meetings show depth (expert walkthroughs), and emails show formality (structured reports and escalation chains).

## Why Stack Overflow Matters

Stack Overflow for Teams captures curated, community-validated knowledge that other sources miss:

- **Verified answers** — Accepted and highly-voted answers represent solutions the community has validated. These are high-confidence content for docs.
- **Structured Q&A format** — Questions and answers are already organized, tagged, and searchable — reducing the effort needed to extract doc-worthy content.
- **Long-tail coverage** — SO captures niche questions that never appear in busy support channels because users self-serve before asking in real-time.
- **Cross-team visibility** — Questions from across the organization surface blind spots that your team's channel alone wouldn't reveal.
- **Link resolution** — When support threads or meeting conversations reference SO links, the agent retrieves full Q&A content via the MCP instead of broken HTML fetches.

## Prerequisites

- **WorkIQ MCP server** — Required for Teams channel access, meeting transcript/recap retrieval, and email search. Ensure it's configured and you have access to the target support channel, meetings, and mailboxes.
- **Stack Overflow for Teams MCP server** — Optional. Required for Stack Overflow analysis. Ensure the `stackoverflow` MCP server is configured and you have access to your organization's Stack Overflow for Teams instance.
- **Meeting transcription** — For meeting analysis, transcription must be enabled on the target meetings. Copilot recaps require Teams Premium or Microsoft 365 Copilot.
- **Shared mailbox access** — For email analysis, you must have permissions to the target shared mailbox or DL (membership or delegated access).
- **Docs repository** — Your documentation must be in markdown format and accessible in the current workspace (or a path you specify).

## Configuration

Edit `config/octane.yaml` in your workspace to configure:

> **⚠️ Required:** You **must** set `channel.name` and `channel.team` before running any workflow. These are team-specific and have no universal default.

```yaml
support-driven-docs:
  channel:
    name: ""           # Teams channel name (e.g., "Cirrus Support")
    team: ""           # Teams team name (e.g., "EngSys")
  meetings:
    names: []          # Meeting names to analyze (e.g., ["Office Hours", "Customer Support Sync"])
    include_transcripts: true    # Analyze full meeting transcripts
    include_recaps: true         # Use Copilot meeting recaps (summaries, action items)
    include_meeting_chat: true   # Include messages from meeting chat threads
  email:
    mailbox: ""        # Shared mailbox or DL (e.g., "team-support@microsoft.com"). Leave empty to skip.
    keywords: []       # Filter keywords (e.g., ["error", "help", "how to"]). Leave empty for all.
    include_threads: true  # Include full reply chains
  docs:
    path: "docs/"      # Relative path to your docs directory
    faq_path: "docs/faq.md"  # Where to write/update FAQ
  analysis:
    prioritize_human_responses: true   # Deprioritize bot answers
    min_threads: 10                    # Minimum threads before generating recommendations
  stackoverflow:
    tag: ""            # Stack Overflow for Teams tag (e.g., "my-product"). Leave empty to skip.
```

## Workflows

### Full Improvement Cycle (`/Octane.DocImprover.Run`)

1. Configure your Teams channel name, meeting names, email mailbox, and docs path in `config/octane.yaml`
2. Run `/Octane.DocImprover.Run` — optionally provide a date range
3. The agent scrapes your support channel, meeting transcripts, email threads, and Stack Overflow Q&A via WorkIQ and the Stack Overflow MCP
4. It categorizes all data by topic and cross-references against your existing docs
5. FAQ entries are generated for undocumented questions; existing doc pages are enriched
6. A summary report is displayed showing all changes, top pain points, and next steps
7. Review the file changes in your workspace and commit

### Analysis Only (`/Octane.DocImprover.Analyze`)

1. Run `/Octane.DocImprover.Analyze` — no files are modified
2. The agent scrapes channels, meetings, emails, and Stack Overflow Q&A, categorizes data, and analyzes your docs
3. A gap analysis report is displayed: top pain points, source-specific findings, documentation gaps
4. Use the report to prioritize manual doc improvements or run the full workflow next

### FAQ Generation (`/Octane.DocImprover.GenerateFAQ`)

1. Run `/Octane.DocImprover.GenerateFAQ`
2. The agent scrapes channels, meetings, emails, and Stack Overflow Q&A, identifies the most common questions
3. A FAQ file is created or updated at the configured path with new entries grouped by topic
4. Existing FAQ entries are preserved — only new questions are added

## Sample Prompts

```shell
# Full workflow: scrape channel + meetings + emails → analyze docs → generate FAQ + improvements
/Octane.DocImprover.Run

# Analyze support threads, meeting transcripts, and emails (generates a report without modifying docs)
/Octane.DocImprover.Analyze

# Generate/update FAQ from previously analyzed threads, meetings, and emails
/Octane.DocImprover.GenerateFAQ
```

## Expected Output

| Workflow | What It Produces |
|----------|-----------------|
| `/Octane.DocImprover.Run` | Modifies doc files in your workspace (FAQ entries + doc page improvements) and displays a summary report in chat with pain points, changes made, and next steps |
| `/Octane.DocImprover.Analyze` | Read-only gap analysis report displayed in chat — no files are modified. Shows top pain points, source-specific findings, and recommended actions |
| `/Octane.DocImprover.GenerateFAQ` | Creates or updates the FAQ file at the configured path. Displays a summary of entries added and sections updated |

## Example Results

From the original experiment on the Cirrus team:
- **300+ support threads analyzed** spanning 4+ years
- **~30 new FAQ entries** added across 7 sections
- **22 existing doc pages improved** with 853 lines of real customer-driven content
- All based on what customers actually ask about, not what the team assumed

## Tips

- **Prioritize human responses** over auto-bot answers for doc content — real team expertise is more valuable
- **Categorize threads by topic** to find patterns — you may discover surprising gaps (auth/MSI was Cirrus's #1 gap)
- **Run in batches** for large channels — analyze 3-6 month windows at a time for manageable PR sizes
- **Enable transcription on recurring meetings** — office hours without transcription can't be analyzed
- **Meeting recaps accelerate analysis** — Copilot recaps provide pre-categorized topics and action items, reducing analysis time significantly
- Support history from years ago often surfaces issues customers still hit today
- **Combine all sources** — channel threads show breadth (how many people hit an issue), meetings show depth (detailed expert walkthroughs), emails show formality (structured reports and escalation chains), and Stack Overflow shows curated knowledge (community-validated answers)
