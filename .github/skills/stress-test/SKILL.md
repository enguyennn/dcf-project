---
name: stress-test
description: |
  Stress test execution skill for validating test-hardening stability-by-design edits. Automatically activated when users request any of these tasks:
  - Queue a stress test ("run stress test", "queue stress test", "validate my hardening edits")
  - Verify hardening stability ("check if the edits are stable", "test for intermittent failures")
  - Run tests multiple times ("run tests repeatedly", "stress the test")
---

# Stress Test Skill

This skill provides guidance for running stress tests to verify that test-hardening stability-by-design edits are stable and the test doesn't fail intermittently under repeated execution. It supports two modes: **cloud** (via `queue_stress_test` MCP tool) and **local** (via repeated `dotnet test` execution).

## Prerequisites

Before running a stress test:
- Local build and test execution must complete successfully
- The target test must be **QTest**; skip the entire stress-test skill if it is **CloudTest**

## Steps

### 1. Prepare for Stress Test

Before running the stress test:
- **Verify local success**: Confirm the test passes locally before stress testing

### 2. Select Stress Test Mode

**Decision Rule:**
- If the `queue_stress_test` MCP tool (from `deflaker`) is **available and the repository is configured for cloud builds** → Use **Cloud Mode** (Step 3)
- If the `queue_stress_test` MCP tool is **unavailable**, or the repository is not configured for cloud builds → Use **Local Mode** (Step 4)

### 3. Cloud Mode — Queue Remote Stress Test

Use the `queue_stress_test` MCP tool to queue a stress test for the test project.

**Tool:** `queue_stress_test`

**Required Parameter:**
- `TestName`: The name of the test (e.g., `MyNamespace.MyTestClass.MyTestMethod`)
- `StressTestPath`: The path to the test project directory (e.g., `src\Services\DatacenterPlatform\OneMosAgent\UnitTests`)

**What the Tool Does:**
1. Creates a temporary branch with the local changes
2. Queues a CloudBuild job that runs the tests multiple times to detect flakiness
3. Returns a link to monitor the stress test results

**Notify the user**: Ask the user to avoid making any local changes while the stress test is being queued.

After the stress test is successfully queued, inform the user and provide a response similar to:
```
Stress test queued successfully!
Build URL: https://cloudbuild.microsoft.com/build/a856f369-7d4c-4153-87ba-3e4b552ba078?bq=azure_one_compute
Test Configuration:
- Queue: azure_one_compute
- Test Path: src\Services\DatacenterPlatform\OneMosAgent\UnitTests
- Repository: Azure-Compute
```

### 4. Local Mode — Run Tests Repeatedly

When cloud stress testing is unavailable, run the test multiple times locally to verify stability.

#### 4.1. Locate the Test Project

Identify the `.csproj` file for the test project containing the hardened test method.

#### 4.2. Run the Stress Loop

Execute the test repeatedly (default: 5 iterations). All iterations must pass for the fix to be considered stable.

**PowerShell Command:**
```powershell
$testProject = "<path-to-test-project.csproj>"
$testFilter = "<TestMethodName>"
$iterations = 5
$failures = 0

for ($i = 1; $i -le $iterations; $i++) {
    Write-Host "--- Iteration $i of $iterations ---"
    dotnet test $testProject --filter $testFilter --no-build
    if ($LASTEXITCODE -ne 0) { $failures++ }
}

Write-Host "`n--- Stress Test Summary ---"
Write-Host "Total iterations: $iterations"
Write-Host "Passed: $($iterations - $failures)"
Write-Host "Failed: $failures"
if ($failures -eq 0) { Write-Host "Result: STABLE" } else { Write-Host "Result: UNSTABLE - $failures/$iterations iterations failed" }
```

- Replace `<path-to-test-project.csproj>` with the actual test project path.
- Replace `<TestMethodName>` with the test method name.

#### 4.3. Interpret Results

| Outcome | Action |
|---------|--------|
| All iterations pass (STABLE) | Hardening edit is verified; proceed to next workflow step |
| Any iteration fails (UNSTABLE) | Hardening edit is insufficient; revert the failing stability-by-design finding(s) and report |

#### 4.4. Report Results

Provide the user with the stress test summary including:
- Number of iterations run
- Pass/fail count
- Overall verdict (STABLE or UNSTABLE)

#### 4.5. Parallel Local Mode (Optional)

When the local stress run takes long enough to bottleneck the wall-clock — typically **≥ 5 iterations** with each iteration **≥ 10 s** — issue the iterations as **parallel processes** instead of serially. Each `dotnet test` / `pytest` / `vitest run` invocation runs in its own process, so iterations have no shared in-process state.

**Use this when:**
- Iteration count × per-iteration time exceeds the developer's patience window.
- The runner spawns a fresh process per invocation (default for `dotnet test`, `pytest`, `vitest run`, `go test`).

**Do NOT use this when:**
- The runner shares one process across iterations (e.g., `dotnet test --blame-hang` with a hosted runner, or any `--repeat` flag that re-enters the same process).
- The test method depends on a **shared external resource** that cannot tolerate concurrent access: hard-coded port number, fixed temp file path, exclusive DB row, named-pipe / mutex.
- The host machine is resource-starved (< 4 physical cores, or < 50% free RAM relative to one iteration's footprint).

**PowerShell 7+ pattern (preferred):**

```powershell
$testProject = "<path-to-test-project.csproj>"
$testFilter  = "<TestMethodName>"
$iterations  = 5
# Throttle to physical core count; oversubscribing increases context-switch noise.
$throttle    = [Math]::Max(2, [Environment]::ProcessorCount / 2)

