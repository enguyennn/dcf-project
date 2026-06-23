# Cirrus

**Schema:** 1

Cirrus is Azure's test orchestration platform. It launches test passes on Azure fabric nodes via TiP (Test in Production) sessions, tracked through Kusto telemetry. OES (Overlay Engineering Services) pipelines trigger Cirrus test passes for agent teams.

<!-- NAVIGATION -->
**Available Test Types:** overlake, guest-agent
**Reading Order:** Read this file first. If a test type is resolved, read the test type file next.
**Platform Primitives:** Observe, Diagnose
<!-- /NAVIGATION -->

### Glossary

| Acronym | Full Name | Description |
|---------|-----------|-------------|
| **OES** | Overlay Engineering Services | Pipeline and build system that triggers Cirrus test passes |
| **TiP** | Test in Production | Azure's system for allocating bare-metal nodes for testing |
| **CER** | Centralized Error Records | Error reporting system — `ErrorBuckets` table stores per-error records |
| **SoC** | System on Chip | Physical processor/node identifier in Azure fabric |
| **TPD2** | Test Pass Definition v2 | JSON definition of a test pass (RunSets, Runs, Actions) |
| **ADO** | Azure DevOps | CI/CD platform — builds and pipelines |
| **MCP** | Model Context Protocol | Tool protocol for LLM agents to call external services |
| **SAW** | Secure Admin Workstation | Secure workstation required for AME credential access |
| **DRI** | Designated Responsible Individual | On-call engineer for a service |
| **FTE** | Full-Time Employee | Microsoft full-time employee (relevant for Kusto access auto-approval) |
| **OM** | Object Manager | Azure fabric component for deploying/managing software on nodes |
| **ARM** | Azure Resource Manager | Azure's control plane for resource lifecycle operations |

## Required Settings

| Key | Description | Example | Required for |
|-----|-------------|---------|-------------|
| `cirrus_tenant` | Cirrus tenant — an organizational partition in Cirrus that scopes all queries to a team's test passes | `OverlakeAgents` | All primitives |
| `subscription_id` | Cirrus subscription ID | `<your-cirrus-subscription-id>` | All primitives |

## Optional Settings

| Key | Description | Example | When needed |
|-----|-------------|---------|------------|
| `requested_by` | Developer's alias or schedule name — for filtering ApiAttempt queries | `youralias` | To scope queries by requestor |
| `ado_organization` | ADO org for pipeline builds | `msazure` | If using ADO Pipeline Extension |
| `ado_project` | ADO project | `One` | If using ADO Pipeline Extension |
| `ado_pipeline_id` | ADO pipeline ID | `12345` | If using ADO Pipeline Extension |
| `schedule_name` | Default schedule name to filter by | `MySchedule` | If launching via schedules |
| `ado_build_definition_name` | ADO build definition to filter by | `Overlake-Build-Official` | To scope queries by build pipeline |
| `agent_name` | Agent name for filtering OESBuild/OvlProd queries by `OesTestAgentName` | `vfpsocagent` | For overlake queries that filter by agent |
| `cluster_name` | Target TiP cluster name(s) | `CVL02PrdApp12` | For cluster-level diagnostics |
| `workload_name` | Filter by GuestAgent workload name (e.g., `FIO`, `DiskSpeed`, `HammerDB`) | `FIO` | 🚧 Reserved for guest-agent test type — not yet used in queries |

## MCP Data Source

Primitives that declare `Method: mcp` use the `azure-mcp` MCP server (installed to `.vscode/mcp.json` by Octane).

**VS Code Tool Discovery:**
```
tool_search_tool_regex("mcp_azure.*kusto")   → finds the kusto MCP tool (works with both extension and workspace server)
<kusto_tool>(learn=true)                       → returns available commands
```

**Available Commands:**

| MCP Command | Required Parameters | Notes |
|-------------|-------------------|-------|
| `kusto_query` | `cluster-uri`, `database`, `query` | Executes KQL. Auth inherited from `az login`. **Read-only queries only** — never execute management commands (`.drop`, `.purge`, `.set`, `.delete`, `.alter`). |
| `kusto_sample` | `database`, `table`, `limit` | Quick row sample for exploration. |

**Default Parameters for this provider:**

| Parameter | Value |
|-----------|-------|
| `cluster-uri` | `https://cirrus.kusto.windows.net` |
| `database` | `cirrus` |

