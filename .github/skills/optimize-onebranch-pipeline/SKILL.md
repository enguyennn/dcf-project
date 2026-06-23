---
name: optimize-onebranch-pipeline
description: "Analyze and optimize OneBranch PR pipeline build times. Use when: pipeline slow, build time, PR checks taking too long, speed up CI, optimize pipeline, reduce build time, OneBranch performance."
---

# OneBranch PR Pipeline Optimization

Analyze a OneBranch PR pipeline for build time reduction by examining actual pipeline YAML, 1ES template behavior, real build timelines, and task-level logs. Do not guess — read the source and the logs.

## When to Use

- User says their PR pipeline is slow or wants to speed up CI
- User wants to analyze build times or find optimization opportunities
- User mentions OneBranch pipeline performance

## Prerequisites

- User must be logged into Azure CLI (`az login`)
- The `az` CLI must be installed and on PATH
- Access to the repo containing the pipeline YAML

## Procedure

### Step 1 — Read the Pipeline YAML

Start by reading the actual pipeline source. Find the PR pipeline YAML in the repo:

```powershell
Get-ChildItem -Path . -Recurse -Include "*.yml","*.yaml" | Where-Object { $_.FullName -match '\.pipelines' } | Select-Object FullName
```

Read the PR pipeline YAML and identify:

1. **Which 1ES template it extends** — look for the `extends:` block:
   ```yaml
   extends:
     template: v2/OneBranch.NonOfficial.CrossPlat.yml@templates
   ```
   The template name tells you which 1ES Pipeline Template version is in use. `NonOfficial` = PR builds, `Official` = CI/release. `CrossPlat` = supports both Windows and Linux pools.

2. **The `globalSdl` section** — what SDL checks are enabled/disabled:
   ```yaml
   globalSdl:
     binskim:
       enabled: false
     antimalwareScan:
       enabled: false
   ```

3. **The `featureFlags` section** — critical optimization levers:
   ```yaml
   featureFlags:
     automaticContainerPatching: false  # Copa
     EnableDefenderForLinux: false
     useHyperV: false
   ```

4. **Each job's `pool.type`** — `windows` vs `linux`. This matters hugely for SDL overhead.

5. **Each job's `ob_` variables** — OneBranch-specific variables that control behavior:
   - `ob_outputDirectory` — what gets uploaded as artifacts
   - `ob_sdl_roslyn_break` — whether Roslyn SDL failures break the build
   - `ob_git_fetchDepth` — git clone depth

6. **Stage/job dependency chains** — look for `dependsOn:` to understand what runs serially vs in parallel.

### Step 2 — Read the Pipeline Templates

Check the `.pipelines/templates/` directory for custom job/step templates:

```powershell
Get-ChildItem -Path ".pipelines/templates" -Recurse -Include "*.yml","*.yaml" | Select-Object FullName
```

Read each template to understand what they do. Look for:
- Docker build commands and their flags (`--no-cache`, `--pull`, `--cache-from`)
- Heavy install steps (apt-get, npm install, dotnet restore)
- Steps that could be parallelized or eliminated for PR validation
- Duplicate work across templates

### Step 3 — Fetch and Analyze Real Build Data

Authenticate and pull recent builds:

```powershell
$token = az account get-access-token --resource "https://app.vssps.visualstudio.com" --query accessToken -o tsv
$headers = @{ Authorization = "Bearer $token" }
```

Get the pipeline definition ID from the ADO URL or ask the user. Fetch recent succeeded builds:

