---
name: pr-review-mining
description: >
  Shared skill for fetching and analyzing PR review comments from Azure DevOps or GitHub.
  Provides platform detection, data fetching patterns, comment categorization, filtering rules,
  and scoring formulas. Used by both learn-from-reviews (author-scoped) and team-playbook (repo-scoped).
allowed-tools: Bash, Read, Write, Glob, Grep, Task
---

# PR Review Mining — Shared Skill Reference

Shared data-fetching and analysis foundation for any scenario that mines PR review comments.

## Platform Detection

Auto-detects hosting platform from `git remote get-url origin`:

| Pattern | Platform |
|---------|----------|
| `dev.azure.com/{org}/{project}/_git/{repo}` | Azure DevOps |
| `{org}@vs-ssh.visualstudio.com:v3/{org}/{project}/{repo}` | Azure DevOps |
| `{org}.visualstudio.com/{project}/_git/{repo}` | Azure DevOps |
| `github.com/{owner}/{repo}` | GitHub |

## Data Fetching

### Azure DevOps

Uses the ADO MCP server (`ado-stdio`). Requires authentication via browser flow.

Key operations:
- Search PRs by project/repo (optionally filter by author)
- Fetch PR threads (review comments) per PR

### GitHub

Uses `gh` CLI with GraphQL batch query. Requires `gh auth login`.

**Repo-scoped query** (all authors — for team-level analysis):
```bash
gh api graphql -f query='
query($owner: String!, $repo: String!) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, states: MERGED, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number
        title
        createdAt
        reviews(first: 50) {
          nodes { body, author { login }, state }
        }
        reviewThreads(first: 100) {
          nodes {
            isResolved
            comments(first: 20) {
              nodes { body, path, author { login }, diffHunk }
            }
          }
        }
      }
    }
  }
}' -f owner='{owner}' -f repo='{repo}'
```

**Author-scoped query** (single developer — for personal learning):
```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $author: String!) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 20, states: [OPEN, CLOSED, MERGED], orderBy: {field: CREATED_AT, direction: DESC}, author: $author) {
      nodes {
        number
        title
        createdAt
        reviews(first: 50) {
          nodes { body, author { login }, state }
        }
        reviewThreads(first: 100) {
          nodes {
            isResolved
            comments(first: 20) {
              nodes { body, path, author { login }, diffHunk }
            }
          }
        }
      }
    }
  }
}' -f owner='{owner}' -f repo='{repo}' -f author='{username}'
```

## Comment Filtering

### Keep
- Substantive feedback (suggestions, corrections, concerns, questions)
- Bot feedback if substantive (security scans, AI code review findings)

### Skip
- Comments fewer than 10 characters
- Approvals: "LGTM", "Approved", "looks good", "+1", "👍"
- Status updates: "merged", "closing", "resolved"
- Auto-generated merge/CI comments

## Comment Categories

| Category | Covers |
|----------|--------|
| **BugRisk** | Potential bugs, null checks, logic errors, edge cases, race conditions |
| **Security** | Vulnerabilities, auth issues, data exposure, injection, secrets in code |
| **Performance** | Optimization, caching, async patterns, memory, scalability |
| **CodeQuality** | Style, naming, readability, formatting, code smells |
| **Testing** | Missing tests, coverage, flaky tests, assertions |
| **Documentation** | Missing docs, comments, README, API docs |
| **Design** | Architecture, patterns, SOLID principles, abstractions, coupling |
| **ErrorHandling** | Exception handling, logging, retry logic, graceful degradation |
| **Refactoring** | Cleanup, dead code, restructuring, modernization |
| **Configuration** | Config files, env vars, build settings, dependencies |

## Scoring Formulas

### Pattern Score (general)
```
pattern_score = (frequency * 2) + (prs_affected * 3) + (unique_reviewers * 1.5)
```

### Rejection Score (team playbook)
```
rejection_score = (frequency * 2) + (prs_affected * 3) + (unique_reviewers * 2)
```

### Tribal Knowledge Score (team playbook)
```
tribal_score = (explanation_depth * 2) + (consequence_severity * 3) + (area_traffic * 1)
```

### Match Score (personal learning cards)
```
match_score = (file_matches * 2) + (keyword_matches * 1) + (semantic_match * 3) + (pattern_score * 0.1)
```

## Error Handling

| Scenario | Response |
|----------|----------|
| Not in git repo | Stop — "I need a git repository." |
| ADO MCP unavailable | Show connection guidance, stop gracefully |
| `gh` CLI not authenticated | "Run `gh auth login` to connect." |
| Remote is not ADO or GitHub | Ask user for platform details |
| No PRs found | Report clearly, do not fabricate |
| API error / timeout | Report error, do not retry silently |

**Hard rule: Never fabricate review history. If data is unavailable, say so.**
