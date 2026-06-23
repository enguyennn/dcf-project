---
name: download-skills
description: Downloads review-derived-skills from azure-core/pandora and installs them into the target repository's .github/skills folder. Use this skill to provision or refresh guideline skill files before running the Gatekeeper review pipeline.
---

# Download Skills

Downloads the `review-derived-skills` folder from [`azure-core/pandora`](https://github.com/azure-core/pandora/tree/main/src/gatekeeper-data/crp-guideline-data/guidelines/review-derived-skills) and places the contents into `.github/skills/` under a target repository root.

## When to Use

Use this skill **before running the Gatekeeper review pipeline** to ensure the target repository has the latest guideline skill definitions. It clears any existing content in `.github/skills/` before downloading to guarantee a clean, up-to-date set.

## How to Invoke

```bash
python .github/skills/download-skills/scripts/download_skills.py <target_folder>
```

### Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `target_folder` | Yes | — | Root directory of the target repository (e.g. `D:\Compute-CPlat-Core`) |

### Prerequisites

- **Python 3.6+**
- **`gh` CLI** authenticated (`gh auth login`) — used to obtain a GitHub API token. The script still works without it but may hit API rate limits.

## Behavior

1. **Clears** the `<target_folder>/.github/skills/` directory if it exists
2. **Creates** the directory if it doesn't exist
3. **Downloads** all files and subdirectories from the pandora source path via the GitHub Contents API
4. **Writes** them into `.github/skills/`, preserving the folder structure

## Output

Prints each downloaded file path to stdout:

```
Clearing D:\Compute-CPlat-Core\.github\skills
Downloading ... -> D:\Compute-CPlat-Core\.github\skills
  D:\Compute-CPlat-Core\.github\skills\_conversion-manifest.json
  D:\Compute-CPlat-Core\.github\skills\add-defensive-contract-assertions\SKILL.md
  ...
Done.
```

## Example Pipeline Usage

```bash
# 1. Download/refresh skills into the target repo
python .github/skills/download-skills/scripts/download_skills.py /path/to/repo

# 2. Run filter stage
python .github/skills/filter-guidelines/filter.py --output filter_output.json

# 3. Batch files for review
python .github/skills/batch-files/scripts/batch_files.py \
  --input filter_output.json --output batches.json
```

On PowerShell:

```powershell
python .github/skills/download-skills/scripts/download_skills.py "D:\Compute-CPlat-Core"
```
