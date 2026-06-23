---
name: support-thread-analysis
description: Use when extracting and categorizing support threads from a Teams channel via WorkIQ
---

# Support Thread Analysis

Extract, categorize, and rank support threads from a Teams channel to identify documentation gaps.

## When to Use

Use this skill when you need to pull support history from a Teams channel and structure it for documentation analysis.

## Mandatory Execution Steps

### Step 1: Query Support Channel

Use WorkIQ to ask about the Teams support channel. **WorkIQ returns results in batches** — a single query will NOT return all threads from a large channel. You MUST paginate to get complete coverage.

**Initial query:**
```
"What are the support threads in the [channel name] channel in [team name] from [date range]? 
For each thread, give me: 
1. The original question or problem reported 
2. Who responded and their answer 
3. Whether the response was from a bot or a human"
```

**Pagination strategy (CRITICAL):**
1. **Break large date ranges into 3-month windows** — e.g., Jan-Mar, Apr-Jun, Jul-Sep, Oct-Dec for a full year
2. **After each query, check for completeness** — if WorkIQ returns a round number of results (e.g., exactly 10 or 20), or says "here are some threads", assume the results are truncated
3. **Request more** — ask "Are there more threads in [channel name] from [same date range]?" or "Show me the next batch of threads"
4. **Narrow the window if still truncating** — if a 3-month window returns too many results, break it into monthly windows
5. **Continue until WorkIQ confirms no more results** or returns fewer results than previous batches
6. **Track running totals** — after each batch, count total threads retrieved and report progress

**Completeness check:**
After all batches are processed, report:
- Total threads retrieved
- Date range covered
- Number of batches queried
- Whether any batches appeared truncated (flag for user review)

### Step 2: Extract Thread Data

For each thread, extract:
- **Question**: The customer's original question or problem statement
- **Responder**: Who answered (human team member vs. bot)
- **Resolution**: The answer or solution provided
- **Date**: When the thread was created

### Step 3: Filter and Prioritize

- **Prioritize human responses** over bot/automated answers — real team expertise is more valuable for documentation
- **Skip threads** with no resolution or only bot responses (unless the bot answer is substantive)
- **Flag recurring themes** — if the same question appears multiple times, note the count

### Step 4: Categorize by Topic

Assign each thread to one or more categories:

| Category | Keywords / Signals |
|----------|-------------------|
| Authentication / Identity | auth, MSI, token, RBAC, login, certificate, managed identity |
| Setup / Installation | install, setup, onboarding, getting started, prerequisites |
| API / SDK | API, SDK, endpoint, request, response, payload, schema |
| Configuration | config, settings, environment, variable, parameter |
| Troubleshooting / Errors | error, fail, broken, timeout, 500, 404, exception, crash |
| Performance / Reliability | slow, latency, timeout, scale, throttle, retry |
| Migration / Upgrade | migrate, upgrade, deprecate, breaking change, version |

### Step 5: Rank by Frequency

Count threads per category and produce a ranked summary:

```
1. Authentication / Identity — 47 threads (15.7%)
2. Troubleshooting / Errors — 38 threads (12.7%)
3. Setup / Installation — 31 threads (10.3%)
...
```

## Error Handling

- **WorkIQ returns no results** → Verify channel name and team name are correct. Ask the user to confirm.
- **Channel has very few threads** → Report the low count and note that recommendations may be limited. Minimum `${config:support-driven-docs.analysis.min_threads}` threads recommended.
- **Ambiguous categorization** → Assign to the most specific matching category. A thread can belong to multiple categories.
