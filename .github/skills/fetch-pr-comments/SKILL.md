---
name: fetch-pr-comments
description: Fetches code-level reviewer comments from a PR (Azure DevOps or GitHub), maps them to iterations, and returns JSON in the format expected by the Gatekeeper Replay pipeline. Use after fetch-pr-iterations to collect the comments for classification.
---

# Fetch PR Comments Skill

Fetches all human code-level reviewer comments from a pull request, maps each to its iteration, and returns a JSON array ready for the Gatekeeper Replay pipeline.

Supports Azure DevOps and GitHub PRs.

## When to Use

Use this skill in **Step 3 (Fetch PR Comments)** of the Gatekeeper Replay pipeline, after `fetch-pr-iterations` has produced the iteration timeline.

## How to Invoke

```bash
python .github/skills/fetch-pr-comments/scripts/fetch_pr_comments.py \
  --pr-url "https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}" \
  --iterations output/replay/pr-iterations.json \
  --output output/replay/pr-comments.json
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--pr-url` | Yes | Full PR URL (Azure DevOps or GitHub) |
| `--iterations` | No | Path to pr-iterations.json (from fetch-pr-iterations skill). Filters comments to only iterations with comments. |
| `--iteration-id` | No | Filter output to only comments for this specific iteration ID (e.g., `5`). Use for per-iteration analysis in parallel replay. |
| `--output` | No | Output file path. If omitted, prints JSON to stdout. |

### Prerequisites

- **Azure DevOps**: `az` CLI authenticated (`az login`)
- **GitHub**: `gh` CLI authenticated (`gh auth login`)

## Output Format

```json
[
  {
    "comment_id": "201403854",
    "iteration_id": "5",
    "file_path": "src/CRP/Dev/.../EntityCache.cs",
    "line_number": "189",
    "comment_body": "rename to entityGroupCacheQueryContext or just cacheQueryContext",
    "author": "Sameer Motwani"
  }
]
```

Fields:
- `comment_id`: Platform-native thread/comment ID (string)
- `iteration_id`: Which iteration the comment belongs to (string)
- `file_path`: Repo-relative file path
- `line_number`: Line number or range (e.g., `"189"` or `"39-42"`)
- `comment_body`: Comment text (HTML stripped, whitespace normalized)
- `author`: Display name of the commenter

Comments are sorted by iteration_id, then file basename, then line number.
