# Real-World Results

## EngineeringHub (Origin Pipeline)

These optimizations were first validated on the EngineeringHub OneBranch pipeline, reducing median build time from ~50 minutes to ~27 minutes with a 0% hang rate (down from 27%):

| # | Change | Before | After | Improvement |
|---|--------|--------|-------|-------------|
| 1 | Disable Copa (`automaticContainerPatching: false`) | 48m median | 27m median | ~45% faster |
| 2 | Disable BinSkim + Antimalware (`globalSdl`) | 14 BinSkim tasks, 115s MDE scans | 0 BinSkim tasks, 1s no-ops | Minutes saved across parallel jobs |
| 3 | Disable MDE Linux Scanner (`EnableDefenderForLinux: false`) | Scanner injected on all Linux jobs | No scanner | Seconds per job |
| 4 | Fix MSBuild STDIO hang (`-nodeReuse:false`) | 27% hang rate (4–19h) | 0% hang rate | Hangs eliminated |
| 5 | Replace RoslynAnalyzers@3 for container preps | ~61s per publish step | ~1.5s per publish step | ~97% faster per step |
| 6 | Eliminate zip packaging for containers | Zip + unzip overhead | Direct publish | Reduced I/O and Dockerfile complexity |
| 7 | Remove redundant SDL variable overrides | 235 lines of redundant config | Clean config | Maintainability |
| 8 | 1ES PT Windows Defender bug ([Bug 2383594](https://dev.azure.com/mseng/1ES/_workitems/edit/2383594)) | +1–6m per Windows job | N/A | No user fix available |

## Multi-Repo Validation (May 2026)

The skill was applied to 7 additional repositories across Azure Core. Results below show both wall-clock savings and compute capacity freed:

| Repo | Changes Applied | Wall-Clock Savings | Compute Freed/Mo | Notes |
|------|----------------|-------------------|-------------------|-------|
| **Azure-Compute-ResourceCentral** | SDL disable (BinSkim + AntiMalware) + hang prevention | **−23.6 min/build (39%)** | **~118 hrs/mo** | SDL was on critical path — strongest result |
| **EngSys-Performance-CirrusContent** | SDL disable + shallow clone + CG disable | **−8.4 min/build (16%)** | **~100 hrs/mo** | SDL + clone overhead removed from parallel jobs |
| **Azure-Compute-AzAllocator** | SPMI disable + skip redundant build + hang prevention | **−14.6 min/build (predicted)** | ~37 hrs/mo | Hang prevention + SPMI removal |
| **Azure-Common** | SDL disable + hang prevention | ~72s/build | ~1 hr/mo | Small pipeline; hang prevention is primary value |
| **Networking-Madari** | UseSharedCompilation=false on Official | Prevents 241-min hangs | ~10 hrs/mo saved | Reliability: eliminates VBCSCompiler hang events |
| **Compute-Fabric-HostAgent** | SDL disable + Copa prevention | −3–11 min/build | ~10 hrs/mo | Large test suite dominates; SDL runs in parallel |
| **aks-rp** | Copa + MDE disable on Buddy pipeline | Minimal | — | Go monorepo; Buddy pipeline low-frequency |

**Aggregate impact across 7 repos: ~275+ hrs/mo compute capacity freed**

### Key Insight: Wall-Clock vs Compute Capacity

Even when SDL is not on the critical path (e.g., HostAgent where tests take 180+ min), disabling it in PR builds still frees compute capacity — CPU, memory, and I/O that can serve other builds. In a capacity-constrained world with increasing PR volume from AI agentic adoption, this allows more builds to run concurrently on the same infrastructure.

**When SDL IS the critical path** (ResourceCentral, CirrusContent): Expect 15–45% wall-clock reduction.  
**When SDL is NOT the critical path** (HostAgent, AzAllocator): Expect 0% wall-clock reduction but full compute capacity savings.

Either way, disabling SDL in PR builds is correct — Official builds run full SDL before deployment.

## Gotchas Discovered

These are non-obvious pitfalls found through source code reading, not documentation:

1. **Copa**: Pipeline-level `variables: enableContainerVulnerabilityPatching: false` does NOT work. The 1ES template reads from `parameters.featureFlags`, not pipeline variables.
2. **Antimalware**: The property name is `antimalwareScan`, NOT `antimalware`. The wrong name silently does nothing. Found by reading GovernedTemplates source at `/v2/Core.Template.yml`.
3. **MDE Linux Scanner**: Controlled by `featureFlags.EnableDefenderForLinux`, found at GovernedTemplates source line 1167–1170.
4. **MSBuild hang**: `--disable-build-servers` only works on .NET 7+ SDK. For .NET 6, use `-nodeReuse:false -p:UseSharedCompilation=false` instead.
5. **Component Governance**: Must be disabled via `globalSdl.cg.enabled: false`, NOT as an `ob_sdl_cg_enabled` job variable.
6. **Shallow clone**: Use `ob_git_fetchDepth: 1` as a job-level variable. The `globalSdl` section does NOT control git fetch depth.
7. **SPMI**: Disable per-job with `ob_sdl_spmi_enabled: false` in the job's variables block (not in globalSdl).

## Key Principles

1. **Read the source, don't guess** — always read the pipeline YAML, templates, Dockerfiles, and actual task logs before making recommendations
2. **Focus on the critical path** — parallel jobs don't affect wall-clock time; find the serial bottleneck
3. **PR builds need speed, not completeness** — defer heavy validation (Copa, full SDL, integration tests) to Official builds
4. **Measure before and after** — use the trend analysis with real build data to prove improvements
5. **Linux > Windows for 1ES PT overhead** — Windows agents waste minutes on Defender signature updates even when scanning is disabled
6. **Distinguish user-controlled vs 1ES-injected** — `globalSdl` controls Guardian tasks; 1ES PT injects its own tasks that ignore these flags on Windows
7. **Read the 1ES GovernedTemplates source** — documentation is often incomplete or wrong; the template source code is the ground truth for feature flag names and behavior
8. **Pre-built images beat runtime installs** — bake stable dependencies into base images updated weekly rather than installing them every build
9. **Always disable SDL in PR builds** — even when SDL is not on the critical path, it consumes compute capacity (CPU, memory, I/O) that could serve other builds. Official builds enforce SDL before deployment regardless
10. **Frame savings as capacity** — in a compute-constrained world with growing AI-generated PR volume, freed capacity = more builds without provisioning new agents