```powershell
$org = "<ORG_URL>"      # e.g., https://dev.azure.com/msazure
$project = "<PROJECT>"   # e.g., One
$definitionId = "<ID>"

$builds = (Invoke-RestMethod -Uri "$org/$project/_apis/build/builds?definitions=$definitionId&statusFilter=completed&resultFilter=succeeded&`$top=10&api-version=7.1" -Headers $headers).value
$builds | ForEach-Object {
    $duration = [math]::Round(([datetime]$_.finishTime - [datetime]$_.startTime).TotalMinutes, 1)
    Write-Host "$($_.id) | ${duration}m | $($_.startTime)"
}
```

### Step 4 — Analyze the Build Timeline (Job Level)

Pick a recent build and get the full timeline. This contains every job and task with start/finish times:

```powershell
$buildId = "<RECENT_BUILD_ID>"
$timeline = Invoke-RestMethod -Uri "$org/$project/_apis/build/builds/$buildId/timeline?api-version=7.1" -Headers $headers
$jobs = $timeline.records | Where-Object { $_.type -eq "Job" -and $_.result -eq "succeeded" }
$jobs | Sort-Object { -([datetime]$_.finishTime - [datetime]$_.startTime).TotalMinutes } | ForEach-Object {
    $duration = [math]::Round(([datetime]$_.finishTime - [datetime]$_.startTime).TotalMinutes, 1)
    Write-Host "$($_.name) | ${duration}m | id=$($_.id)"
}
```

Identify the **critical path** — the longest chain of dependent jobs (use `dependsOn` from the YAML). Parallel jobs don't affect wall-clock time.

### Step 5 — Analyze Task-Level Breakdown for Slowest Jobs

For each of the top 3-5 slowest jobs, list ALL tasks and their durations:

```powershell
$jobId = "<JOB_ID>"
$tasks = $timeline.records | Where-Object { $_.parentId -eq $jobId -and $_.type -eq "Task" }
$tasks | Sort-Object { -([datetime]$_.finishTime - [datetime]$_.startTime).TotalSeconds } | ForEach-Object {
    $duration = [math]::Round(([datetime]$_.finishTime - [datetime]$_.startTime).TotalSeconds, 1)
    Write-Host "$($_.name) | ${duration}s | logId=$($_.log.id)"
}
```

This shows exactly where time is spent. Look for tasks that are unexpectedly slow.

### Step 6 — Fetch Actual Task Logs for Suspicious Tasks

When a task takes unexpectedly long, read the actual log to understand WHY:

```powershell
$logId = "<LOG_ID>"
$logContent = Invoke-RestMethod -Uri "$org/$project/_apis/build/builds/$buildId/logs/$logId?api-version=7.1" -Headers $headers
# Show first and last 50 lines to understand what the task did
$lines = $logContent -split "`n"
Write-Host "=== First 50 lines ==="
$lines | Select-Object -First 50 | ForEach-Object { Write-Host $_ }
Write-Host "=== Last 50 lines ==="
$lines | Select-Object -Last 50 | ForEach-Object { Write-Host $_ }
Write-Host "Total lines: $($lines.Count)"
```

Read the logs carefully. Look for:
- Time gaps between log lines (indicates slow operations)
- Defender signature updates (`MpCmdRun.exe`, `Update-MpSignature`, signature download URLs)
- Copa patching steps (`copa`, `patch`, container vulnerability scanning)
- Downloading large files or images
- `npm install` / `dotnet restore` / `apt-get install` taking a long time
- Steps that complete instantly but the task still takes minutes (overhead from the 1ES wrapper)

### Step 7 — Investigate 1ES Injected Tasks

1ES Pipeline Templates inject tasks that don't appear in your YAML. These are the biggest source of hidden overhead. Look for tasks with names containing:

- `(1ES PT)` — injected by the 1ES Pipeline Template
- `SDL Binary Analysis` — BinSkim and antimalware scanning
- `Guardian` — SDL scanning framework
- `Auto-baselining` — SDL baseline management
- `Component Governance` — dependency scanning

Compare injected task behavior between Windows and Linux jobs:

```powershell
$sdlTasks = $timeline.records | Where-Object { $_.name -like "*SDL Binary*" -or $_.name -like "*1ES PT*" }
foreach ($task in $sdlTasks) {
    $parentJob = $timeline.records | Where-Object { $_.id -eq $task.parentId -and $_.type -eq "Job" }
    $duration = [math]::Round(([datetime]$task.finishTime - [datetime]$task.startTime).TotalSeconds, 1)
    Write-Host "$($parentJob.name) | $($task.name) | ${duration}s"
}
```

#### Known 1ES PT Issue: Windows Defender Signature Updates

On **Windows** agents, the "SDL Binary Analysis Checks via output (1ES PT)" task runs `sdlBinaryAnalysisChecks.ps1`. This script **unconditionally updates Windows Defender signatures** before checking whether scanning is actually needed. Even with `binskim.enabled: false` and `antimalwareScan.enabled: false`, the Defender update still runs.

- **Cold Windows agent**: 3-6 minutes per job just for signature downloads
- **Warm Windows agent**: 25-60 seconds
- **Linux agent**: The equivalent `sdlBinaryAnalysisCombinedPreChecks.ps1` correctly reads the disabled flags and skips in ~2 seconds

To confirm this, fetch the log for a slow SDL task and look for:
```
Updating Windows Defender signatures
MpCmdRun.exe -SignatureUpdate
```

**There is no user-controllable variable to skip this.** It's a bug in the 1ES PT Windows implementation tracked in [Bug 2383594](https://dev.azure.com/mseng/1ES/_workitems/edit/2383594). Mitigation options:
- Track the bug for an upstream fix
- Move jobs from `pool: type: windows` to `pool: type: linux` where possible
- Accept the overhead on jobs that must stay on Windows

### Step 8 — Check for Copa/Container Patching

Copa (Container Patching) can add 15-20+ minutes by scanning and patching container images for OS-level vulnerabilities. Look for it in two places:

**In the YAML** — check `featureFlags`:
```yaml
featureFlags:
  automaticContainerPatching: false  # Set to false to disable
