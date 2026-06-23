---
name: octane-team-playbook
description: >-
  Generate a Team Playbook from PR review history for new contributors —
  surfaces top rejection patterns, quality bar by area, tribal knowledge, and
  reviewer mapping by mining the last 50 merged PRs (repo-scoped, all authors)
  from GitHub or Azure DevOps. Use when a developer says "generate a team
  playbook", "what do reviewers care about", "help me prepare to contribute", or
  "analyze PR review history".
metadata:
  type: operational
  agent: RepoAnalyst
  version: "2.0"
---

# Team Playbook — Contributor Onboarding from PR History

Generate a **Team Playbook** for new contributors by mining PR review history.
The playbook teaches what reviewers care about, what gets PRs rejected, tribal
knowledge, and who reviews which areas.

**Philosophy**: This is a learning document for new hires. It should feel like a
friendly senior engineer briefing you before your first PR — not a rulebook.

> **Shared foundation**: this skill extends the shared
> [`pr-review-mining`](../../../../shared/skills/pr-review-mining/SKILL.md)
> skill (platform detection, fetching patterns, comment categories, filtering
> rules, scoring formulas) with repo-scoped analysis and team-oriented output.

## When to Use

- The user says "generate a team playbook", "what do reviewers care about",
  "help me prepare to contribute", or "analyze PR review history".
- A new contributor wants to understand the review culture of a repository
  before submitting their first PR.