$results = 1..$iterations | ForEach-Object -Parallel {
    $i = $_
    Write-Host "--- Iteration $i started ---"
    & dotnet test $using:testProject --filter $using:testFilter --no-build *>&1 | Out-Null
    [PSCustomObject]@{ Iteration = $i; ExitCode = $LASTEXITCODE }
} -ThrottleLimit $throttle

$failures = ($results | Where-Object { $_.ExitCode -ne 0 }).Count
Write-Host "`n--- Parallel Stress Test Summary ---"
Write-Host "Iterations:  $iterations"
Write-Host "Throttle:    $throttle (parallel processes)"
Write-Host "Passed:      $($iterations - $failures)"
Write-Host "Failed:      $failures"
if ($failures -eq 0) { Write-Host "Result: STABLE" } else { Write-Host "Result: UNSTABLE - $failures/$iterations iterations failed" }
```

**PowerShell 5.1 fallback (when `ForEach-Object -Parallel` is unavailable):**

```powershell
$jobs = 1..$iterations | ForEach-Object {
    Start-Job -ScriptBlock {
        param($project, $filter)
        & dotnet test $project --filter $filter --no-build
        $LASTEXITCODE
    } -ArgumentList $testProject, $testFilter
}
$exitCodes = $jobs | Receive-Job -Wait -AutoRemoveJob
$failures = ($exitCodes | Where-Object { $_ -ne 0 }).Count
```

**Acceptance** is unchanged: the same **100 % pass-rate** target defined in [`stress-validation-protocol`](../stress-validation-protocol/SKILL.md) applies. Parallel execution does not relax the threshold — it only reduces the wall-clock cost of reaching it. If any one iteration fails, the run is `stress-failed` and the offending stability-by-design finding(s) are reverted per the protocol's partial-revert rules.

**Reporting note.** Record `parallel-throttle: <N>` in the stress summary alongside iteration count so the developer can reproduce. Add it to the PR description's stress block when present.

## Rules

### Test Eligibility
- ✅ Only run for **QTest**
- ❌ Skip entirely for **CloudTest**

### User Communication
- **Warn before queuing (cloud mode)**: Always inform the user not to make local changes while queuing
- **Provide tracking link (cloud mode)**: Always return the CloudBuild URL for monitoring
- **Show progress (local mode)**: Display iteration count and pass/fail status during execution

### Stress Test Execution
- **Run after local success**: Only run stress tests after local build and tests pass
- **Single execution**: Run one stress test at a time
- **Monitor results**: Provide the URL (cloud) or summary (local) so users can assess stability

### PR Integration
- **Document in PR**: Recommend adding stress test results (cloud URL or local summary) to the PR description
- **Reviewer validation**: Reviewers can use the evidence to verify fix stability

## Failure Handling

| Scenario | Action |
|----------|--------|
| `queue_stress_test` tool unavailable | Fall back to Local Mode (Step 4) |
| Authentication Issues with Azure DevOps | Report the error and fall back to Local Mode |
| Tool fails to queue a stress test | Report the error and fall back to Local Mode |
| Local tests not passing | Do not run stress test; fix local issues first |
| Branch creation fails (cloud mode) | Report the error with details |
| Local stress test shows failures | Report failure details; fix is insufficient |

## Tips

- Add the stress test results (cloud URL or local summary) to the PR description for reviewers to validate the fix stability
- For local mode, 5 iterations is the default; increase to 10+ for higher confidence if time permits