The test type toolkit specifies which KQL to run and which cluster/database to target. The agent calls the kusto MCP tool (discovered via `tool_search_tool_regex("mcp_azure.*kusto")`) with `command="kusto_query"` and `parameters` containing the cluster-uri, database, and query.

> **Note:** The kusto tool may be provided by either the workspace `azure-mcp` server (`.vscode/mcp.json`) or the Azure MCP VS Code extension (`ms-azuretools.azure-mcp`). The regex pattern `mcp_azure.*kusto` matches both: `mcp_azure-mcp_kusto` (workspace) and `mcp_azure_mcp_kusto` (extension).

## Common Metadata

**Cluster:** https://cirrus.kusto.windows.net
**Database:** cirrus
**Auth:** cli(az) — via Azure MCP server

**Portal:** https://cirrusperf.azurewebsites.net

### Common Tables — Cirrus Cluster

`cluster-uri: https://cirrus.kusto.windows.net`, `database: cirrus`

| Table | What it contains |
|-------|------------------|
| `TestPass` | Test pass details — created when a test pass is launched |
| `TestPassStatus` | Status history of test passes |
| `RunSet` | RunSet details within a test pass |
| `RunSetStatus` | RunSet status history |
| `Run` | Individual run details |
| `RunStatus` | Run status history |
| `Action` | Orchestrator actions within runs |
| `ActionStatus` | Current status of each action |
| `EnvironmentEvent` | TiP session info — TipSessionId, test pass, runset details |
| `EnvironmentSelection` | Step-by-step log of TipDynamic cluster selection during launch |
| `ApiAttempt` | Launch request attempts (query by ScheduleName or RequestedBy) |
| `ScheduleAttempt` | Schedule-based launch attempts |
| `PerfMeasurement` | Performance metrics from workloads; ExtraMetadata has rich action data |
| `ErrorBuckets` | CER — centralized error records for test pass instances. Use `ErrorBucketsLatest()` function for most current view. |
| `GarbageCollectionRegistration` | Resources registered for GC cleanup — tracks policy, resource type, expiration time |
| `GarbageCollectionCleanup` | GC cleanup execution log — shows what was cleaned, when, and status |
| `ActionLog` | Action-level debug logs from orchestrator |
| `CirrusRunLogs` | Geneva logging for debugging workload actions (replaces deprecated RunLogsv5) |
| `TipLogsv5` | TiP create/update/delete debug logs |
| `VMSKU` | Synced VM SKU data. Use `VMSKULatest()` function for current view. |
| `DeploymentEvent` | Deployment events — TenantName, Schedule, RunGuid mapping for tracking deployments across test passes |

### Common Tables — AzureCM Cluster

`cluster-uri: https://azurecm.kusto.windows.net`, `database: AzureCM`

| Table | What it contains |
|-------|------------------|
| `AllocableVmCount` | Cluster capacity — VM allocation counts over time |
| `TMMgmtNodeStateChangedEtwTable` | Node state transitions — Unhealthy, HumanInvestigate, Ready |
| `TMMgmtFabricSettingEtwTable` | Fabric settings — TiP session limits, subscription allowlists |
| `LogNodeSnapshot` | Point-in-time node state snapshots — includes `tipNodeSessionId`, `nodeId`, `Tenant` (cluster). Used to count active TiP sessions/nodes per cluster. |

### Key Functions

| Function | What it returns |
|----------|----------------|
| `GetTestPassCompletion(startUtc, endUtc)` | Completed test passes with terminal status |
| `GetTestPassCompletionFailures(startUtc, endUtc)` | Failed test passes with failing Run/Action and error details |
| `GetRunSetCompletion(startUtc, endUtc)` | RunSet-level completion |
| `GetRunCompletion(startUtc, endUtc)` | Run-level completion |

### Error Records (CER) — `ErrorBuckets` table

Centralized error store — all errors associated with a test pass instance (on Cirrus cluster).

| Field | Description |
|-------|-------------|
| `TestPassInstanceId` | (long) Matches `TestPassId` from completion functions |
| `Message` | Error message |
| `Component` | Cirrus component that reported the error |
| `ExceptionType` | Exception type with full namespace |
| `Category` | Error category (may be empty if no categorization rule matched) |
| `SubCategory` | Error sub-category — key for TSG URL mapping (e.g., `DeploymentTimeout`, `PF-InvalidServiceConfigIni`, `ClusterInInvalidState`, `PF-PathNotFound`) |
| `IsRetriable` | Whether the error is retriable |
| `ActionId` | (long) Which action produced this error |
| `RunSetId` | (long) Which runset this error belongs to |
| `CreatedDateTime` | Timestamp when the error record was created — use for ordering |
| `StackTrace` | Full exception stack trace |