- The agent should be `Octane.RepoAnalyst` (see
  [agents/Octane.RepoAnalyst.agent.md](../../agents/Octane.RepoAnalyst.agent.md)); it
  carries the declared model, the `ado-stdio/*` tool allow-list, and the
  step-compliance guarantees this skill depends on. If a different agent is
  active, this skill will delegate — see
  [Agent Delegation](#agent-delegation-mandatory).

## Inputs

No user inputs are required. All context (platform, repository, organization) is
gathered automatically from the local git repository via
`git remote get-url origin`.

## Scope

- **Repo-scoped** — fetches PRs from all authors (not filtered to one
  developer).
- **Target audience** — new contributors who haven't submitted a PR yet.
- **Data source** — last 50 merged PRs with all review threads.

## Agent Delegation (MANDATORY)

This skill is designed to run under the `Octane.RepoAnalyst` agent (see
[agents/Octane.RepoAnalyst.agent.md](../../agents/Octane.RepoAnalyst.agent.md)), which
carries the model declaration, the `ado-stdio/*` tool allow-list, and the
step-compliance + quality guarantees this skill's workflow assumes.

**Before executing any step below, check the active agent:**

- **If the active agent IS `Octane.RepoAnalyst`** → proceed to `## Primary
  Directive`.
- **If the active agent is NOT `Octane.RepoAnalyst`** → you MUST delegate this
  skill's execution to `Octane.RepoAnalyst` instead of running it yourself. Use the
  host's agent-switching mechanism:
  - **VS Code Copilot Chat**: instruct the user to re-invoke under the target
    agent (e.g., `@Octane.RepoAnalyst /octane-team-playbook`) and stop.
  - **Copilot CLI**: re-invoke with `--agent Octane.RepoAnalyst` (e.g.,
    `copilot --agent Octane.RepoAnalyst -p "/octane-team-playbook"`) or launch
    `Octane.RepoAnalyst` as a sub-agent for this task.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch to
    `Octane.RepoAnalyst` as a sub-agent.

Do **not** silently execute the workflow under a generic or unrelated agent —
the categorization and scoring contract assumes the `Octane.RepoAnalyst` tool
allow-list, and running it elsewhere may fabricate quotes or attributions.

## Primary Directive

Mine the repository's PR review history and write a contributor Team Playbook to
`./docs/team-playbook.md`. Quote reviewers accurately, attribute correctly, and
frame the output as "here's how to succeed" rather than "here's how you'll
fail".

## Workflow Overview

```
Phase 1: DETECT PLATFORM & CONTEXT    → git remote, platform detection
Phase 2: FETCH PR REVIEW COMMENTS     → GitHub GraphQL or ADO MCP
Phase 3: ANALYZE & CATEGORIZE         → AI analysis into 4 sections
Phase 4: GENERATE TEAM PLAYBOOK       → write docs/team-playbook.md
```

Present each phase as **trackable todos** so the user can follow progress.

## Phase 1: Detect Platform & Context

Run context gathering:

```bash
echo "===REMOTE===" && git remote get-url origin && echo "===BRANCH===" && git branch --show-current
```

### Parse Platform

| Pattern | Platform |
|---------|----------|
| `dev.azure.com/{org}/{project}/_git/{repo}` | Azure DevOps |
| `{org}@vs-ssh.visualstudio.com:v3/{org}/{project}/{repo}` | Azure DevOps |
| `{org}.visualstudio.com/{project}/_git/{repo}` | Azure DevOps |
| `github.com/{owner}/{repo}` | GitHub |

Extract: `owner`/`org`, `project` (ADO), `repo` name.

## Phase 2: Fetch PR Review Comments

### For GitHub Repositories

Use a **single GraphQL query** to fetch the last 50 merged PRs with all review
threads:

```bash
gh api graphql -f query='
query($owner: String!, $repo: String!) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 50, states: MERGED, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number
        title
        url
        author { login }
        mergedAt
        changedFiles
        additions
        deletions
        reviews(first: 50) {
          nodes {
            body
            author { login }
            state
          }
        }
        reviewThreads(first: 100) {
          nodes {
            isResolved
            path
            comments(first: 20) {
              nodes {
                body
                path
                author { login }
                diffHunk
                createdAt
              }
            }
          }
        }
      }
    }
  }
}' -f owner='{owner}' -f repo='{repo}'
```

If `gh` CLI is not authenticated:
> ⚠️ Run `gh auth login` to connect to GitHub.

### For Azure DevOps Repositories

Use the `ado-stdio/*` MCP server tools:

1. Search for the last 50 merged PRs in the detected project/repo.
2. For each PR, fetch review threads and inline comments.
3. Collect: comment body, file path, author, resolution status, code context.

If the ADO MCP is unavailable:
> ⚠️ The Azure DevOps MCP server is not connected. Ensure `ado-stdio` is
> registered and you're authenticated.

### Common: Filter Comments

**Keep**: substantive feedback (suggestions, corrections, concerns,
explanations, questions about design/patterns).

**Skip**:
- Comments < 10 characters.
- Pure approvals: "LGTM", "Approved", "+1", "👍", "looks good".
- Status updates: "merged", "closing", "resolved".
- Bot noise (unless substantive like security findings).

**Hard cap: 50 PRs. Never paginate beyond this.**

## Phase 3: Analyze & Categorize

Analyze the collected comments and organize them into 4 sections. The
playbook-section mapping:

| Playbook Section | Source Categories | Signals |
|-----------------|-------------------|---------|
| **Rejection Patterns** | All categories | Corrections, "please fix", "this will break", change requests |
| **Quality Bar** | Testing, Documentation, CodeQuality | "Add tests", "update docs", "coverage" |
| **Tribal Knowledge** | Design, Configuration, Refactoring | "Intentional because", "don't change", "historical", "workaround for" |
| **Reviewer Mapping** | All | Derived from comment author × file path × comment type |

### Section 1: Top Rejection Patterns

Identify **recurring negative feedback** — the same type of issue flagged across
multiple PRs by multiple reviewers. For each pattern, extract: pattern name,
frequency (count + PRs affected), affected areas (file path patterns),
representative quote (actual reviewer words), and a correct alternative (search
the codebase for a contrasting good example; only include if high confidence,
same language).

**Scoring**:
```
rejection_score = (frequency * 2) + (prs_affected * 3) + (unique_reviewers * 2)
```

Keep the top 5–8 patterns sorted by score.

### Section 2: Quality Bar by Area

Group comments that request **tests, documentation, or coverage** by the file
path prefix they target. Produce a per-directory quality expectations table:
which directories require unit tests, documentation updates, strict review, and
what coverage level is expected. Group by top-level directory (e.g., `src/api/`,
`src/core/`, `tests/`).

### Section 3: Tribal Knowledge

Identify comments that are **explanatory, not corrective** — they convey
institutional knowledge. Signal patterns: "This is intentional because…",
"Don't change/refactor X because…", "This looks wrong but it's needed for…",
"Historical context: …", "If you change this, you also need to update…", "We
tried X before and it broke Y", "This is a workaround for …". For each item
capture: area, the knowledge, source quote, and why it matters. Keep the top
5–10 most impactful items.

### Section 4: Who Reviews What

From comment metadata, build a reviewer map. For each significant reviewer (3+
PRs reviewed): name/handle, areas they review (top file path patterns), what
they focus on (testing? security? architecture? performance?), and review style
(detailed? concise? question-heavy?). Sort by review volume. Keep the top 5–8
reviewers.

## Phase 4: Generate Team Playbook

Write the complete playbook to `./docs/team-playbook.md` in a **single write
operation**. Create the `docs/` directory if needed.

### Output Template

```markdown
# Team Playbook

> Your guide to making high-quality contributions to this repository.
> Auto-generated from PR review history by Octane.

**Repository:** [{repo_name}]({repo_url})
**Generated:** [YYYY-MM-DD]
**PRs analyzed:** [N] | **Comments processed:** [N]

---

## 🚫 Top Rejection Patterns

*What will get your PR sent back — and how to avoid it.*

### 1. [Pattern Name]

**Flagged:** [N] times across [N] PRs | **Areas:** `[paths]`

> 💬 "[Representative reviewer quote]"
> — *[Reviewer], on PR #[N]*

**Instead, do this:**
\`\`\`[language]
[correct alternative from codebase, or description if no example found]
\`\`\`

---
[Repeat for top 5-8 patterns]

---

## ✅ Quality Bar by Area

*What level of completeness each area expects.*

| Directory | Tests Required | Docs Required | Coverage Bar | Notes |
|-----------|:---:|:---:|:---:|-------|
| `src/api/` | ✅ | ✅ | ~80% | Integration tests preferred |
| `src/core/` | ✅ | ❌ | ~90% | Unit tests required |
| `scripts/` | ❌ | ❌ | — | Best-effort |

---

## 💡 Tribal Knowledge

*Things that aren't in the docs but every experienced contributor knows.*

### 1. [Area]: [Brief title]

> 💬 "[Source quote from reviewer]"
> — *[Reviewer]*

**What this means for you:** [Plain language explanation of the implication]

---
[Repeat for top 5-10 items]

---

## 👥 Who Reviews What

*Know your reviewers — what they focus on and which areas they own.*

| Reviewer | Areas | Focus | Style |
|----------|-------|-------|-------|
| @[handle] | `src/api/`, `src/auth/` | Security, error handling | Detailed, asks "why" questions |
| @[handle] | `src/core/` | Architecture, patterns | Concise, links to docs |

---

*Powered by Octane Team Playbook 📘*
```

## Output Rules

1. **Write to file** — all content goes to `./docs/team-playbook.md`.
2. **No code modifications** — this skill NEVER changes the user's code.
3. **Honest about data** — if the platform is unavailable or returns no data,
   say so.
4. **Quote accurately** — use actual reviewer words, attributed correctly.
5. **Repo-scoped** — analyze ALL authors, not just the current user.
6. **Positive tone** — frame as "here's how to succeed" not "here's how you'll
   fail".

## Error Handling

| Scenario | Response |
|----------|----------|
| Not in git repo | "I need a git repository. Please run from inside a repo." |
| Remote is not GitHub or ADO | "Platform not detected. This skill supports GitHub and Azure DevOps." |
| `gh` CLI not authenticated (GitHub) | "Run `gh auth login` to connect." |
| ADO MCP unavailable (ADO) | Show connection guidance |
| No PRs found | "No merged PRs found. The Team Playbook needs PR history to generate insights." |
| PRs found but no substantive comments | "Found [N] PRs but no substantive review comments to analyze." |
| API rate limited | "Hit API rate limits. Try again later or reduce PR count." |

## Hard Limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| Max PRs fetched | 50 | Sufficient signal, bounded API usage |
| Max rejection patterns | 8 | Focused, not overwhelming |
| Max tribal knowledge items | 10 | Most impactful only |
| Max reviewers listed | 8 | Key people, not everyone |

## Example

```text
/octane-team-playbook
```

Produces `docs/team-playbook.md` with rejection patterns, quality bar, tribal
knowledge, and reviewer mapping derived from the last 50 merged PRs.

## Output

`docs/team-playbook.md` — the contributor Team Playbook. This skill never
modifies the user's source code.
