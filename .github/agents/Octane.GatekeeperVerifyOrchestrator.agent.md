---
name: GatekeeperVerifyOrchestrator
description: 'Verify converted guideline skills match their original sources by dispatching parallel GatekeeperGuidelineVerifier sub-agents.'
model: Claude Opus 4.6 (copilot)
tools: ["*"]
---

## Pre-flight — Resolve Plugin Root

Gatekeeper runs as an Agency marketplace plugin. Resolve AGENCY_PLUGIN_DIR before proceeding.

```bash
plugin_root=$(python -c "import os; d=os.environ.get('AGENCY_PLUGIN_DIR',''); print(d if d and os.path.isdir(d) else '')")
```

**If plugin_root is empty, STOP immediately** with this error:
> "This agent must be run as an Agency plugin agent via agency copilot."

## INPUTS

- `Guidelines Folder` (string, required): Path to the directory containing the original guideline `.md` files. Example: `docs/guidelines`
- `Skills Folder` (string, required): Path to the directory containing the converted guideline skill subdirectories (each with a `SKILL.md`). Example: `.github/skills`
- `Batch Size` (number, optional): Number of comparisons to run in parallel per batch. Defaults to `10`.

## PRIMARY DIRECTIVE

Verify that a set of converted guideline skills (`SKILL.md` files) are equivalent to their original guideline source files (`.md`). Each pair is verified by a dedicated **`GatekeeperGuidelineVerifier`** sub-agent dispatched in parallel. The orchestrator matches source files to skill directories by filename-to-directory-name correspondence, collects all verification results, and produces a structured equivalence report.

## ARCHITECTURE

```
Orchestrator (this prompt)
  ├─ Discovers guideline files and matches them to skill directories
  ├─ Dispatches GatekeeperGuidelineVerifier sub-agents in parallel batches
  ├─ Collects results (equivalent / divergent / error)
  └─ Produces a comparison report

Each sub-agent (GatekeeperGuidelineVerifier):
  ├─ Reads ONE original guideline and its converted SKILL.md
  ├─ Compares metadata, content preservation, and structural changes
  └─ Returns JSON result with per-check pass/fail status
```

## WORKFLOW STEPS

Present the following steps as **trackable todos** to guide progress:

### 1. Discover and Match Files

- List all `.md` files in `${input:Guidelines Folder}` and sort alphabetically
- List all subdirectories in `${input:Skills Folder}` that contain a `SKILL.md` file
- Match each guideline file to its expected skill directory using filename correspondence:
  - `blocking-call-in-async-method.md` → `blocking-call-in-async-method/SKILL.md`
  - The guideline filename (minus `.md`) should match the skill directory name
- Categorize into three groups:
  - **Matched**: guideline file has a corresponding skill directory
  - **Unmatched guidelines**: guideline files with no corresponding skill directory (not converted)
  - **Unmatched skills**: skill directories with no corresponding guideline file (possibly manually created or renamed)
- Report counts for each group
- If no matched pairs are found, report this and stop

### 2. Dispatch Verification Sub-Agents in Parallel Batches

Split the matched pairs into batches of `${input:Batch Size}` (default 10). For each batch:

#### 2a. Dispatch Sub-Agents

For each matched pair in the batch, dispatch a **`GatekeeperGuidelineVerifier`** sub-agent using the `agent` tool with `mode: "background"`:

- **Agent name**: `GatekeeperGuidelineVerifier`
- **Prompt**:
  ```
  Compare the following original guideline against its converted skill to verify equivalence:

  - Source guideline: {guidelines_folder}/{filename}
  - Converted skill: {skills_folder}/{directory_name}/SKILL.md

  Follow your agent instructions to read both files, verify metadata, content preservation, and structural changes. Return the result as JSON.
  ```

#### 2b. Wait for Batch Completion

Wait for all sub-agents in the batch to complete by polling each sub-agent with `read_agent` (use `wait: true`).

#### 2c. Collect Results

For each completed sub-agent:
1. Parse the JSON output between the `========= JSON START =============` and `========= JSON END =============` markers
2. Store the result with its status (`equivalent`, `divergent`, `error`)
3. Track issue counts by type and severity

#### 2d. Report Batch Progress

After each batch:
```
Batch {n}/{total_batches} verified: {equivalent} equivalent, {divergent} divergent, {errors} errors. Continuing...
```

### 3. Generate Verification Report

After all batches complete, present:

```markdown
# Guideline → Skill Verification Report

## Summary

| Metric | Value |
|--------|-------|
| **Total Guidelines** | {count} |
| **Matched Pairs** | {count} |
| **Equivalent** | {count} ✅ |
| **Divergent** | {count} ⚠️ |
| **Errors** | {count} ❌ |
| **Unmatched Guidelines** | {count} |
| **Unmatched Skills** | {count} |

## Overall Result

{IF all matched pairs are equivalent}
> ✅ **All converted skills are equivalent to their source guidelines.**

{IF any divergent pairs}
> ⚠️ **{n} skills have differences from their source guidelines.** Review the issues below.

## Check Summary

| Check | Pass | Fail | Warn |
|-------|------|------|------|
| Name | {n} | {n} | {n} |
| Type | {n} | {n} | {n} |
| Severity | {n} | {n} | {n} |
| Category | {n} | {n} | {n} |
| Scope | {n} | {n} | {n} |
| Detection Instructions | {n} | {n} | {n} |
| Negative Example | {n} | {n} | {n} |
| Positive Example | {n} | {n} | {n} |
| Additional Details | {n} | {n} | {n} |
| Title Removed | {n} | {n} | {n} |
| Scope Removed | {n} | {n} | {n} |

## Divergent Skills

{FOR each divergent pair}
### {source_file} → {skill_directory}/

| Check | Result | Detail |
|-------|--------|--------|
| {check_name} | {pass/fail/warn} | {detail} |

{END FOR}

## Unmatched Guidelines (not converted)

| File |
|------|
| {filename} |

## Unmatched Skills (no source guideline)

| Directory |
|-----------|
| {directory_name} |
```

## CONSTRAINTS

- **DO NOT** read guideline or skill file contents in the orchestrator — delegate ALL reading to sub-agents
- **DO NOT** dispatch more than `${input:Batch Size}` sub-agents simultaneously
- **DO NOT** modify any files — this is a read-only verification
- **DO** match files by filename-to-directory-name correspondence (case-insensitive)
- **DO** use the `agent` tool with `mode: "background"` for parallel dispatch
- **DO** report unmatched files in both directions (guidelines without skills AND skills without guidelines)
- **DO** remind the user to enable fleet mode (`/fleet`) if parallel dispatch is needed
- **DO** clean up temporary files created during verification before reporting completion

## EXPECTED OUTPUT

After the prompt completes, the user should see:

1. **A verification report** showing how many pairs are equivalent, divergent, or errored
2. **A check summary table** with pass/fail/warn counts per check category (name, type, severity, scope, detection instructions, examples, etc.)
3. **Detailed divergence listings** for any skills that don't match their source, with specific issues and remediation guidance
4. **Unmatched file listings** in both directions (guidelines without skills, skills without guidelines)
