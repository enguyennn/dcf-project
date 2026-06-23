---
name: fetch-pr-iterations
description: Fetches PR iteration timeline with comment mappings from Azure DevOps or GitHub. Returns JSON in the format expected by the Gatekeeper Replay pipeline. Use at the start of a replay to build the iteration timeline without manual API calls.
---

# Fetch PR Iterations Skill

Fetches the iteration timeline for a pull request, maps reviewer comments to iterations by date, and returns a JSON structure ready for the Gatekeeper Replay pipeline.

Supports Azure DevOps and GitHub PRs.

## When to Use

Use this skill at the **start of a Gatekeeper Replay** (Step 2: Fetch PR Metadata) to replace manual API calls for building the iteration timeline. The script handles:

- Parsing the PR URL to determine platform (ADO or GitHub)
- Fetching iterations/updates and comment threads via platform APIs
- Filtering out bot/system comments (MerlinBot, etc.)
- Mapping each comment to the correct iteration by published date
- Returning only iterations that received human code-level comments

## How to Invoke

```bash
python .github/skills/fetch-pr-iterations/scripts/fetch_pr_iterations.py \
  --pr-url "https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{id}" \
  --output output/replay/pr-iterations.json
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--pr-url` | Yes | Full PR URL (Azure DevOps or GitHub) |
| `--output` | No | Output file path. If omitted, prints JSON to stdout. |

### Prerequisites

- **Azure DevOps**: `az` CLI authenticated (`az login`)
- **GitHub**: `gh` CLI authenticated (`gh auth login`)

## Output Format

```json
{
  "pr_url": "https://dev.azure.com/.../pullrequest/12345",
  "pr_title": "Feature: add widget support",
  "platform": "Azure DevOps",
  "total_iterations": 10,
  "iterations_with_comments": 3,
  "total_code_comments": 15,
  "iteration_timeline": [
    {
      "iteration_id": 2,
      "base_commit": "abc123...(40 chars)",
      "head_commit": "def456...(40 chars)",
      "commit_range": "abc123...def456",
      "has_comments": true,
      "comment_count": 8
    }
  ]
}
```

The `commit_range` uses three-dot diff format (`base...head`) which shows only changes on the source branch relative to the merge-base — matching what a reviewer sees when opening the PR.

## Example

```bash
# Fetch and save iterations for a replay
python .github/skills/fetch-pr-iterations/scripts/fetch_pr_iterations.py \
  --pr-url "https://msazure.visualstudio.com/One/_git/Compute-CPlat-Core/pullrequest/12667474" \
  --output output/replay/pr-iterations.json

# Use in PowerShell
$iterations = python .github/skills/fetch-pr-iterations/scripts/fetch_pr_iterations.py `
  --pr-url "https://msazure.visualstudio.com/One/_git/Compute-CPlat-Core/pullrequest/12667474"
$data = $iterations | ConvertFrom-Json
Write-Host "Iterations with comments: $($data.iterations_with_comments)"
```
