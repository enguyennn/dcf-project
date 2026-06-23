---
name: email-thread-analysis
description: Use when extracting and analyzing support emails from shared mailboxes or distribution lists via WorkIQ
---

# Email Thread Analysis

Extract customer questions, escalation patterns, and resolution steps from support email threads in shared mailboxes or distribution lists.

## When to Use

Use this skill when the team receives support requests via email (shared mailboxes, DLs, or forwarded support cases). Emails capture formal support requests, escalation threads, and cross-team questions that may not appear in Teams channels or meetings.

## What Emails Add

- **Formal support requests** — customers who email instead of posting in Teams, often with detailed reproduction steps
- **Escalation threads** — complex issues with long back-and-forth that contain deep troubleshooting detail
- **Azure SR / IcM threads** — support cases forwarded to the team mailbox with structured problem descriptions
- **Cross-team questions** — engineers from other teams asking via email rather than joining a channel
- **External partner questions** — partners or customers outside the org who can't access Teams channels

## Important Constraints

- WorkIQ can only access mailboxes the current user has permissions for (shared mailbox membership or delegated access)
- Emails are queried at a point in time — no real-time monitoring
- Deleted or purged emails are not accessible
- DLP and sensitivity labels are respected

## Mandatory Execution Steps

### Step 1: Query the Mailbox

Use WorkIQ to search the configured shared mailbox or DL for support-related emails:

```
"Search emails in [mailbox] from [date range].
Filter for emails containing: [keywords if configured].
For each email thread, give me:
1. Subject line
2. Original sender (customer vs. internal)
3. Full email body of the initial request
4. All replies in the thread
5. Whether the thread was resolved"
```

If keywords are configured (`${config:support-driven-docs.email.keywords}`), use them to filter. Otherwise, retrieve all emails in the mailbox.

**Pagination (CRITICAL):** WorkIQ returns email results in batches. A single query will NOT return all emails from a large mailbox. After each query, ask "Are there more emails matching this search?" and continue until all results are retrieved. Break large date ranges into monthly windows if results appear truncated.

### Step 2: Extract Thread Data

For each email thread, extract:

- **Initial question**: The customer's original request or problem report
- **Sender type**: External customer, internal engineer, partner, or automated system
- **Reply chain**: All responses, noting who replied (team member vs. support bot vs. customer follow-up)
- **Resolution**: Whether the issue was resolved and what the fix was
- **Attachments**: Note any logs, screenshots, or config files attached (these indicate complex issues)
- **Thread length**: Number of replies (long threads = complex issues = potential doc gaps)

### Step 3: Filter and Prioritize

- **Prioritize human team responses** over automated replies or auto-acknowledgments
- **Flag long threads** (5+ replies) — these indicate issues that are hard to resolve and likely need better docs
- **Flag escalation markers** — phrases like "escalating", "urgent", "P1", "looping in", "can you help" indicate important gaps
- **Skip** auto-generated notifications, out-of-office replies, and calendar invites
- **Deduplicate** against channel and meeting data — flag emails about the same topic (reinforcement) vs. email-only issues (unique gaps)

### Step 4: Categorize by Topic

Assign each email thread to one or more categories, using the same taxonomy as channel and meeting analysis:

| Category | Keywords / Signals |
|----------|-------------------|
| Authentication / Identity | auth, MSI, token, RBAC, login, certificate, managed identity |
| Setup / Installation | install, setup, onboarding, getting started, prerequisites |
| API / SDK | API, SDK, endpoint, request, response, payload, schema |
| Configuration | config, settings, environment, variable, parameter |
| Troubleshooting / Errors | error, fail, broken, timeout, 500, 404, exception, crash |
| Performance / Reliability | slow, latency, timeout, scale, throttle, retry |
| Migration / Upgrade | migrate, upgrade, deprecate, breaking change, version |

### Step 5: Extract Documentation Content

From email threads, extract content that would improve docs:

- **Detailed reproduction steps** — emails often contain step-by-step repro that channels lack
- **Error messages and stack traces** — customers paste full errors in emails
- **Configuration snippets** — customers share their config when asking for help
- **Workarounds** — team members provide workarounds that should be documented
- **Links to related resources** — team members often link to internal docs, PRs, or wiki pages

### Step 6: Produce Email Analysis Summary

```
Mailbox: [mailbox address]
Emails analyzed: [count]
Date range: [start] — [end]

Questions extracted: [count]
  - Also in channels/meetings: [count] (reinforcement)
  - Email-only: [count] (unique gaps)

Long escalation threads (5+ replies): [count]
Threads with attachments: [count]

Top topics:
1. [topic] — [count] email threads
2. [topic] — [count] email threads
...
```

## Error Handling

- **Mailbox not accessible** → User may not have permissions. Verify shared mailbox membership or delegated access.
- **No emails found** → Check mailbox address and date range. If keywords are too restrictive, try without keyword filtering.
- **Too many emails** → Process in reverse chronological order. Apply keyword filters to focus on support-relevant messages.
- **Non-English emails** → Note the language and process as best as possible. Flag for manual review if needed.