```

**In the build timeline** — look for Copa-related tasks:
```powershell
$copaTasks = $timeline.records | Where-Object { $_.name -like "*copa*" -or $_.name -like "*patch*" -or $_.name -like "*container patch*" }
```

Copa is unnecessary for PR builds because the container images are not deployed. Disabling it with `automaticContainerPatching: false` can cut build times by up to ~45% when Copa is on the critical path, and always frees compute capacity even when it isn't.

### Step 9 — Analyze Docker Builds

If the pipeline builds Docker images, read the Dockerfile(s) AND the build command:

1. **Find Dockerfiles**: `Get-ChildItem -Recurse -Filter "Dockerfile*"`
2. **Read each Dockerfile** — look for:
   - Number of `FROM` stages (multi-stage builds)
   - Heavy `RUN` commands: `apt-get install`, `npm install`, `dotnet restore`, `pip install`
   - Whether dependencies are installed before source code is copied (layer caching optimization)
   - Duplicate work across stages
3. **Find the docker build command** in the pipeline YAML or templates — look for `docker build` and check flags:
   - `--no-cache` — forces full rebuild. On ephemeral CI agents the local cache is empty anyway, so this flag has no effect on its own. But it also **prevents `--cache-from` from working**, which blocks registry-based caching.
   - `--pull` — forces re-pull of base images (usually fine, adds a few seconds)
   - `--cache-from` — enables registry-based layer caching (recommended)
4. **Read the Docker build log** to see actual step timings — each Dockerfile step is logged with timing

**Optimization opportunities**:
- Remove `--no-cache` and add `--cache-from <registry>/<image>:cache` for registry-based caching
- Reorder Dockerfile: `COPY package.json` → `RUN npm install` → `COPY . .` (so source changes don't bust the npm cache)
- Consolidate sequential `RUN` commands into single layers
- Pre-build base images containing stable dependencies (OS packages, SDKs, CLI tools), update weekly
- Remove unused packages (e.g., `mono-complete` if no longer needed)

### Step 10 — Check for Unnecessary Work in PR Builds

Compare the PR pipeline to the Official/Release pipeline. PR builds should be leaner:

- **ARM/Bicep template validation** — does the PR build need full Armory validation, or is a syntax check sufficient?
- **Multiple environment builds** — PR only needs one, not dev/test/prod
- **Integration tests** — should run in a separate pipeline, not block PR checks
- **Full SDL suite** — many SDL checks can be deferred to Official builds
- **Duplicate .NET restores/builds** — if multiple jobs build the same solution, consider building once and sharing artifacts

### Step 11 — Present Findings

Summarize findings with data from the actual build. Use a table with both wall-clock and capacity impact:

| Optimization | Current Time | Wall-Clock Savings | Compute Capacity Freed | How to Fix | Risk |
|-------------|-------------|-------------------|----------------------|------------|------|
| (Fill from actual analysis) | | | | | |

**Important framing:** Always recommend disabling SDL in PR builds regardless of whether it's on the critical path. The rationale:
- **If SDL is on the critical path:** Both wall-clock time AND compute capacity are saved (expect 15–45% build time reduction)
- **If SDL is NOT on the critical path:** Compute capacity is still freed (CPU, memory, I/O) even though wall-clock time doesn't change. In capacity-constrained pools with increasing AI-generated PR volume, this freed capacity allows more concurrent builds without provisioning new agents.

Official/Release builds always run full SDL before deployment, so PR-level SDL provides no security value — it only catches issues earlier in the feedback loop at the cost of developer wait time and compute resources.

Include specific build IDs, task names, and durations as evidence.

### Step 12 — Trend Analysis

Compare builds over time to measure improvements:

```powershell
$builds = (Invoke-RestMethod -Uri "$org/$project/_apis/build/builds?definitions=$definitionId&statusFilter=completed&resultFilter=succeeded&`$top=100&minTime=$((Get-Date).AddDays(-14).ToString('o'))&api-version=7.1" -Headers $headers).value
$builds | Group-Object { ([datetime]$_.startTime).ToString("yyyy-MM-dd") } | Sort-Object Name | ForEach-Object {
    $durations = $_.Group | ForEach-Object { ([datetime]$_.finishTime - [datetime]$_.startTime).TotalMinutes }
    $sorted = $durations | Sort-Object
    $median = $sorted[[math]::Floor($sorted.Count / 2)]
    $avg = [math]::Round(($durations | Measure-Object -Average).Average, 1)
    Write-Host "$($_.Name) | $($_.Count) builds | median $([math]::Round($median, 1))m | avg ${avg}m"
}
```

Use this to show before/after impact of changes.

### Step 13 — Investigate MSBuild STDIO Hangs

PR builds on OneBranch can randomly hang for hours. The root cause is often RoslynAnalyzers@3 (Guardian Dotnet Analyzers) spawning analyzer host processes that inherit STDIO handles, keeping the pipeline step alive indefinitely.

**Detection**: First, check whether this issue affects the pipeline:

1. Look for builds with abnormally long durations (4h, 8h, 19h) in the build history from Step 3.
2. If suspicious builds exist, fetch the job logs and search for STDIO-related warnings such as:
   ```
   ##[warning]The STDIO streams did not close within 10 seconds of the exit event from process 'dotnet.exe'. This may indicate a child process inherited the STDIO streams and has not yet exited.
   ```
3. If no long-running builds or STDIO warnings are found, **skip this step**.

**Fix** (only if STDIO warnings are confirmed): Add `-nodeReuse:false -p:UseSharedCompilation=false` to all `dotnet build`, `dotnet publish`, and `dotnet test` steps:

```yaml
- task: DotNetCoreCLI@2
  inputs:
    command: build
    arguments: '-nodeReuse:false -p:UseSharedCompilation=false'
