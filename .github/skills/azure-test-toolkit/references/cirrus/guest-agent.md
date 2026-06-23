# guest-agent

**Schema:** 1
**Description:** Azure Performance Guest Agent (GuestAgent) workload testing on real Azure fabric nodes via Cirrus orchestration. Covers VM-resident .NET Core service (`azperf`) that downloads NuGet packages from the `EngSys-Performance-GuestAgent` feed, orchestrates workload phases (Setup → Workload → Cleanup), and uploads results via the AppInsights → EventHub → Kusto pipeline. Supports Windows + Linux with RuntimeId matching (win-x64, linux-x64, linux-arm64, ubuntu-x64, centos-x64).

## Defaults

| Key | Value |
|-----|-------|
| `cirrus_tenant` | `<your-cirrus-tenant>` |
| `subscription_id` | `<your-cirrus-subscription-id>` |

These are used when the developer's `octane.yaml` does not specify values for the guest-agent test type.

## Workload Types

GuestAgent supports a variety of performance and reliability workloads, all orchestrated through JSON `.workload.json` files deployed as NuGet packages:

| Workload | Description | Perf Data | Kusto Upload | Reliability |
|----------|-------------|-----------|--------------|-------------|
| **FIO** | Disk I/O benchmarks (sequential/random read/write) | Yes | No | Yes |
| **DiskSpeed** | Disk performance measurement | Yes | No | Yes |
| **DiskSpeed + Kusto** | Disk performance with telemetry upload | Yes | Yes | Yes |
| **HammerDB** | Database workload (TPC-C/TPC-H benchmarks) | Yes | Yes | Yes |
| **CloudDB** | In-memory database workload | Yes | Yes | Yes |
| **DDA-GPU** | GPU performance (DirectDevice Assignment) | Yes | — | Yes |
| **DDA-NVMe** | NVMe performance (DirectDevice Assignment) | Yes | Yes | Yes |
| **Clairvoyance + Jitter** | Guest CPU cycle measurement | Yes | Yes | No |
| **ACC Suite** | Hardware/ACC validation | — | Yes | No |
| **IndexServe** | Bing search workload | Yes | — | Yes |
| **Athena** | Workload execution infrastructure | Yes | No | — |

### Workload JSON Structure

Workloads are defined in `.workload.json` files with this structure:

```json
{
  "Requires": {
    "Packages": [{"Name": "package-name", "Version": "[1.0,2.0)"}],
    "RuntimeId": "linux-x64"
  },
  "Phases": {
    "Setup": { "Tasks": [{"Description": "", "Command": "", "Arguments": "", "Timeout": "DD.HH:MM:SS"}] },
    "Workload": { "Repetitions": 1, "TaskOrder": "sequential", "MaxDuration": "DD.HH:MM:SS", "Tasks": [] },
    "Cleanup": { "Tasks": [] },
    "Reboot": { }
  }
}
```

> **Note:** Cleanup and Reboot phases are **NYI (Not Yet Implemented)** — defining them in a workload file has no effect. Setup and Workload are the only active phases.

### Task Fields

Each task in Setup/Workload phases supports:

| Field | Description | Required |
|-------|-------------|----------|
| `Description` | Human-readable task name | No |
| `RequiresRuntime` | Only run this task on matching RuntimeId | No |
| `Command` | Executable to run (e.g., `bash`, `python3`, `fio`) | Yes |
| `Arguments` | Command arguments | No |
| `WorkingDirectory` | Working dir for the command | No |
| `Timeout` | Hard timeout, format: `DD.HH:MM:SS.MS` (default: `Timespan.MaxValue`) | No |

### Package Environment Variables

When workloads reference NuGet packages, GuestAgent sets environment variables for package paths:

```
PKG_RUNTIME_{NormalizedName}  → points to runtimes/{RuntimeId}/ directory
PKG_ROOT_{NormalizedName}     → points to package root directory
```

Normalization: `PackageName.ToUpperInvariant().Replace(".", "_").Replace("-", "_")`

Example: Package `My.Workload-Tools` → `PKG_RUNTIME_MY_WORKLOAD_TOOLS`, `PKG_ROOT_MY_WORKLOAD_TOOLS`

### RuntimeId Matching

GuestAgent selects binaries based on the VM's OS and architecture:

