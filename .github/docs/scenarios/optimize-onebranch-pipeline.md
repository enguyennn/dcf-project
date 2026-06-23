# Optimize OneBranch Pipeline

Analyze and optimize OneBranch PR pipeline build times. This skill reads your pipeline YAML, fetches real build timelines from Azure DevOps, and identifies concrete opportunities to reduce CI wall-clock time.

## When to Use

- Your OneBranch PR pipeline takes more than 20-30 minutes
- PR builds are randomly hanging for hours
- You want to reduce CI overhead without compromising release-time security
- You're seeing slow SDL or Copa tasks in your build timeline
- You want to understand where time is spent in your OneBranch pipeline

## Prerequisites

- **Azure CLI** -- must be installed and authenticated (`az login`)
- **Azure DevOps access** -- read access to the repository and pipeline builds

## Workflows

1. **Read pipeline YAML** -- the skill reads your PR pipeline YAML, identifies the 1ES template, `globalSdl` settings, `featureFlags`, job pools, and dependency chains
2. **Fetch build data** -- authenticates to Azure DevOps and pulls recent build timelines with job- and task-level durations
3. **Analyze the critical path** -- identifies the longest chain of dependent jobs and the serial bottleneck
4. **Inspect slow tasks** -- for the slowest jobs, breaks down every task and fetches logs for suspicious ones
5. **Identify unnecessary PR checks** -- compares PR pipeline to Official/Release pipeline and flags checks that can be deferred (Copa, SDL, MDE scanner, etc.)
6. **Detect build hangs** -- looks for RoslynAnalyzers@3 STDIO hang patterns and recommends MSBuild flags
7. **Present findings** -- produces a summary table with current time, estimated savings, fix instructions, and risk level

## Example Prompts

```text
# General optimization request
My OneBranch PR pipeline is slow, can you help speed it up?

# Targeted analysis
Analyze the build times for pipeline definition 12345 in msazure/One

# Investigate hangs
Our PR builds keep hanging for hours, what's causing it?

# Check for Copa overhead
Is Copa container patching adding time to our PR builds?

# Compare before and after
Show me the build time trend for the last 2 weeks after we disabled Copa
```

## Expected Output

The skill produces a **findings table** with actionable recommendations:

| Optimization | Current Time | Estimated Savings | How to Fix | Risk |
|-------------|-------------|-------------------|------------|------|
| Disable Copa | 39.5m cumulative | ~22m | `featureFlags.automaticContainerPatching: false` | Low -- PR images aren't deployed |
| Disable BinSkim | 14 tasks, ~2m each | ~28m cumulative | `globalSdl.binskim.enabled: false` | Low -- runs in Official builds |
| Fix MSBuild hang | 27% hang rate | Eliminates hangs | `-nodeReuse:false -p:UseSharedCompilation=false` | None |

Each recommendation includes the specific YAML change, evidence from actual build data, and risk assessment.

## Current Capabilities

**Remove unnecessary PR checks** -- PR builds don't need the same rigor as Official/Release builds. This skill identifies checks that can be safely deferred to Official builds, including:

- **Copa container patching** -- scans and patches container images for OS-level vulnerabilities. Unnecessary for PR builds since images aren't deployed. Disabling `automaticContainerPatching` has shown ~45% build time reduction in production pipelines.
- **SDL overhead on Windows agents** -- the 1ES Pipeline Template unconditionally updates Windows Defender signatures even when BinSkim and antimalware scanning are disabled, adding 1-6 minutes per Windows job. The skill identifies affected jobs and recommends moving them to Linux where feasible.
- **Redundant SDL checks** -- identifies `globalSdl` settings that can be relaxed for PR validation without compromising release-time security scanning.
- **MDE Linux Scanner** -- identifies and disables the Microsoft Defender for Endpoint scanner injected on all Linux Docker jobs via `EnableDefenderForLinux`.
- **MSBuild STDIO hangs** -- detects the RoslynAnalyzers@3 hang pattern where analyzer host processes inherit STDIO handles, causing builds to hang for hours. Recommends `-nodeReuse:false -p:UseSharedCompilation=false`.
- **RoslynAnalyzers on container preps** -- identifies container prep builds (ContentScrubber, DocfxFileSanitizer, etc.) running unnecessary SDL Roslyn analysis, adding 60+ seconds per publish step.
- **Unnecessary zip packaging** -- spots container artifacts being zip-packaged in CI then unzipped in Dockerfiles, recommending `zipAfterPublish: false`.
- **Redundant SDL variable overrides** -- finds per-job `ob_sdl_*` variables that match defaults and can be removed to reduce config noise.

The skill documents non-obvious gotchas discovered through 1ES GovernedTemplates source code reading (e.g., `antimalwareScan` vs `antimalware` property name, Copa requiring `parameters.featureFlags` not pipeline variables).

## Future Roadmap

This skill is designed to grow into a comprehensive OneBranch pipeline optimization toolkit:

- **Docker layer caching** -- analyze Dockerfiles and build commands, recommend `--cache-from` registry-based caching and optimal layer ordering
- **Critical path analysis** -- map job dependency chains to identify the serial bottleneck and recommend parallelization
- **Trend analysis** -- track build times over days/weeks to measure the impact of changes and detect regressions
- **Pre-built base images** -- recommend extracting stable dependencies into weekly-rebuilt base images instead of installing at build time
- **Task-level log analysis** -- automatically fetch and analyze logs for slow tasks to find hidden time sinks

## Real-World Results

Validated on the EngineeringHub OneBranch pipeline -- median build time dropped from ~50m to ~27m, hang rate from 27% to 0%:

| Change | Before | After | Improvement |
|--------|--------|-------|-------------|
| Disable Copa (`automaticContainerPatching: false`) | 48m median | 27m median | ~45% faster |
| Disable BinSkim + Antimalware (`globalSdl`) | 14 BinSkim tasks, 115s MDE scans | 0 tasks, 1s no-ops | Minutes saved |
| Disable MDE Linux Scanner | Scanner on all Linux jobs | No scanner | Seconds per job |
| Fix MSBuild STDIO hang | 27% hang rate (4-19h) | 0% hang rate | Hangs eliminated |
| Replace RoslynAnalyzers for container preps | ~61s per publish step | ~1.5s | ~97% faster |
| Eliminate zip packaging | Zip + unzip overhead | Direct publish | Reduced I/O |
| Remove redundant SDL overrides | 235 lines | Clean config | Maintainability |
| 1ES PT Windows Defender bug (unresolved) | +1-6m per Windows job | N/A | No user fix |
