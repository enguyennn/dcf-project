---
name: run-id
description: Generates a short unique run identifier (6 hex characters from a UUID4) for isolating pipeline output directories. Use this skill at the start of any pipeline execution that writes output files, to avoid collisions with parallel runs.
---

# Run ID Skill

Generates a 6-character hexadecimal identifier derived from a UUID4. Used to create unique output directory names so parallel pipeline executions don't collide.

## When to Use

Use this skill **at the very start** of any pipeline execution that writes output to a shared `output/` directory — particularly CheckStability, which may run concurrently with other Gatekeeper pipelines.

## How to Invoke

```bash
python .github/skills/run-id/scripts/generate_run_id.py
```

### Output

Prints a single line to stdout: a 6-character lowercase hex string.

```
a1b2c3
```

### Example Usage

```bash
RUN_ID=$(python .github/skills/run-id/scripts/generate_run_id.py)
OUTPUT_DIR="output/stability-${RUN_ID}"
mkdir -p "$OUTPUT_DIR"
echo "Stability output directory: $OUTPUT_DIR"
```

On PowerShell:

```powershell
$RunId = python .github/skills/run-id/scripts/generate_run_id.py
$OutputDir = "output/stability-$RunId"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Write-Host "Stability output directory: $OutputDir"
```