| RuntimeId | Platform |
|-----------|----------|
| `win-x64` | Windows x64 |
| `linux-x64` | Generic Linux x64 |
| `linux-arm64` | Linux ARM64 |
| `ubuntu-x64` | Ubuntu-specific x64 |
| `centos-x64` | CentOS-specific x64 |

### TestType Definitions in CirrusContent

- `src/CirrusTenants/HostValidation/TestTypes/GuestAgent_Windows.TestType.json`
- `src/CirrusTenants/HostValidation/TestTypes/GuestAgent_Linux.TestType.json`

### Deployment Methods

| Method | Description | When to use |
|--------|-------------|-------------|
| **Via Cirrus** (primary) | TestPassDefinition2 with `TestTypePath` pointing to GuestAgent TestType JSON | Production test passes |
| **Local/Standalone** | Download zip from NuGet feed, run `install.sh` (Linux) or `install.cmd` (Windows) | Local dev/debug |
| **PowerShell** | `InstallGuestAgentToVM.ps1` script | Manual VM setup |

### Deep Links

| Link | Pattern | When to show |
|------|---------|-------------|
| **Cirrus Portal (Test Pass)** | `https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/{TestPassId}` | When you have a TestPassId |
| **Cirrus Portal (RunSet)** | `https://cirrusperf.azurewebsites.net/v1/query?key={RunSetId}&type=RunSetId` | When investigating CER by RunSet |
| **Jarvis GuestAgent Dashboard** | `https://portal.microsoftgeneva.com/dashboard/cirrus/GuestAgent/Prod` | For overall GuestAgent health |
| **NuGet Feed** | `https://msazure.pkgs.visualstudio.com/_packaging/EngSys-Performance-GuestAgent/nuget/v3/index.json` | When debugging package issues |
| **AppInsights Logs** | `https://ms.portal.azure.com/...engsys-performance-guestagent/logs` | When Kusto logs are missing or delayed |
| **ADO Build Pipeline** | `https://dev.azure.com/msazure/One/_build/results?buildId={AdoBuildId}&view=results` | When investigating build issues |

KQL to generate deep links from query results:
```kql
| extend CirrusURL = strcat("https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/", TestPassId)
| extend RunSetURL = strcat("https://cirrusperf.azurewebsites.net/v1/query?key=", RunSetId, "&type=RunSetId")
| extend ADOBuildPipelineURL = strcat("https://dev.azure.com/msazure/One/_build/results?buildId=", AdoBuildId, "&view=results")
```

### Test Execution Flow

1. **NuGet package published** → Workload packaged and pushed to `EngSys-Performance-GuestAgent` feed
2. **Cirrus launch** → `Start-CirrusTestPassRequest` with GuestAgent TestType → `ApiAttempt` records the launch
3. **TiP session created** → `EnvironmentSelection` logs cluster selection → `EnvironmentEvent` records session
4. **Agent deployed** → `azperf` service installed on target VM; downloads workload NuGet packages
5. **Workload phases execute** → Setup → Workload (N repetitions) → Cleanup → optional Reboot
6. **Results uploaded** → AppInsights → EventHub → Kusto (`WorkflowDb`) — `GuestAgentTraces`, `GuestAgentMetrics`, `GuestAgentFileUploads`

## Multi-Cluster Data Sources

GuestAgent queries span multiple Kusto clusters. The MCP `kusto_query` tool accepts `cluster-uri` and `database` per call. For Cirrus, AzureCM, and TipNodeService clusters, see provider.md Common Tables.

| Alias | Cluster URI | Database | What it has |
|-------|------------|----------|-------------|
| **WorkflowDb** | `https://cirrus.kusto.windows.net` | `WorkflowDb` | GuestAgent-specific telemetry — traces, events, metrics, file uploads (`GuestAgentTraces`, `GuestAgentEvents`, `GuestAgentMetrics`, `GuestAgentFileUploads`) |

Unless noted, queries target the **Cirrus** cluster/database (inherited from provider.md). GuestAgent-specific queries target **WorkflowDb** and are explicitly marked.

---

<!-- PRIMITIVE:Build -->
#### Build

**Status:** passthrough
**Reason:** 🚧 Under construction — Azure Test Platform is working to make Build happen! NuGet package build/push workflow will be defined after validating with the GuestAgent team.

---

<!-- PRIMITIVE:Run -->
#### Run