```

> **Gotcha**: The `--disable-build-servers` flag doesn't work with DotNetCoreCLI@2 on .NET 6 SDK (only supported in .NET 7+).

### Step 14 — Check for RoslynAnalyzers on Container Prep Builds

RoslynAnalyzers@3 can cause STDIO warnings and 60+ second delays on publish steps for container prep builds (e.g., ContentScrubber, DocfxFileSanitizer). These builds don't need SDL Roslyn analysis.

**Fix**: Replace `RoslynAnalyzers@3` with plain `DotNetCoreCLI@2` (command: build) in container prep templates. This can drop publish steps from ~61s to ~1.5s each.

### Step 15 — Eliminate Unnecessary Zip Packaging

If container artifacts are zip-packaged in CI and then unzipped in the Dockerfile, the packaging step is unnecessary overhead.

**Fix**: Add `zipAfterPublish: false` to `dotnet publish` tasks for container artifacts. Use `dotnet publish` directly in Dockerfile build scripts. Remove `unzip`/`rm` commands from Dockerfiles.

### Step 16 — Remove Redundant SDL Variable Overrides

OneBranch pipelines often accumulate redundant per-job `ob_sdl_*` variable overrides that match the defaults (e.g., `ob_sdl_binskim_break: true`). These add noise without changing behavior.

**Fix**: Audit all `ob_sdl_*` variables across pipeline files. Remove any that match the default values. Also remove redundant `ob_git_checkout: true` and empty `variables:` sections.

## Reference

For real-world results, gotchas, and key principles, see [references/results.md](references/results.md).