### Common Tables — TipNodeService Cluster

`cluster-uri: https://tipnodeservice.kusto.windows.net`, `database: TipNodeService`

| Function | What it returns |
|----------|----------------|
| `GetTipQuotaAllocationForUser("{subscription_id}")` | TiP quota: total quota, active nodes, unrecovered nodes, available quota |
| `GetTipActiveNodesForUserQuota("{subscription_id}")` | List of currently active TiP node sessions under this quota |
| `GetTipUnhealthyNodesForUser("{subscription_id}")` | TiP nodes in unhealthy state under this quota |

## Query Conventions

These conventions apply to **all** primitives and test types that use Kusto queries.

### Schema Discovery

Table schemas can be discovered at runtime using KQL. Use this instead of hardcoding column lists:

```kql
// Discover columns for any table
{table_name} | getschema | project ColumnName, ColumnType
// Or: .show table {table_name} schema as json
```

This works on all clusters (Cirrus, OESBuild, OvlProd, AzureCM, WorkflowDb). Use schema discovery when constructing new queries or when a column name is uncertain.

### Common ID Mapping

The same entity has different column names across clusters:

| Concept | Cirrus Platform | OESBuild (Overlake) | WorkflowDb (GuestAgent) | Notes |
|---------|----------------|---------------------|------------------------|-------|
| Test pass ID | `TestPassInstanceId` (long) | `CirrusTestPassId` (long) | — | Same value, different names. Use `TestPassId` to query `ErrorBuckets`, `ActionStatus`, `PerfMeasurement`. Use `CirrusTestPassId` for `OverlakeCirrusTestpass`. |
| Request ID | `OperationId` (guid) | `CirrusRequestId` (string) | — | Same value — `CirrusRequestId` in OESBuild = `OperationId` in ApiAttempt |
| Request name | `ScheduleName` or `RequestName` | `CirrusRequestName` | — | Test pass name pattern |
| Run ID | `RunId` (long) | — | `RunGuid` = `cirrusRunId` (guid) | Bridge query: `Run | where TestPassId == {test_pass_id} | project RunId, RunGuid` |
| Build ID | — | `AdoBuildNumber` (string, e.g. "20260314.1") | — | Build version string |
| Build numeric | — | `AdoBuildId` (long) | — | ADO pipeline numeric ID, used in URLs |
| Node ID (physical) | — | `TipNodeNodeId` (string) | — | Physical blade identifier. Used in AzureCM queries (`BladeID`). |
| Node ID (SoC) | — | `TipNodeSocId` (string) | — | SoC identifier. Used in OvlProd queries for agent-level diagnostics. |
| RunSet ID | `RunSetId` (long) | `CirrusRunSetId` (long) | — | Same value, different column names across clusters |
| Action ID | `ActionId` (long) | `CirrusActionId` (long) | — | Same value — ErrorBuckets uses `ActionId`, OESBuild uses `CirrusActionId` |

### Parameter Chain

Query placeholders (`{param}`) come from these sources:

| Parameter | Source | How to get it |
|-----------|--------|---------------|
| `{cirrus_tenant}` | Required Setting | Developer provides (e.g., `OverlakeAgents`) |
| `{subscription_id}` | Required Setting | Developer provides |
| `{requested_by}` | Optional Setting | Developer's alias |
| `{schedule_name}` | Optional Setting | Developer provides or from `ApiAttempt.ScheduleName` |
| `{ado_build_definition_name}` | Optional Setting | Developer provides — filters OESBuild queries. Empty = show all. |
| `{agent_name}` | Optional Setting | Developer provides or from `OverlakeCirrusTestpass.OesTestAgentName` |
| `{cluster_name}` | Optional Setting | Developer provides (e.g., `CVL02PrdApp12`) or from `OverlakeCirrusResult.TipNodeCluster` |
| `{test_pass_id}` | Query output | From `ApiAttempt.TestPassInstanceId` or `OverlakeCirrusTestpass.CirrusTestPassId` |
| `{request_name}` | Query output | From `GetTestPassCompletionFailures.RequestName` or `OverlakeCirrusTestpass.CirrusRequestName` |
| `{build_number}` | Query output | From build inventory `OverlakeCirrusTestpass.AdoBuildNumber` |
| `{oes_build_name}` | Query output | From build inventory `OverlakeCirrusTestpass.OesBuildName` |
| `{tip_node_soc_id}` | Query output | From `OverlakeCirrusResult.TipNodeSocId` — used in OvlProd node queries |
| `{tip_node_node_id}` | Query output | From `OverlakeCirrusResult.TipNodeNodeId` — used in AzureCM queries (maps to `BladeID`) |
| `{tip_node_cluster}` | Query output | From `OverlakeCirrusResult.TipNodeCluster` |
| `{cirrus_run_id}` | Bridge query | `Run.RunGuid` → use as `GuestAgentTraces.cirrusRunId` |
| `{metric_name}` | Query output or Optional | From `GuestAgentMetrics.metricName` or developer provides (e.g., `IOPS`, `Latency`). Empty = show all. |