**Status:** passthrough
**Reason:** 🚧 Under construction — Azure Test Platform is working to make Run happen! GuestAgent test launch (TestTypePath referencing GuestAgent TestType JSONs) will be defined in a future version.

---

<!-- PRIMITIVE:Observe -->
#### Observe

**Extends:** provider
**Data Source:** Multiple clusters — see Multi-Cluster Data Sources above

GuestAgent extends the platform Observe (ApiAttempt, GetTestPassCompletionFailures) with WorkflowDb telemetry for workload phase tracking, agent traces, performance metrics, and file upload status.

##### Result Granularity

GuestAgent results are per-workload-phase, not per-test-case:

| Phase | What it covers | Key signals |
|-------|---------------|-------------|
| **Setup** | Package download, dependency installation | Exit codes, timeout, `GuestAgentTraces` with severity=Error |
| **Workload** | Repetitions of workload tasks | `GuestAgentMetrics` values, iteration counts, task durations |
| **Cleanup** | Resource teardown | Exit codes, cleanup completion |
| **Reboot** | Optional VM reboot between iterations | Reboot success, agent restart |

##### Presentation Rules

Extends provider.md Presentation Guidelines with GuestAgent-specific rules:

1. Group test passes by workload type when identifiable from `RequestName` or workload package name.
2. Show workload phase outcomes (Setup/Workload/Cleanup) for each test pass.
3. For performance workloads, surface key metrics from `GuestAgentMetrics` (latency, throughput, IOPS).
4. Show ingestion health — flag if `GuestAgentTraces` are delayed or missing.
5. Include Jarvis dashboard link for overall GuestAgent health context.

##### Query Flow

Provider handles platform queries (ApiAttempt, GetTestPassCompletionFailures). GuestAgent extends with:

