---
name: meeting-transcript-analysis
description: Use when extracting and analyzing Teams meeting transcripts and Copilot recaps via WorkIQ
---

# Meeting Transcript Analysis

Extract customer questions, expert explanations, and documentation action items from Teams meeting transcripts and Copilot recaps.

## When to Use

Use this skill when you need to analyze Teams meetings (office hours, support syncs, Q&A sessions) as a data source for documentation improvement. Meetings capture verbal questions and detailed expert walkthroughs that never appear in support channels.

## Important Constraints

- Transcripts are accessed **per meeting instance**, not as a global search
- Each occurrence of a recurring meeting has its own transcript, chat, and recap
- Copilot recaps require Teams Premium or Microsoft 365 Copilot
- Transcription must have been enabled during the meeting for transcripts to exist

## Mandatory Execution Steps

### Step 1: Find Meeting Occurrences

Use WorkIQ to find occurrences of each configured meeting within the date range:

```
"Find all occurrences of the meeting '[meeting name]' from [date range]. 
For each occurrence, tell me:
1. Date and time
2. Whether a transcript exists
3. Whether a Copilot recap/summary is available
4. Number of attendees"
```

If a meeting has many occurrences, process in batches (e.g., 10 at a time). **WorkIQ may not return all occurrences in a single query** — ask "Are there more occurrences?" and continue until all are retrieved.

### Step 2: Retrieve Copilot Recaps First

For each occurrence with a recap available, query WorkIQ:

```
"For the [meeting name] meeting on [date], give me:
1. The Copilot meeting summary
2. All action items identified
3. Key topics discussed
4. Any decisions made"
```

**Why recaps first:** Recaps provide pre-structured summaries and action items, giving you a quick overview before diving into full transcripts. This is faster and often sufficient for identifying documentation gaps.

### Step 3: Retrieve Full Transcripts (When Needed)

For meetings where the recap is insufficient or unavailable, query the full transcript:

```
"For the [meeting name] meeting on [date], give me the meeting transcript. 
I'm looking for:
1. Questions asked by attendees (especially customer-facing questions)
2. Detailed explanations or walkthroughs given in response
3. Any mentions of documentation, wikis, or 'we should document this'"
```

### Step 4: Extract Documentation-Relevant Content

From each meeting occurrence, extract:

**Customer/attendee questions:**
- Questions about how to use a feature or service
- Questions about errors, failures, or unexpected behavior
- Questions about setup, configuration, or prerequisites
- "How do I...?" and "Why doesn't...?" patterns

**Expert explanations:**
- Step-by-step walkthroughs provided verbally
- Workarounds or tips shared by team members
- Context or "gotchas" mentioned during explanations
- These are often richer than channel replies and make excellent doc content

**Documentation action items:**
- Explicit: "We should document this", "I'll update the wiki", "This needs to be in the FAQ"
- Implicit: "I keep explaining this every week", "This comes up in every office hours"
- Track whether these action items were ever resolved

**Recurring patterns:**
- Questions that appear across multiple meeting occurrences
- Topics that come up repeatedly in office hours (strong signal for doc gaps)

### Step 5: Retrieve Meeting Chat (If Configured)

If meeting chat analysis is enabled, also query:

```
"What messages were shared in the chat during the [meeting name] meeting on [date]?
Include any links, code snippets, or files shared."
```

Meeting chat often contains:
- Links shared as references during the discussion
- Code snippets or error messages pasted by attendees
- Follow-up questions that didn't get answered verbally

### Step 6: Categorize and Deduplicate

Assign each extracted item to topic categories matching the channel thread categories:

| Category | Keywords / Signals |
|----------|-------------------|
| Authentication / Identity | auth, MSI, token, RBAC, login, certificate, managed identity |
| Setup / Installation | install, setup, onboarding, getting started, prerequisites |
| API / SDK | API, SDK, endpoint, request, response, payload, schema |
| Configuration | config, settings, environment, variable, parameter |
| Troubleshooting / Errors | error, fail, broken, timeout, 500, 404, exception, crash |
| Performance / Reliability | slow, latency, timeout, scale, throttle, retry |
| Migration / Upgrade | migrate, upgrade, deprecate, breaking change, version |

**Deduplicate against channel data:**
- Flag questions that also appear in channel threads (reinforcement)
- Highlight questions that ONLY appear in meetings (unique verbal gaps — high value)

### Step 7: Produce Meeting Analysis Summary

For each analyzed meeting series, produce:

```
Meeting: [name]
Occurrences analyzed: [count]
Date range: [start] — [end]

Questions extracted: [count]
  - Also in channels: [count] (reinforcement)
  - Meeting-only: [count] (unique gaps)

Expert explanations captured: [count]
Documentation action items: [count] ([resolved] resolved, [unresolved] unresolved)

Top topics:
1. [topic] — [count] mentions across [count] occurrences
2. [topic] — [count] mentions across [count] occurrences
...
```

## Error Handling

- **Meeting not found** → Verify the meeting name matches exactly. Ask the user to confirm.
- **No transcript available** → The meeting may not have had transcription enabled. Log and skip. Note in the report which meetings lack transcripts.
- **No Copilot recap** → Fall back to full transcript analysis. Note that recaps require Teams Premium or M365 Copilot.
- **Too many occurrences** → Process in reverse chronological order. Most recent meetings are typically more relevant.
- **WorkIQ can't access meeting** → User may not have been an attendee. Only meetings the user attended or organized are accessible.