### Time Column Reference

Different tables use different timestamp column names:

| Table / Cluster | Time Column | Notes |
|----------------|-------------|-------|
| `ApiAttempt` (Cirrus) | `TimeStamp` | Launch request time |
| `OverlakeCirrusTestpass` (OESBuild) | `CirrusCreationTimeUtc` / `CirrusCompletionTimeUtc` | Creation vs completion time |
| `OverlakeCirrusResult` (OESBuild) | `CirrusStartedDateUtc` / `CirrusCompletedDateUtc` | Test execution window |
| OvlProd tables | `TIMESTAMP` (all caps) | Agent telemetry |
| AzureCM tables | `PreciseTimeStamp` | Fabric event timestamps |
| `ErrorBuckets` (Cirrus) | `CreatedDateTime` | Error record creation time |
| WorkflowDb tables (GuestAgent) | `TIMESTAMP` / `eventTime` | `TIMESTAMP` = Kusto ingestion time; `eventTime` = actual event time. Gap = ingestion delay. |
| `OverlakeCirrusTestpass` (OESBuild) | `CirrusStartTimeUtc` | Test start time (distinct from `CirrusCreationTimeUtc`). Used in discovery queries. |

### Time Range Resolution

Use the developer's request to resolve the time range. Default is `ago(1d) .. now()`.
Do NOT modify the time window beyond what the developer asked for.

| Developer says | Time range |
|----------------|------------|
| "yesterday", "last day" | `ago(1d) .. now()` |
| "last 2 days" | `ago(2d) .. now()` |
| "last week" | `ago(7d) .. now()` |
| "since Monday" | Resolve to actual date, e.g. `datetime(2026-03-02) .. now()` |
| No time mentioned | `ago(1d) .. now()` (default) |

### Terminology

| Term | Scope | Table | Status Field | Values |
|------|-------|-------|-------------|--------|
| **Test Pass** | Top-level orchestration unit — 1+ RunSets | `TestPass`, `TestPassStatus` | `State` | NotStarted, Executing, Succeeded, Failed, Expired, Canceled |
| **RunSet** | Collection of parallel Runs — defined in TPD2 via `RunSets[]` | `RunSet`, `RunSetStatus` | `Status` | NotStarted, Executing, Succeeded, Failed, Expired, Canceled |
| **Run** | Single execution instance within a RunSet — `Count` parameter controls how many | `Run`, `RunStatus` | `Status` | NotStarted, Executing, Succeeded, Failed, Expired, Canceled |
| **Action** | Smallest execution unit — runs in sequence within a Run | `Action`, `ActionStatus` | `Status` | NotStarted, Executing, Succeeded, Failed, Expired, Canceled |
| **Schedule** | Recurring launch definition — cron-based, runs until disabled | `ScheduleAttempt` | — | — |

> **OESBuild note:** OESBuild views use `CirrusStatus` (values: Succeeded, Failed, Aborted) and `CirrusOutcome` (values: Successful, Failed, Aborted). These are OESBuild-specific projections — `Aborted` maps to both `Canceled` AND `Expired` in Cirrus platform tables. `CirrusOutcome = "Successful"` maps to `CirrusStatus = "Succeeded"`. To distinguish Canceled from Expired when OESBuild shows "Aborted", check the Cirrus platform `TestPassStatus.State` value.

#### Execution Hierarchy