1. **Launch inventory** — List recent launches via `ApiAttempt` filtered by `{cirrus_tenant}`, show pass/fail counts and deep links. Always start here.
2. **Workload traces** — For each test pass (or the developer's chosen pass), query `GuestAgentTraces` in WorkflowDb for application logs and error summary.
   - *If empty:* Wait and retry — possible ingestion delay (AppInsights → EventHub → Stream Analytics → Kusto pipeline). Retry after a few minutes before escalating.
3. **Performance metrics** — Query `GuestAgentMetrics` for workload measurement results (latency, throughput, IOPS).
4. **File uploads** — Query `GuestAgentFileUploads` for uploaded artifacts with download URIs.
5. **Ingestion health** — Check ingestion delay between `eventTime` and `TIMESTAMP` in `GuestAgentTraces` to detect pipeline issues.
6. **Trend analysis** — Test pass outcome percentages (weekly) for trend tracking.

##### Queries — WorkflowDb (GuestAgent-specific)

**MCP Parameters:** `cluster-uri: https://cirrus.kusto.windows.net`, `database: WorkflowDb`

```kql
// GuestAgent trace overview — error summary by message and runtime
// Use to identify top error patterns across recent workloads
GuestAgentTraces
| where TIMESTAMP between (ago(1d) .. now())
| where severity == 'Error'
| summarize ErrorCount = count() by message, severity, runtimeId
| order by ErrorCount desc
| take 25
```

```kql
// Traces for a specific Cirrus run — full application log
GuestAgentTraces
| where cirrusRunId == '{cirrus_run_id}'
| project TIMESTAMP, eventTime, severity, message, runtimeId
| order by TIMESTAMP asc
```

```kql
// GuestAgent lifecycle events for a specific run
GuestAgentEvents
| where cirrusRunId == '{cirrus_run_id}'
| project TIMESTAMP, eventTime, eventName
| order by TIMESTAMP asc
```

```kql
// Performance metrics for a specific run
GuestAgentMetrics
| where cirrusRunId == '{cirrus_run_id}'
| project TIMESTAMP, eventTime, metricName, metricValue
| order by TIMESTAMP asc
```

```kql
// File uploads for a specific run — artifacts with download URIs
// NOTE: cirrusRunId is a guid column — wrap the parameter value in quotes
GuestAgentFileUploads
| where cirrusRunId == toguid('{cirrus_run_id}')
| project TIMESTAMP, TaskName, localFileName, downloadUri
| order by TIMESTAMP asc
```

```kql
// Ingestion delay check — detect AppInsights → EventHub → Kusto pipeline lag
GuestAgentTraces
| where TIMESTAMP between (ago(2d) .. now())
| summarize MaxIngestionTime = max(TIMESTAMP), MaxEventTime = max(eventTime)
| extend IngestionDelay = MaxIngestionTime - MaxEventTime
```

```kql
// Workload performance trend — metric averages over time
// Filter by workload name pattern in the request name
// MCP Parameters: cluster-uri: https://cirrus.kusto.windows.net, database: WorkflowDb
GuestAgentMetrics
| where TIMESTAMP between (ago(7d) .. now())
| where metricName in ('{metric_name}') or '{metric_name}' == ''
| summarize AvgValue = avg(metricValue), P95Value = percentile(metricValue, 95),
            MaxValue = max(metricValue), MinValue = min(metricValue)
    by bin(TIMESTAMP, 1d), metricName
| order by TIMESTAMP asc, metricName asc
```

##### Queries — Cirrus Cluster (GuestAgent extensions)

Inherits MCP parameters from provider.md (`cluster-uri: https://cirrus.kusto.windows.net`, `database: cirrus`).

```kql
// Bridge query — map Cirrus TestPassId/RunId to GuestAgent cirrusRunId
// This is essential for crossing from Cirrus platform data into WorkflowDb telemetry
// The Run table's RunGuid maps to GuestAgentTraces.cirrusRunId
Run
| where TIMESTAMP > ago(7d)
| join kind=inner RunSet on RunSetId
| where TestPassId == {test_pass_id}
| project TestPassId, RunSetId, RunId, RunGuid, Description, Status
| order by RunSetId asc, RunId asc
```

```kql
// Enhanced deep-link generator — generate clickable links for each action in a test pass
// Uses bridge query to get RunSetId/ActionId, then constructs portal URLs
Run
| where TIMESTAMP > ago(7d)
| join kind=inner RunSet on RunSetId
| where TestPassId == {test_pass_id}
| extend CirrusActionURL = strcat("https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/", TestPassId, "/runsets/", RunSetId)
| extend CirrusRunSetURL = strcat("https://cirrusperf.azurewebsites.net/v1/query?key=", RunSetId, "&type=RunSetId")
| extend JarvisDashboard = "https://portal.microsoftgeneva.com/dashboard/cirrus/GuestAgent/Prod"
| project TestPassId, RunSetId, RunId, RunGuid, Description, Status,
         CirrusActionURL, CirrusRunSetURL, JarvisDashboard
| order by RunSetId asc, RunId asc
```

---

<!-- PRIMITIVE:Diagnose -->
#### Diagnose

**Extends:** provider

GuestAgent extends the platform Diagnose (ApiAttempt, EnvironmentSelection, CER, AzureCM, TipNodeService) with WorkflowDb diagnostics for workload phase failures, agent health, ingestion pipeline issues, and GuestAgent-specific failure patterns.

##### Diagnostic Flow

Provider handles platform diagnostic steps (launch status, capacity abort, TiP environment, completion, CER, node health, cluster config, TiP quota). GuestAgent extends with:

1. **Identify workload type** → Extract workload name from `RequestName` or package metadata to scope diagnosis
2. **CER drill-down** → Join CER data with build context; map errors to GuestAgent failure patterns
3. **Workload phase analysis** → Query `GuestAgentTraces` filtered by `cirrusRunId` to identify which phase (Setup, Workload, Cleanup) failed and the root cause
4. **Agent health check** → Check for heartbeat/lifecycle events in `GuestAgentEvents`; missing events indicate agent crash or failed startup
5. **Ingestion pipeline diagnosis** → If `GuestAgentTraces` are missing or delayed, check ingestion delay; escalate to AppInsights → EventHub → Stream Analytics pipeline
6. **Daily cap check** → If errors spike, cross-reference with daily cap alerts; identify offending workloads via error volume per `cirrusRunId`
7. **Package/dependency issues** → Check for exit code 127 (command not found), NuGet feed connectivity failures, or version mismatch errors in traces

##### Diagnostic Queries — WorkflowDb (GuestAgent-specific)

**MCP Parameters:** `cluster-uri: https://cirrus.kusto.windows.net`, `database: WorkflowDb`

```kql
// Phase failure analysis — errors grouped by phase for a specific run
// Setup failures indicate package/dependency issues; Workload failures indicate test logic issues
GuestAgentTraces
| where cirrusRunId == '{cirrus_run_id}'
| where severity in ('Error', 'Warning')
| project TIMESTAMP, eventTime, severity, message, runtimeId
| order by TIMESTAMP asc
```

```kql
// Error volume by run — identify top offending runs (daily cap diagnosis)
GuestAgentTraces
| where TIMESTAMP between (ago(1d) .. now())
| where severity == 'Error'
| summarize ErrorCount = count() by cirrusRunId, tostring(split(message, '\n')[0])
| where ErrorCount > 100
| order by ErrorCount desc
```

```kql
// Daily cap offenders — cross-database join to identify tenant/schedule responsible
// Execute from WorkflowDb; uses cross-db reference to cirrus.DeploymentEvent
let traces = GuestAgentTraces
| where TIMESTAMP between (ago(1d) .. now())
| where severity == 'Error'
| summarize ErrorCount = count() by cirrusRunId, message
| where ErrorCount > 1000000;
traces
| join kind=inner (database('cirrus').DeploymentEvent) on $left.cirrusRunId == $right.RunGuid
| summarize TotalErrors = sum(ErrorCount) by TenantName, Schedule
| sort by TotalErrors desc
```

```kql
// Missing telemetry diagnosis — check if traces exist for a run
// Empty result means AppInsights ingestion pipeline failure
GuestAgentTraces
| where cirrusRunId == '{cirrus_run_id}'
| summarize TraceCount = count(), MinTime = min(TIMESTAMP), MaxTime = max(TIMESTAMP),
            ErrorCount = countif(severity == 'Error')
```

```kql
// Agent heartbeat check — lifecycle events indicate agent is alive
// Missing events suggest agent service crash or failed startup
GuestAgentEvents
| where TIMESTAMP between (ago(1d) .. now())
| where cirrusRunId == '{cirrus_run_id}'
| summarize EventCount = count(), Events = make_set(eventName),
            FirstEvent = min(TIMESTAMP), LastEvent = max(TIMESTAMP)
```

```kql
// Ingestion pipeline health — gap detection
// Large gaps between eventTime and TIMESTAMP indicate EventHub/Stream Analytics delays
GuestAgentTraces
| where TIMESTAMP between (ago(2d) .. now())
| extend IngestionLag = TIMESTAMP - eventTime
| summarize AvgLag = avg(IngestionLag), MaxLag = max(IngestionLag),
            P95Lag = percentile(IngestionLag, 95)
    by bin(TIMESTAMP, 1h)
| where MaxLag > 30m
| order by TIMESTAMP desc
```

```kql
// Package download failures — Setup phase errors related to NuGet
GuestAgentTraces
| where TIMESTAMP between (ago(1d) .. now())
| where severity == 'Error'
| where message contains 'NuGet' or message contains 'package' or message contains 'download'
    or message contains 'feed' or message contains 'restore'
| project TIMESTAMP, cirrusRunId, message, runtimeId
| order by TIMESTAMP desc
| take 50
```

```kql
// Runtime compatibility errors — platform mismatch issues
GuestAgentTraces
| where TIMESTAMP between (ago(1d) .. now())
| where severity == 'Error'
| where message contains 'RuntimeId' or message contains 'NETCore.Platforms'
    or message contains 'runtime.json' or message contains 'platform'
| project TIMESTAMP, cirrusRunId, message, runtimeId
| order by TIMESTAMP desc
| take 50
```

##### Diagnostic Knowledge

###### Failure Patterns

Platform patterns (GatewayTimeout, capacity, TiP quota, cluster-to-AZ, EnvironmentSelection, node unhealthy, ClusterInInvalidState, Deploy App Over OM timeout) are in provider.md. GuestAgent-specific patterns:

| Symptom | Root Cause | Fix | TSG |
|---------|-----------|-----|-----|
| Missing Kusto logs — `GuestAgentTraces` not appearing after test | Diagnostics Settings → EventHub → Stream Analytics pipeline failure; EventHub partition stuck or Stream Analytics job stopped | Check Stream Analytics job health (12 streaming units); check EventHub consumer groups; verify Diagnostics Settings on AppInsights resource; swap prod/stage if needed | `InternalDocs/Team/TSG/GA-MissingKustoLog.md` |
| Daily cap reached — email "daily cap limit reached" | Excessive exceptions from workload scripts; unchecked logging verbosity | Contact offending team; increase daily cap if legitimate; implement stricter logging | `InternalDocs/Team/TSG/GuestAgentDailyCapReached.md` |
| Exit code 127 (command not found) | Required tool (Python, Ruby, etc.) not installed on VM | Add tool installation to TestDependencies in TestType JSON | `Authoring-TestTypes.md` |
| Platform compatibility error (`NETCore.Platforms` outdated) | `runtime.json` missing new platform entry | Update `runtime.json` in the workload NuGet package | `InternalDocs/Systems/GuestAgent.md` |
| Argument parsing fails (Win vs Linux) | .NET `ProcessStartInfo` escapes args differently between platforms | Triple-escape quotation marks; test separately per platform | `Defining-Workloads.md` |
| Workload timeout in Setup phase | Package download failure or dependency install timeout | Check NuGet feed connectivity (`EngSys-Performance-GuestAgent`); verify package version exists in feed | — |
| No heartbeat from agent — `GuestAgentEvents` empty | Agent service crashed or failed to start | Check `systemctl status azperf` (Linux) or `sc query EngSys.Performance.GuestAgent` (Windows); check local logs at `/var/lib/azperf/.guestagent/logs/` (Linux) or `%ALLUSERSPROFILE%\.guestagent\logs\` (Windows); check AppInsights for exceptions | — |
| Stream Analytics job stopped/crashed | EventHub → Kusto ingestion breaks; `GuestAgentTraces` stop arriving | Check Stream Analytics job health in Azure Portal; verify 12 streaming units allocated; restart job if stopped | `InternalDocs/Systems/GuestAgent/GuestAgentBuildout.md` |
| AppInsights sampling drops data | High-volume workloads exceed sampling rate; telemetry silently dropped | Increase sampling rate or disable adaptive sampling for the `engsys-performance-guestagent` AppInsights resource | — |

###### Cascade Rules

Platform cascade rules (TiP session failure, launch failure, abort, parent action cascade, unhealthy node, TiP quota) are in provider.md. GuestAgent-specific rules:

- If `GuestAgentTraces` are empty for a `cirrusRunId` → agent likely never started or AppInsights ingestion pipeline is down. Check `GuestAgentEvents` for heartbeats first; if also empty, check agent service status on the VM.
- If Setup phase fails (exit code ≠ 0 in traces) → Workload and Cleanup phases will not execute. Focus on Setup errors, not downstream phase failures.
- If ingestion delay exceeds 30 minutes → results may appear eventually; check `IngestionDelay` query before concluding data is missing.
- If daily cap was reached → all telemetry for the remainder of the day is dropped. Check the daily cap offenders query to identify the source.
- If errors contain "NuGet" or "feed" or "package" → the issue is in package acquisition, not workload logic. Check feed connectivity and package version.
- If `runtimeId` in error traces doesn't match the expected platform → workload was deployed to wrong VM type. Check TestType JSON for correct RuntimeId constraint.

###### Agent Service Monitoring

| Platform | Service Name | Check Command | Log Location |
|----------|-------------|---------------|-------------|
| Linux | `azperf` | `systemctl status azperf` | `/var/lib/azperf/.guestagent/logs/*.log` + AppInsights → `GuestAgentTraces` |
| Windows | `EngSys.Performance.GuestAgent` | `sc query EngSys.Performance.GuestAgent` | `%ALLUSERSPROFILE%\.guestagent\logs\` + AppInsights → `GuestAgentTraces` |

###### Environment Checks

Platform environment checks (Cirrus cluster reachability, fabric settings, capacity, TiP quota) are in provider.md. GuestAgent-specific checks:

- Verify the WorkflowDb database is accessible: `https://cirrus.kusto.windows.net` / `WorkflowDb`
- Verify the NuGet feed is reachable: `https://msazure.pkgs.visualstudio.com/_packaging/EngSys-Performance-GuestAgent/nuget/v3/index.json`
- Verify AppInsights → EventHub → Kusto pipeline is active (check for recent `GuestAgentTraces` within last 2 hours)
- Check Jarvis dashboard for overall GuestAgent health: `https://portal.microsoftgeneva.com/dashboard/cirrus/GuestAgent/Prod`
- Verify the developer has access to the Cirrus tenant (check CirrusTenants.json for their security group)

---

<!-- PRIMITIVE:Report -->
#### Report

**Status:** passthrough
**Reason:** Report format will be defined in a future version. The Summarize phase in the agent handles result presentation for now.