```
TestPass → 1+ RunSets (sequential by SequenceId)
  RunSet → 1+ Runs (parallel, controlled by Count or IterationCount)
    Run → 1+ Actions (sequential by SequenceId)
```

#### FailureHandling Modes (per Action)

Actions have a `FailureHandlingOnException` property that controls what happens when an action fails:

| Mode | Behavior |
|------|----------|
| `AbortOnFailure` | **Default.** Stops the run immediately and marks downstream actions as `NotStarted`. |
| `ContinueOnFailure` | Logs the failure but continues executing the remaining actions in the run. |
| `FastFailOnFailure` | Fails the entire test pass immediately — no further runs or actions execute. |

> When diagnosing, check the failing action's `FailureHandlingOnException` value. If it allows continuation (`ContinueOnFailure`), the failure may not roll up to TestPass status — inspect individual action results separately.

#### Early Failure Detection

The `ContainsFailure` boolean on TestPass/RunSet/Run is set to `True` immediately when a child entity fails, even while the parent is still `Executing` (e.g., cleanup actions still running). Use this for early detection without waiting for terminal state.

Test type toolkits may define additional terminology (e.g., test cases, scenarios) specific to their testing mode.

### Presentation Guidelines

These apply to both Observe and Diagnose reports:

1. Use the time range from the developer's request. Default is `ago(1d)`.
2. Always show builds first (unless the test type's Build primitive is passthrough — then skip builds and start with launch inventory).
3. Don't aggregate across builds unless explicitly asked.
4. Filter by `ado_build_definition_name` from config if present.
5. Show deep links (Cirrus Portal, ADO Build, Build Health) per test pass.
6. Use correct terminology — "test pass" for `CirrusStatus`, "test case" for `CirrusOutcome`.

## Provider Notes

- **Launch requires AME credentials from SAW.** Corp credentials are deprecated for launching. Kusto queries work from Corp with `az login`.
- **Content lives in EngSys-Performance-CirrusContent repo** under `src/CirrusTenants/{tenant}/`. TestPassDefinition2 JSON files define what gets tested.
- **Cirrus MCP server is planned** — will expose CER, PerfMeasurement, launch status, action status. Not for launching tests yet.
- **Launch methods:** PowerShell (`Start-CirrusTestPassRequest` recommended), ADO Pipeline Extension, Cirrus Portal.
- **PowerShell requires 7.4+** — use `Cirrus.PowerShell` module. `Submit-CirrusTestPassRequest` is deprecated → use `Start-CirrusTestPassRequest`.
- **ADO Pipeline Extension** supports Workload Identity Federation (preferred) and legacy Service Principal Secret auth. Extension: `cirrusdev.cirrus-pipeline-task`. Requires adding `TenantApp` role to `CirrusTenants.json` with the Managed Identity's Client ID.

### Permissions & Access

- **Tenant access** is controlled by AAD security groups defined in `CirrusTenants.json`.
- **Corp domain:** SG membership checked via IdWeb → MyAccess/CoreIdentity.
- **AME domain:** SG membership managed via OneIdentity from SAW device.
- **Kusto access (Corp):** Join `AZURE-ALL-STD` via [aka.ms/azaccess](https://aka.ms/azaccess).
- **Kusto access (AME):** Join `Cirrus-KustoReader` group via OneIdentity (auto-approval for FTEs, ~10min propagation).
- **Content repo write access:** Join `Azure-Source-RW` for branch creation.
- Permission error `"User does not have permissions to create a TestPass instance"` → check CirrusTenants.json for correct domain/role/SG, then verify membership.

### CER Data Model

Cirrus Error Records (CER) are the centralized error store:
- Scope order: OperationId → TestPassInstanceId → RunSet → RunId → ActionId
- Use `TestPassInstanceId` to search if available; `OperationId` is for pre-launch failures (no TestPassInstanceId exists yet)
- Fields: `Message`, `Component`, `ExceptionType`, `Category`, `SubCategory`, `IsRetriable`
- Consume via: Kusto (`ErrorBuckets` / `ErrorBucketsLatest()`), REST API, PowerShell (`Get-CirrusErrorRecord`)
- View interactively: Cirrus Portal → Test Pass Instance → "Failures" tab

### Garbage Collection

All resources created by Cirrus tests should be registered with GC:

| Policy | Trigger |
|--------|---------|
| `ExpirationTimeOnly` | Deletes at specified datetime (may clean up early on action failure) |
| `ActionEnd` | Deletes when owning action completes |
| `RunEnd` | Deletes when owning run completes |
| `RunSetEnd` | Deletes when owning runset completes |
| `TestPassEnd` | Deletes when test pass completes |

Best practices: Synchronize ARM + TiP expiration using `SessionExpiryTime` DataSet from TipCreate. Always clean ARM resources before or at same time as TiP resources. TiP Smart Cleanup is a safety net only.

### Schedules

- Schedules run tests at regular intervals — **run forever until disabled** (user responsibility).
- Minimum granularity: 5 minutes. Cron expression defines cadence.
- Stored in CirrusContent repo under `src/CirrusTenants/{tenant}/`.
- **Sync delay after merge: ~10 min** (cache refreshes via CheckAndUpdateScheduleCacheAsync every ~10 minutes).
- Two formats: ScheduleV2 (legacy), ScheduleV3 (current — supports Managed Identity).

### Test Cancellation

- **Under Cirrus control** (setup/deployment stages): Cancel via Cirrus Portal button.
- **Free-Running** (long-lived tests): Go to [Azure Resources page](https://cirrusperf.azurewebsites.net/v1/azresources), select resources, click "Delete Selected" (sets Expiration to Now, GC handles cleanup).
- Always use Cirrus-managed deletion — Cirrus knows which related resources to clean up.

### Support Channels

- **Stack Overflow (MS):** [tag=cirrus](https://stackoverflow.microsoft.com/questions/tagged/cirrus) — primary support channel
- **MS Teams:** `Cirrus Support` team → `Announcements` channel for outages
- **Email:** [cirrussupport@microsoft.com](mailto:cirrussupport@microsoft.com) — permissions/onboarding issues
- **Office Hours:** Every 2nd and 4th Thursday @ 11:30am PST
- **ICMs:** `Service=Cirrus`, `Team=Cirrus` — Sev 2 triggers auto phone call to DRI

## Platform Primitives

These sentinel-marked sections provide platform-level defaults for Cirrus primitives. Test type files can:
- **Inherit** (`**Inherits:** provider`) — use this section as-is, no test-type-specific content needed
- **Extend** (`**Extends:** provider`) — add test-type-specific content; agent reads provider section first, then test type section
- **Override** (no marker) — provide a complete replacement; agent ignores the provider section for this primitive

---

<!-- PRIMITIVE:Run -->
#### Run

**Status:** passthrough
**Reason:** Run primitive is not yet implemented. Launch mechanisms (PowerShell cmdlets, Start-CirrusTestPassRequest) will be defined in a future version after validating with Overlake and GuestAgent workflows.

---

<!-- PRIMITIVE:Observe -->
#### Observe

**Method:** mcp
**MCP Server:** `azure-mcp`
**Tool:** `kusto_query`
**Auth:** cli(az) — inherited from Common Metadata
**Data Source:** Cirrus cluster (default), see Common Tables above
**Portal URL:** https://cirrusperf.azurewebsites.net

##### Tool Discovery

```
tool_search_tool_regex("mcp_azure.*kusto")   → finds the kusto MCP tool (works with both extension and workspace server)
<kusto_tool>(learn=true)                       → returns available commands
```

##### MCP Parameters (per query)

Default parameters for platform queries (test type files may override per-query):

| Parameter | Value | Source |
|-----------|-------|--------|
| `cluster-uri` | `https://cirrus.kusto.windows.net` | Common Metadata |
| `database` | `cirrus` | Common Metadata |

##### Platform Discovery

Find recent launch activity when no specific identifier is provided:

```kql
// Launch requests by user
// Note: Discovery queries use ago(7d) — wider than the default ago(1d) — to catch recent activity across a full week.
ApiAttempt
| where RequestedBy == '{requested_by}' and TimeStamp > ago(7d)
| project TimeStamp, RequestedBy, Status, Message, TestPassInstanceId, OperationId, TenantName, ScheduleName
| order by TimeStamp desc
| take 10
```

##### Platform Query Flow

1. **Launch status** — `ApiAttempt` for recent launch requests by user or schedule
2. **Test pass completion** — `GetTestPassCompletionFailures()` for failed passes with error details
3. **If failures detected** — proceed to Diagnose

Test type files extend this flow with test-type-specific queries (e.g., OESBuild views, test case results).

##### Platform Queries — Cirrus Cluster

**MCP Parameters:** `cluster-uri: https://cirrus.kusto.windows.net`, `database: cirrus` (default)

```kql
// Failed test passes with Cirrus-native error details
GetTestPassCompletionFailures(ago(1d), now())
| where TenantName == '{cirrus_tenant}'
| project RequestId, RequestName, TestPassId, EndTime, State,
         RunSetDescription, ActionDescription, ErrorCategory, ErrorMessage
| order by EndTime desc
```

> **Column name note:** `GetTestPassCompletionFailures` returns `ErrorCategory` and `ErrorMessage`. The `ErrorBuckets` table stores the same data as `Category` and `Message`. Do not mix these names across contexts.

---

<!-- PRIMITIVE:Diagnose -->
#### Diagnose

**Method:** mcp
**MCP Server:** `azure-mcp`
**Tool:** `kusto_query`
**Auth:** cli(az) — inherited from Common Metadata

##### Tool Discovery

Same tool as Observe — if already discovered, skip.

```
tool_search_tool_regex("mcp_azure.*kusto")   → finds the kusto MCP tool
```

##### Platform Diagnostic Flow

**Empty results are meaningful.** Do not skip empty results, do not automatically widen time range, do not hallucinate explanations. Interpret in context of prior steps.

**If re-running without optional filters still returns empty:** the entity genuinely doesn't exist for that time range. Report this clearly.

0. **Resolve user input** → The user may provide a build number, schedule name, test pass ID, or description. Resolve it to `{test_pass_id}` before proceeding. If the user gives a non-numeric identifier, search by schedule name (`ApiAttempt.ScheduleName`) or build number (`OverlakeCirrusTestpass.AdoBuildNumber`) first.
   - *If Observe was already run:* use the test pass ID from Observe results.
   - *If not:* run the Observe Discovery query first to find matching test passes.
1. **Did the launch succeed?** → Check `ApiAttempt` for the launch request status
   - *If empty:* Launch not found — verify schedule name, check time range, or test hasn't launched yet. Possible Kusto outage. Ask user to confirm.
2. **Did the test pass complete?** → Check `GetTestPassCompletion()` for terminal state. Use `| where TestPassId == {test_pass_id}` for a specific pass.
   - *If empty:* Test pass is still running. Check RunSet/Run/Action status tables for current progress. Give Cirrus Portal link.
3. **Was it a TiP failure?** → Only if ApiAttempt shows a TiP-related error in Message. Check `EnvironmentSelection` for cluster selection failures (OutCount = 0). Requires `{request_name}` from step 2 output or `OverlakeCirrusTestpass.CirrusRequestName`.
   - *If empty:* Request wasn't TiP-dynamic, or environment selection didn't happen. Move on.
4. **Which action failed?** → Walk the hierarchy: RunSet (sort by SequenceId) → Run → Action. Check CER from `ErrorBuckets`.
   - **Early exit:** If ErrorBuckets `SubCategory` or `Message` matches a Failure Pattern with a TSG URL → **stop cascade and report**.
   - *If ErrorBuckets empty AND test pass Failed:* Retry after a few minutes — possible ingestion delay or Kusto outage. Give up after 2-3 retries. Fallback: check `OverlakeCirrusResult.CirrusErrorMessage` for script-level errors.
   - *Walk top-down:* RunSet 1 → Run 1 → Action 1, 2, 3... Find the first failed action.
5. **Node health / Cluster config / TiP quota** → 🚧 Under construction — diagnostic queries exist below but decision logic is not yet formalized. Test types should NOT assume these steps are fully operational.

Test type files extend this flow with test-type-specific diagnostic steps. Test type files provide all diagnostic queries — the provider defines the flow and decision logic, not the queries.

##### Platform Diagnostic Knowledge

###### Platform Failure Patterns

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| "Invoke Fabric Function" fails with `GatewayTimeout` / `TaskCanceledException` | TiP fabric proxy timeout — AzTipNodeService unresponsive on target cluster | Retry the test pass. If persistent, check cluster health or try a different region. |
| `Cluster {name} is not found in the cluster to az map` | Cluster decommissioned or not registered in TiP's cluster-to-AZ mapping | Exclude the cluster via TipDynamic constraints, or contact TiP team to update the mapping. |
| `Timeout occurred while waiting for Deploy App Over OM` | TiP Update (deploy) exceeded timeout on the target node | Increase timeout or investigate node-level OM deployment issues. |
| `EnvironmentSelection` OutCount = 0 for all filters | No TiP clusters match the requested constraints | Relax TipDynamic constraints (region, SKU, cluster type) or check regional capacity. |
| ApiAttempt Message: "No capacity was found after filtering for TiP-ClusterCapacity" | All candidate clusters at capacity at launch time | Wait and retry; check AllocableVmCount for cluster capacity trends; widen candidate cluster list. |
| Node state changed to `Unhealthy` or `HumanInvestigate` during test | Test node became unhealthy during execution — possible hardware issue or fabric action | Check AzureCM.TMMgmtNodeStateChangedEtwTable for the node's state transitions; likely not a test issue. |
| `ClusterInInvalidState` in CER | Target cluster is in an invalid state — TiP sessions cannot be created | Choose a different cluster or wait for cluster recovery. |
| TiP quota exhausted — `Quota_Available` = 0 | All TiP quota nodes are in use or unrecovered | Check TipNodeService.GetTipQuotaAllocationForUser for quota; GetTipUnhealthyNodesForUser for stuck nodes; wait for sessions to complete or request quota increase. |
| `Test Pass Launched Failed ... Could not find matching subscription` | Subscription not registered in Cirrus for this tenant | Verify subscription exists in CirrusSubscriptions.json and is mapped to the correct tenant. |
| `User does not have permissions to create a TestPass instance` | Tenant security group membership issue | Check CirrusTenants.json for correct domain/role/SG, verify membership via IdWeb (Corp) or OneIdentity (AME). |
| Sub does not allow the selected SKU in candidate cluster regions | Subscription quota mismatch | Ensure subscription allows the requested VM SKU in the regions of your candidate clusters. |
| Cluster utilization exceeds 0.6 threshold | Cluster too busy for TiP session creation | Widen candidate cluster list or wait for capacity. |
| Cluster is UltraSSD enabled | Allocator errors on UltraSSD-enabled clusters | Exclude UltraSSD clusters from candidate list. |
| Test pass `Expired` status | Test pass exceeded `Timeout` (default: tenant's `DefaultTestPassInstanceLifeTimeInHr`) | Increase `Timeout` in TPD2 or investigate why execution took longer than expected. |
| GC resources not cleaned up | Resources not registered with GC, or mismatched ARM/TiP GC policies | Register all resources; synchronize ARM + TiP expiration using `SessionExpiryTime` DataSet from TipCreate. |

###### Platform Cascade Rules

- **Early exit:** If a Failure Pattern matches with a TSG URL → **stop the diagnostic cascade** and report the pattern + TSG. No need to run further diagnostic steps.
- If TiP session creation fails (EnvironmentSelection shows failure or OutCount=0) → all downstream actions will fail. Focus on EnvironmentSelection, not ActionCompletion.
- If launch fails (ApiAttempt shows error, no TestPassInstanceId) → no test pass exists. Don't query CER.
- If launch was aborted → check ApiAttempt.Message for the reason. Common causes: capacity ("No capacity was found"), user cancel, timeout, quota exceeded, infra abort.
- If a parent action fails, child actions in the same RunSet may cascade-fail. Focus on the first failing action.
- If action's `FailureHandlingOnException` is `ContinueOnFailure`, that failure may not roll up to TestPass status — check individual action results via `ActionStatus` separately.
- If `ContainsFailure=True` but `Status=Executing` → cleanup actions are still running. Report the failure early but note cleanup is in progress.
- If ScheduleAttempt shows errors but no ApiAttempt entry → the schedule itself failed to submit the request. Check ScheduleAttempt.Message for the reason.
- If test pass is `Expired` → execution exceeded the Timeout. Check if actions are stuck in long-running operations; consider increasing Timeout in TPD2.

###### Platform Environment Checks

- Verify the Cirrus Kusto cluster is reachable: `https://cirrus.kusto.windows.net`
- Verify the TipNodeService cluster is reachable: `https://tipnodeservice.kusto.windows.net`
- Verify the AzureCM cluster is reachable: `https://azurecm.kusto.windows.net`
- Check the target cluster's fabric settings — is `Fabric.TiP.AllowNewTipNodeSessions` enabled?
- Check cluster capacity via `AllocableVmCount` if seeing capacity aborts
- Check TiP quota via `GetTipQuotaAllocationForUser` if seeing quota exhaustion
- Verify developer has tenant membership in CirrusTenants.json (correct domain + security group)
- Verify subscription is registered in CirrusSubscriptions.json and mapped to the tenant
