# overlake

**Schema:** 1
**Description:** Overlake SoC agent functional testing on real Azure fabric nodes via Cirrus orchestration. Covers build verification, functional tests (Boot Health, Service Status, Pre/Post-Reboot, Memory Monitor, SE Linux), custom/unmanaged tests, and agent deployment validation across multiple AppModels and clusters.

## Defaults

| Key | Value |
|-----|-------|
| `cirrus_tenant` | `OverlakeAgents` |
| `subscription_id` | `a37e0bda-7ae0-4ca2-9c85-2eefa44dca4c` |

These are used when the developer's `octane.yaml` does not specify values for the overlake test type.

## Test Types

Overlake supports three tiers of Cirrus tests, all orchestrated through the same pipeline:

| Test Type | `TestType` in OverlakeES.definition | Request Name Pattern | Managed by |
|-----------|-------------------------------------|---------------------|------------|
| **Common Functional** | `Functional` | `Cirrus-Functional-Tests-{BuildName}.{AgentName}.{AppModel}` | OES team — uses shared TestPassDefinition + common test scripts |
| **Agent Functional** | `Functional` | `Cirrus-Functional-Tests-{BuildName}.{AgentName}.{AppModel}` | Agent team writes custom test scripts, OES manages the TestPassDefinition |
| **Custom/Unmanaged** | `Custom` | `Cirrus-Custom-Tests-{BuildName}.{AgentName}.{AppModel}` | Agent team owns both TestPassDefinition and scripts |

### Request Name Parsing

The `CirrusRequestName` (in `OverlakeCirrusTestpass`) and `RequestName` (in Cirrus completion functions) encode the build context:

```
Cirrus-Functional-Tests-{OesBuildName}.{OesTestAgentName}.{OesTestAppModel}
```

To extract components:
```kql
| extend Parts = split(RequestName, "Cirrus-Functional-Tests-")[1]
| extend OesBuildName = tostring(split(Parts, ".")[0])
| extend OesTestAgentName = tostring(split(Parts, ".")[1])
| extend OesTestAppModel = tostring(split(Parts, ".")[2])
```

For Custom tests, the prefix is `Cirrus-Custom-Tests-` (not `Cirrus-Custom-` — the `-Tests-` suffix is always present).

### Standard Functional Test Cases

These common test scripts validate baseline agent health:

| Test Case | Script | What it validates |
|-----------|--------|-------------------|
| `Boot Health test` | `boot_health.sh {agent}_config.sh` | Journalctl logs contain expected entries after service start |
| `Service Status test` | `service_status.sh {agent}_config.sh` | `systemctl` shows correct LoadState, ActiveState, SubState |
| `Memory monitor test` | `memory_monitor.sh {agent}_config.sh` | Memory usage stays within configured MEMORY_LIMIT |
| `Soc Pre-Reboot test` | `pre_reboot.sh {agent}_config.sh` | Pre-reboot validation checks |
| `Soc Post-Reboot test` | `post_reboot.sh {agent}_config.sh` | Post-reboot validation checks |
| `SE Linux test` | `selinux_test.sh {agent}_config.sh` | SELinux policy enforcement — checks for AVC denials |

A test pass is considered fully passing when all configured test cases succeed.

### Build Deep Links

All tests are launched from ADO pipeline builds. Use these URL patterns to generate deep links from query results:

| Link | Pattern | When to show |
|------|---------|-------------|
| **ADO Build Pipeline** | `https://dev.azure.com/msazure/One/_build/results?buildId={AdoBuildId}&view=results` | Always — shows the build that triggered the test |
| **Azure Build Health** | `https://dev.azure.com/msazure/One/_apps/buildhealth?view=Test&definitionId=285519&buildId={AdoBuildId}` | Always — shows test results in ABH for the build |
| **Cirrus Portal (Test Pass)** | `https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/{CirrusTestPassId}` | When you have a TestPassId |
| **Cirrus Portal (Action)** | `https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/{CirrusTestPassId}/runsets/{RunSetId}/runs/{RunId}/actions/{ActionId}` | When drilling into a specific action |
| **Cirrus Portal (RunSet)** | `https://cirrusperf.azurewebsites.net/v1/query?key={RunSetId}&type=RunSetId` | When investigating CER by RunSet |
| **Watson Crash Portal** | `https://portal.watson.azure.com/?$filter=(ClientIngestTime le {day_after} and ClientIngestTime ge {test_start} and NodeId eq '{TipNodeSocId}')&view=advancedsearch&range=custom` | When investigating crashes on a node — uses SocId |
| **Gandalf Node Story** | `https://gandalf.azcompute.com/ad/nodestoryweb.html?nodeId={TipNodeSocId}&datetime={hour_before_test}` | When investigating node-level issues |
| **OvlProd Systemd Logs** | `https://azcore.centralus.kusto.windows.net/OvlProd?web=1&query=...LinuxOverlakeSystemd\|where NodeId=='{TipNodeSocId}' and Cluster=='{TipNodeCluster}'` | When investigating service failures — actual journalctl output |
| **OvlProd Service Manager** | `https://azcore.centralus.kusto.windows.net/OvlProd?web=1&query=...OverlakeServiceManagerStatus\|where NodeId=='{TipNodeSocId}' and Cluster=='{TipNodeCluster}'` | When investigating service status issues |
| **Fabric Response (PerfMeasurement)** | `https://cirrus.kusto.windows.net/cirrus?web=1&query=...PerfMeasurement\|where TestPassId=={CirrusTestPassId} and ApiCall=~'{CirrusTestCaseTitle}'\|project parse_json(ExtraMetadata.CommandResults)` | When investigating script execution details |

KQL to generate these:
```kql
| extend ADOBuildPipelineURL = strcat("https://dev.azure.com/msazure/One/_build/results?buildId=", AdoBuildId, "&view=results")
| extend AzureBuildHealthURL = strcat("https://dev.azure.com/msazure/One/_apps/buildhealth?view=Test&definitionId=285519&buildId=", AdoBuildId)
| extend CirrusURL = strcat("https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/", CirrusTestPassId)
| extend WatsonURL = strcat("https://portal.watson.azure.com/?$filter=(ClientIngestTime%20le%20", datetime_add('day',1,CirrusStartedDateUtc), "%20and%20ClientIngestTime%20ge%20", CirrusStartedDateUtc, "%20and%20NodeId%20eq%20%27", TipNodeSocId, "%27)&view=advancedsearch&range=custom")
| extend NodeStoryURL = strcat("https://gandalf.azcompute.com/ad/nodestoryweb.html?nodeId=", TipNodeSocId, "&datetime=", datetime_add('hour',-1,CirrusStartedDateUtc))
```

### Test Execution Flow

1. **OES Pipeline triggers** → Official build produces agent package in CloudVault
2. **Cirrus launch** → `ApiAttempt` records the launch request
3. **TiP session created** → `EnvironmentSelection` logs cluster selection → `EnvironmentEvent` records session
4. **Agent deployed** → SoCTestScripts deployed via TipUpdate/LinuxAppOverOM, then target agent deployed
5. **Tests execute** → `Tip_Soc_Run_Commands` shared script runs each test case on the SoC via RepairAgent
6. **Results recorded** → `OverlakeCirrusResult` (OESBuild) has per-test-case outcomes, `ErrorBuckets` (Cirrus) has CER

## Multi-Cluster Data Sources

Overlake queries span multiple Kusto clusters. The MCP `kusto_query` tool accepts `cluster-uri` and `database` per call. Use the correct source for each query.

| Alias | Cluster URI | Database | What it has |
|-------|------------|----------|-------------|
| **OESBuild** | `https://overlakees.westus2.kusto.windows.net` | `OESBuild` | Overlake build logs, Cirrus test pass/results views, build definitions |
| **Cirrus** | `https://cirrus.kusto.windows.net` | `cirrus` | Cirrus platform data — completion functions, ErrorBuckets, ApiAttempt, EnvironmentSelection, PerfMeasurement |
| **AzureCM** | `https://azurecm.kusto.windows.net` | `AzureCM` | Cluster capacity (AllocableVmCount), node state changes, fabric settings |
| **OvlProd** | `https://azcore.centralus.kusto.windows.net` | `OvlProd` | Node-level telemetry — systemd logs (LinuxOverlakeSystemd), service manager status (OverlakeServiceManagerStatus), memory stats (OverlakeMemoryStatTable), service health (OverlakeServiceHealthTable), unit status (OverlakeUnitStatusTable), Overlake OS/agent version (LinuxOverlakeVersion) |
| **TipNodeService** | `https://tipnodeservice.kusto.windows.net` | `TipNodeService` | TiP quota allocation (GetTipQuotaAllocationForUser), active TiP nodes (GetTipActiveNodesForUserQuota), unhealthy TiP nodes (GetTipUnhealthyNodesForUser) |

Unless noted, queries target the **Cirrus** cluster/database (inherited from provider.md).

---

<!-- PRIMITIVE:Build -->
#### Build

**Status:** passthrough
**Reason:** 🚧 Under construction — Azure Test Platform is working to make Build happen! ADO pipeline integration will be defined after validating the build workflow with the Overlake team.

---

<!-- PRIMITIVE:Run -->
#### Run

**Status:** passthrough
**Reason:** 🚧 Under construction — Azure Test Platform is working to make Run happen! Overlake launch mechanism (Start-CirrusTestPassRequest with OverlakeES TestPassDefinitions) will be defined in a future version.

---

<!-- PRIMITIVE:Observe -->
#### Observe

**Extends:** provider
**Data Source:** Multiple clusters — see Multi-Cluster Data Sources above

Overlake extends the platform Observe (ApiAttempt, GetTestPassCompletionFailures) with OESBuild cluster views, test category classification, and individual test case results.

##### Time Range Resolution

Inherited from provider.md — see **Query Conventions > Time Range Resolution**.

##### Test Categories

The `CirrusRequestName` prefix encodes the test category (Overlake-specific):

| Prefix Pattern | Category | Display Name | Notes |
|---------------|----------|--------------|-------|
| `Cirrus-Functional-Tests-DedicatedBaremetal-` | `Functional-Baremetal` | Functional (Baremetal) | Standard test cases on dedicated hardware |
| `Cirrus-Functional-Tests-` (not Baremetal) | `Functional` | Functional (Standard) | Standard test cases on shared cluster |
| `Cirrus-Custom-Tests-` | `Custom` | Custom Scenarios | Scenario-specific tests, group by scenario name |
| `Cirrus_Unmanaged_` | `Unmanaged` | Unmanaged | Internal/business name for Custom tests — functionally identical to Custom. No `OverlakeCirrusResult` rows (test pass-level data only via `OverlakeCirrusTestpass`). |

**Common test type filter and extraction** — prepend to all OESBuild queries that filter or group by test type:

```kql
// Common: test type filter (include all managed + unmanaged)
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
// Common: TestCategory extraction
| extend TestCategory = case(
    CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal",
    CirrusRequestName startswith "Cirrus-Functional", "Functional",
    CirrusRequestName startswith "Cirrus-Custom", "Custom",
    CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged",
    "Other")
```

Queries below reference this as `// << Apply: test type filter + TestCategory >>` instead of repeating inline.

Extraction KQL for Custom scenario name:

```kql
// From CirrusRequestName like:
//   Cirrus-Custom-Tests-Host_Networking_VfpAgent.vfpsocagent.2008-NatPortReuse_ServicingStress.OVL2
// Extract: NatPortReuse_ServicingStress
| extend ScenarioWithSuffix = extract("Cirrus-Custom-Tests-[^.]+\\.[^.]+\\.[0-9]+-(.*)", 1, CirrusRequestName)
| extend ScenarioBase = extract("^([^.]+)", 1, ScenarioWithSuffix)
| extend ClusterSuffix = extract("\\.(.+)$", 1, ScenarioWithSuffix)
```

##### Presentation Rules

Extends provider.md Presentation Guidelines with Overlake-specific rules:

1. Group test passes by TestCategory: Functional-Baremetal, Functional, Custom, Unmanaged.
2. For Functional passes, show individual test case outcomes (Boot Health, Service Status, etc.).
3. For Custom passes, group by ScenarioBase and show pass/fail per scenario.

MCP parameters inherited from provider.md. OESBuild queries override: cluster-uri: https://overlakees.westus2.kusto.windows.net, database: OESBuild

##### Discovery

Find recent test passes for this tenant. Start with the OESBuild view for the best overview:

**[OESBuild cluster]** `cluster-uri: https://overlakees.westus2.kusto.windows.net`, `database: OESBuild`

```kql
// Test pass overview — functional + custom tests, shows build context, agent, status
// Use CirrusRequestName prefix to distinguish test types:
//   "Cirrus-Functional" = managed functional tests
//   "Cirrus-Custom" or "Cirrus_Unmanaged_" = custom/unmanaged tests
OverlakeCirrusTestpass
| where CirrusStartTimeUtc between (ago(1d) .. now())  // CirrusStartTimeUtc is intentional — filters by test start time, not creation time
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| extend CirrusURL= strcat("https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/", CirrusTestPassId)
| extend ADOBuildPipelineURL = strcat("https://dev.azure.com/msazure/One/_build/results?buildId=", AdoBuildId, "&view=results")
| extend AzureBuildHealthURL = strcat("https://dev.azure.com/msazure/One/_apps/buildhealth?view=Test&definitionId=285519&buildId=", AdoBuildId)
| project AdoBuildReason,
          AdoBuildDefinitionName,
          AdoBuildNumber,
          CirrusRequestName,
          TestCategory,
          OesBuildName,
          OesTestAgentName,
          OesTestAppModel,
          OesBuildASAN,
          CirrusStatus,
          CirrusURL,
          ADOBuildPipelineURL,
          AzureBuildHealthURL,
          OesBuildAgentBranch,
          OesBuildAgentVersion,
          CirrusCreationTimeUtc,
          CirrusCompletionTimeUtc,
          CirrusTestPassId,
          CirrusRequestId
| order by CirrusCreationTimeUtc desc
| take 25
```

##### Query Flow

Provider handles platform queries (ApiAttempt, GetTestPassCompletionFailures). Overlake extends with:

1. **Build inventory** — List distinct `AdoBuildNumber` with pass/fail counts, TestCategory breakdown, branch, and time range. Always start here.
   - *If empty:* No test passes found for this filter + time range. Tests may not have run yet, or the build is still running. Tell user "no tests found" and suggest verifying the build definition name.
2. **Per-build breakdown** — For each build (or the developer's chosen build), show test passes grouped by TestCategory (Functional-Baremetal, Functional, Custom, Unmanaged)
3. **Functional test case detail** — Only for Functional/Functional-Baremetal categories: drill into `OverlakeCirrusResult` for individual test case outcomes (Boot Health, Service Status, etc.)
   - *Note:* Unmanaged tests do NOT produce `OverlakeCirrusResult` rows. Only test pass-level data is available for Unmanaged via `OverlakeCirrusTestpass`.
   - *If empty:* No individual test case results found. Test pass may be Unmanaged/Custom (no `OverlakeCirrusResult` rows), or results haven't ingested yet. Check `OverlakeCirrusTestpass` for pass-level data instead.
4. **Custom scenario summary** — For Custom category: group by ScenarioBase with pass/fail per scenario. Show top failing scenarios first.
   - *If empty:* No Custom test passes in this build/time range. Verify the build runs Custom tests.
5. **Enhanced results with deep links** — Extended `OverlakeCirrusResult` with Watson, Systemd, NodeStory, FabricResponse, ServiceManager, MemoryStat, ServiceHealth, UnitStatus URLs
   - *If empty:* Same as step 3 — no `OverlakeCirrusResult` rows for this test pass.
6. **Trend analysis** — TestCase/TestPass outcome percentages (weekly) for trend tracking
   - *If empty:* Insufficient history — tests may have just started running. Need multiple days of data for meaningful trends.
7. **Good builds** — Identify builds with >300 successful test cases as known-good baselines
   - *If empty:* No builds reached the success threshold — either test volume is low or all builds have failures. Lower the threshold or widen the time range.

##### Queries — OESBuild Cluster

**MCP Parameters:** `cluster-uri: https://overlakees.westus2.kusto.windows.net`, `database: OESBuild`

```kql
// Build inventory — always show this first
// Lists all builds in the time window with pass/fail counts per TestCategory
OverlakeCirrusTestpass
| where CirrusCreationTimeUtc between (ago(1d) .. now())
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| extend ADOBuildPipelineURL = strcat("https://dev.azure.com/msazure/One/_build/results?buildId=", AdoBuildId, "&view=results")
| extend AzureBuildHealthURL = strcat("https://dev.azure.com/msazure/One/_apps/buildhealth?view=Test&definitionId=285519&buildId=", AdoBuildId)
| summarize
    TestPasses = count(),
    Succeeded = countif(CirrusStatus == "Succeeded"),
    Failed = countif(CirrusStatus == "Failed"),
    Aborted = countif(CirrusStatus == "Aborted"),
    Categories = make_set(TestCategory),
    Agents = make_set(OesTestAgentName),
    ADOBuildPipelineURL = take_any(ADOBuildPipelineURL),
    AzureBuildHealthURL = take_any(AzureBuildHealthURL)
    by AdoBuildNumber, OesBuildAgentBranch, AdoBuildDefinitionName, AdoBuildReason
| extend PassRate = strcat(round((todouble(Succeeded) / todouble(TestPasses)) * 100, 1), "%")
| order by AdoBuildNumber desc
```

```kql
// Build-scoped test pass detail — drill into a specific build
// Use after build inventory to show per-category breakdown
OverlakeCirrusTestpass
| where AdoBuildNumber == '{build_number}'
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where OesBuildName in ('{oes_build_name}') or '{oes_build_name}' == ''
| where OesTestAgentName in ('{agent_name}') or '{agent_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| extend CirrusURL = strcat("https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/", CirrusTestPassId)
| extend ADOBuildPipelineURL = strcat("https://dev.azure.com/msazure/One/_build/results?buildId=", AdoBuildId, "&view=results")
| project TestCategory, CirrusRequestName, OesBuildName, OesTestAgentName, OesTestAppModel,
         CirrusStatus, CirrusURL, ADOBuildPipelineURL,
         CirrusCreationTimeUtc, CirrusCompletionTimeUtc, CirrusTestPassId
| order by TestCategory asc, OesTestAgentName asc
```

```kql
// Custom scenario summary — group by scenario name with pass/fail
// Use when Custom test volume is high to identify failing scenarios
OverlakeCirrusTestpass
| where CirrusCreationTimeUtc between (ago(1d) .. now())
| where CirrusRequestName startswith "Cirrus-Custom"
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| where OesBuildName in ('{oes_build_name}') or '{oes_build_name}' == ''
| where OesTestAgentName in ('{agent_name}') or '{agent_name}' == ''
| extend ScenarioWithSuffix = extract("Cirrus-Custom-Tests-[^.]+\\.[^.]+\\.[0-9]+-(.*)", 1, CirrusRequestName)
| extend ScenarioBase = extract("^([^.]+)", 1, ScenarioWithSuffix)
| summarize
    Total = count(),
    Succeeded = countif(CirrusStatus == "Succeeded"),
    Failed = countif(CirrusStatus == "Failed"),
    Aborted = countif(CirrusStatus == "Aborted")
    by ScenarioBase, OesTestAgentName, OesTestAppModel
| extend PassRate = strcat(round((todouble(Succeeded) / todouble(Total)) * 100, 1), "%")
| order by Failed desc, ScenarioBase asc
```

```kql
// Individual test case results — outcomes, node info, deep links
// CirrusErrorMessage contains the script error output for failed tests
// Note: Unmanaged tests do not produce OverlakeCirrusResult rows
OverlakeCirrusResult
| where CirrusStartedDateUtc between (ago(1d) .. now())
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom"
| where OesBuildName in ('{oes_build_name}') or '{oes_build_name}' == ''
| where OesTestAgentName in ('{agent_name}') or '{agent_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", "Other")  // § Test Categories
| extend CirrusURL = strcat("https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/", CirrusTestPassId, "/runsets/", CirrusRunSetId, "/runs/", CirrusRunId, "/actions/", CirrusActionId)
| extend ADOBuildPipelineURL = strcat("https://dev.azure.com/msazure/One/_build/results?buildId=", AdoBuildId, "&view=results")
| extend AzureBuildHealthURL = strcat("https://dev.azure.com/msazure/One/_apps/buildhealth?view=Test&definitionId=285519&buildId=", AdoBuildId)
| project AdoBuildNumber, OesBuildName, OesTestAgentName, OesTestAppModel,
         CirrusTestCaseTitle, CirrusOutcome, CirrusErrorMessage,
         TipNodeCluster, TipNodeNodeId, TipNodeSocId, TipNodeSessionId,
         CirrusStartedDateUtc, OesBuildAgentVersion, OesBuildASAN,
         CirrusURL, ADOBuildPipelineURL, AzureBuildHealthURL
| order by CirrusStartedDateUtc desc
```

```kql
// Failure summary by agent — which agents are failing most?
OverlakeCirrusResult
| where CirrusStartedDateUtc between (ago(7d) .. now())
| where CirrusOutcome == "Failed"
| summarize FailCount = count() by OesTestAgentName
| order by FailCount desc
```

```kql
// Test pass status summary per day — stacked bar chart data, grouped by TestCategory
OverlakeCirrusTestpass
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where CirrusCreationTimeUtc between (ago(7d) .. now())
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| summarize count() by bin(CirrusCreationTimeUtc, 1d), CirrusStatus, TestCategory
| order by CirrusCreationTimeUtc asc
```

```kql
// Results per agent — success/fail/abort breakdown, grouped by TestCategory
OverlakeCirrusTestpass
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where CirrusCreationTimeUtc between (ago(7d) .. now())
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| summarize count() by CirrusStatus, TestCategory, OesBuildName, OesTestAgentName, OesTestAppModel
| order by TestCategory asc, OesBuildName asc
```

```kql
// Enhanced test results with diagnostic deep links (Watson, Systemd, NodeStory, FabricResponse)
// Use this when drilling into individual test case failures — provides clickable links to all
// node-level diagnostic data sources on OvlProd, Cirrus PerfMeasurement, and Watson portal
let baseURLOvlProd = "https://azcore.centralus.kusto.windows.net/OvlProd?web=1&query=cluster('azcore.centralus.kusto.windows.net').database('OvlProd')";
let cirrusURL = "https://cirrusperf.azurewebsites.net/v1/testpassinstances/c/";
let nodeStoryURL = "https://gandalf.azcompute.com/ad/nodestoryweb.html?";
let baseURLCirrusDB = "https://cirrus.kusto.windows.net/cirrus?web=1&query=cluster('cirrus.kusto.windows.net').database('cirrus')";
OverlakeCirrusResult
| where CirrusStartedDateUtc between (ago(1d) .. now())
| where OesBuildName in ('{oes_build_name}') or '{oes_build_name}' == ''
| where OesTestAgentName in ('{agent_name}') or '{agent_name}' == ''
| extend CirrusURL = strcat(cirrusURL, CirrusTestPassId, "/runsets/", CirrusRunSetId, "/runs/", CirrusRunId, "/actions/", CirrusActionId)
| extend ADOBuildPipelineURL = strcat("https://dev.azure.com/msazure/One/_build/results?buildId=", AdoBuildId, "&view=results")
| extend AzureBuildHealthURL = strcat("https://dev.azure.com/msazure/One/_apps/buildhealth?view=Test&definitionId=285519&buildId=", AdoBuildId)
| extend WatsonURL = strcat("https://portal.watson.azure.com/?$filter=(ClientIngestTime%20le%20", datetime_add('day',1,CirrusStartedDateUtc), "%20and%20ClientIngestTime%20ge%20", CirrusStartedDateUtc, "%20and%20NodeId%20eq%20%27", TipNodeSocId, "%27)&view=advancedsearch&range=custom")
| extend timestampQueryString = strcat("| where TIMESTAMP between (todatetime('", datetime_add('hour',-1,CirrusStartedDateUtc), "') .. todatetime('", datetime_add('hour',1,CirrusStartedDateUtc), "'))")
| extend orderingQueryString = "| order by TIMESTAMP asc"
| extend NodeClusterQueryString = strcat("| where NodeId == '", TipNodeSocId, "' and Cluster == '", TipNodeCluster)
| extend SystemdLogs = case(
    CirrusTestCaseTitle == "SE Linux test",
    strcat(baseURLOvlProd, ".LinuxOverlakeSystemd", timestampQueryString, NodeClusterQueryString, "' and MESSAGE contains 'AVC avc' and MESSAGE contains '", OesTestAgentName, "'", "| project PreciseTimeStamp, _SYSTEMD_UNIT, MESSAGE, SYSLOG_IDENTIFIER, Cluster, TIMESTAMP", orderingQueryString),
    strcat(baseURLOvlProd, ".LinuxOverlakeSystemd", timestampQueryString, NodeClusterQueryString, "' and _SYSTEMD_UNIT contains '", OesTestAgentName, "'", "| project PreciseTimeStamp, _SYSTEMD_UNIT, MESSAGE, SYSLOG_IDENTIFIER, Cluster, TIMESTAMP", orderingQueryString))
| extend ServiceManagerStatusLogs = strcat(baseURLOvlProd, ".OverlakeServiceManagerStatus", timestampQueryString, NodeClusterQueryString, "' and ServiceName contains '", OesTestAgentName, "'", orderingQueryString)
| extend MemoryStatTable = strcat(baseURLOvlProd, ".OverlakeMemoryStatTable", timestampQueryString, NodeClusterQueryString, "' and Name contains '", OesTestAgentName, "'", orderingQueryString)
| extend ServiceHealthTable = strcat(baseURLOvlProd, ".OverlakeServiceHealthTable", timestampQueryString, NodeClusterQueryString, "' and Name contains '", OesTestAgentName, "'", orderingQueryString)
| extend UnitStatusTable = strcat(baseURLOvlProd, ".OverlakeUnitStatusTable", timestampQueryString, NodeClusterQueryString, "' and Name contains '", OesTestAgentName, "'", orderingQueryString)
| extend NodeStoryURL = strcat(nodeStoryURL, "nodeId=", TipNodeSocId, "&datetime=", datetime_add('hour',-1,CirrusStartedDateUtc))
| extend FabricResponseURL = strcat(baseURLCirrusDB, ".PerfMeasurement", timestampQueryString, "| where TestPassId ==", CirrusTestPassId, " and ApiCall =~ '", CirrusTestCaseTitle, "'", "| project CommandResultsParsed = parse_json(ExtraMetadata.CommandResults) | project Result = CommandResultsParsed.Result, FabricAPIExitCode = CommandResultsParsed.FabricAPIExitCode, ScriptSuccess = CommandResultsParsed.ScriptSuccess, ExecutionTimeInSeconds = CommandResultsParsed.ExecutionTimeInSeconds")
| project AdoBuildNumber, OesBuildName, OesTestAgentName, OesTestAppModel,
         CirrusTestCaseTitle, CirrusOutcome, CirrusErrorMessage,
         SystemdLogs, UnitStatusTable, ServiceManagerStatusLogs, MemoryStatTable, ServiceHealthTable,
         NodeStoryURL, CirrusURL, FabricResponseURL, WatsonURL,
         CirrusStartedDateUtc, TipNodeSocId, TipNodeNodeId, TipNodeCluster,
         TipNodeMachinePoolName, TipNodeSessionId,
         OesBuildAgentVersion, OesBuildASAN, OesBuildContainer, OesBuildAgentBranch
| order by AdoBuildNumber desc
```

```kql
// TestCase outcome percentage — weekly trend
// Shows pass/fail/abort rates as percentages per week
OverlakeCirrusResult
| where CirrusStartedDateUtc between (ago(30d) .. now())
| summarize count() by bin(CirrusStartedDateUtc, 7d), CirrusOutcome
| join kind=inner (
    OverlakeCirrusResult
    | where CirrusStartedDateUtc between (ago(30d) .. now())
    | summarize total_count = count() by bin(CirrusStartedDateUtc, 7d)
) on CirrusStartedDateUtc
| extend percentage = round((count_ * 100.0) / total_count, 1)
| order by CirrusStartedDateUtc asc
```

```kql
// TestPass outcome percentage — weekly trend, with TestCategory
OverlakeCirrusTestpass
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where CirrusCreationTimeUtc between (ago(30d) .. now())
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| summarize count() by bin(CirrusCreationTimeUtc, 7d), CirrusStatus, TestCategory
| join kind=inner (
    OverlakeCirrusTestpass
    | where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
    | where CirrusCreationTimeUtc between (ago(30d) .. now())
    | where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
    | extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
    | summarize total_count = count() by bin(CirrusCreationTimeUtc, 7d), TestCategory
) on CirrusCreationTimeUtc, TestCategory
| extend percentage = round((count_ * 100.0) / total_count, 1)
| order by TestCategory asc, CirrusCreationTimeUtc asc
```

```kql
// Good builds analysis — builds where >300 individual test cases succeeded
// Useful for identifying known-good baselines
OverlakeCirrusResult
| where CirrusStartedDateUtc between (ago(30d) .. now())
| summarize SuccessfulCount = countif(CirrusOutcome == "Successful") by AdoBuildNumber
| where SuccessfulCount > 300
| join kind=inner (
    OverlakeCirrusResult
    | where CirrusStartedDateUtc between (ago(30d) .. now())
) on AdoBuildNumber
| summarize OutcomeCount = count() by AdoBuildNumber, CirrusOutcome
| order by AdoBuildNumber asc
```

---

<!-- PRIMITIVE:Diagnose -->
#### Diagnose

**Extends:** provider

Overlake extends the platform Diagnose (ApiAttempt, EnvironmentSelection, CER, AzureCM, TipNodeService) with OESBuild diagnostics, OvlProd node-level queries, and Overlake-specific failure patterns.

Inherits tool discovery and default MCP parameters from provider.md. Override cluster-uri per query as marked.

##### Diagnostic Conventions

Time Range Resolution and Terminology are inherited from provider.md — see **Query Conventions**.
TestCategory extraction and Presentation Rules are inherited from this file's Observe section — apply them to Diagnose reports too.

##### Diagnostic Flow

Provider handles platform diagnostic steps (launch status, completion, CER error matching, abort classification). Node health, cluster config, and TiP quota steps are 🚧 under construction at provider level — overlake provides working queries for these below. Overlake extends with:

1. **Identify TestCategory** → Extract TestCategory from `CirrusRequestName` to scope the diagnosis (Functional-Baremetal, Functional, Custom, Unmanaged)
   - *If empty/unrecognizable:* CirrusRequestName doesn't match any known prefix. Check for typos or new test types not yet in the extraction logic.
2. **CER drill-down with TSG** → Use ErrorBuckets for error details, map SubCategory to TSG URLs. Group errors by TestCategory.
   - *If empty:* No CER errors recorded. Possible ingestion delay (retry after a few minutes), or the failure is at the test pass level (not action level). Check `OverlakeCirrusTestpass.CirrusErrorMessage` as fallback.
3. **Per-agent failure distribution?** → Summarize failures by agent AND TestCategory to find systematic issues
   - *If empty:* No failed test passes for this filter/time range. The issue may be aborts (not failures) — check abort classification instead.
4. **Node-level diagnostics?** → Query `OvlProd` for systemd logs, service manager status, memory stats, service health, unit status for the specific agent/node/time window
   - *If empty:* No OvlProd telemetry for this node/time window. Agent may not have been deployed, or OvlProd ingestion is delayed. Verify the node ID and time range.
5. **OS/agent version?** → Query `OvlProd.LinuxOverlakeVersion` to check what version is deployed on the node
   - *If empty:* Version telemetry not available — agent may not report version info, or the node wasn't active during the query window.
6. **Node unhealthy during test?** → Cross-cluster join of test results with AzureCM node state changes, scoped to the test execution window
   - *If empty:* No unhealthy node state changes during the test window — node hardware was likely healthy. Focus on software/test-level issues instead.

##### Diagnostic Queries — Cirrus Cluster

**MCP Parameters:** `cluster-uri: https://cirrus.kusto.windows.net`, `database: cirrus` (default)

```kql
// CER drill-down — errors for a specific test pass with TSG URLs
// Handles both Functional and Custom tests
// Note: filters to isnotempty(ExceptionType) for actionable errors.
// If empty but test pass failed, re-query WITHOUT isnotempty filter to catch all error records.
ErrorBuckets
| where TestPassInstanceId == {test_pass_id}
| where isnotempty(ExceptionType)
| extend CirrusRunSetURL = strcat("https://cirrusperf.azurewebsites.net/v1/query?key=", RunSetId, "&type=RunSetId")
| project CreatedDateTime, ExceptionType, Category, SubCategory, Message,
         CirrusRunSetURL, ActionId, RunSetId
| order by CreatedDateTime asc
```

```kql
// Abort classification — categorize abort causes
// Note: ScheduleName in ApiAttempt may differ from CirrusRequestName in OESBuild
ApiAttempt
| where TimeStamp between (ago(1d) .. now())
| where Status == "Failed"
| where ScheduleName startswith "Cirrus-Functional" or ScheduleName startswith "Cirrus-Custom" or ScheduleName startswith "Cirrus_Unmanaged"
| summarize count() by Message
| extend AbortCategory = case(
    Message contains "No capacity was found", "TipCapacity",
    Message contains "cancel", "UserCancel",
    Message contains "timeout" or Message contains "Timeout", "Timeout",
    Message contains "quota", "QuotaExceeded",
    "InfraOrOther")
```

```kql
// Capacity abort percentage — what fraction of aborts are capacity-related?
// Cross-cluster: OESBuild (OverlakeCirrusTestpass) → Cirrus (ApiAttempt)
let AbortedReqIds = cluster('overlakees.westus2.kusto.windows.net').database('OESBuild').OverlakeCirrusTestpass
    | where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
    | where CirrusCreationTimeUtc between (ago(7d) .. now())
    | where CirrusStatus == "Aborted"
    | distinct CirrusRequestId;
ApiAttempt
| where OperationId in (AbortedReqIds)
| summarize TotalAborts = count(), CapacityAborts = countif(Message contains "No capacity was found")
| extend CapacityAbortPct = round(100.0 * CapacityAborts / TotalAborts, 1)
```

##### Diagnostic Queries — OESBuild Cluster

**MCP Parameters:** `cluster-uri: https://overlakees.westus2.kusto.windows.net`, `database: OESBuild`

```kql
// Test pass failure per agent — last 7 days, grouped by TestCategory
OverlakeCirrusTestpass
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where CirrusCreationTimeUtc between (ago(7d) .. now())
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| where CirrusStatus == "Failed"
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| summarize FailCount = count() by TestCategory, OesTestAgentName, OesTestAppModel
| order by TestCategory asc, FailCount desc
```

```kql
// Test case failure per agent — individual test case level
let totalFailedTests = toscalar(
    OverlakeCirrusResult
    | where CirrusStartedDateUtc between (ago(7d) .. now())
    | where CirrusOutcome == "Failed"
    | summarize totalCount = count()
);
OverlakeCirrusResult
| where CirrusStartedDateUtc between (ago(7d) .. now())
| where CirrusOutcome == "Failed"
| summarize count_ = count() by OesTestAgentName
| extend percentageOfTotalFailed = strcat(round((todouble(count_) / todouble(totalFailedTests)) * 100, 2), "%")
| project OesTestAgentName, count_, percentageOfTotalFailed
| order by count_ desc
```

```kql
// Test pass abort per agent — which agents are getting aborted most? Grouped by TestCategory
OverlakeCirrusTestpass
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where CirrusCreationTimeUtc between (ago(7d) .. now())
| where CirrusStatus == "Aborted"
| where AdoBuildDefinitionName in ('{ado_build_definition_name}') or '{ado_build_definition_name}' == ''
| extend TestCategory = case(CirrusRequestName startswith "Cirrus-Functional-Tests-DedicatedBaremetal", "Functional-Baremetal", CirrusRequestName startswith "Cirrus-Functional", "Functional", CirrusRequestName startswith "Cirrus-Custom", "Custom", CirrusRequestName startswith "Cirrus_Unmanaged", "Unmanaged", "Other")  // § Test Categories
| summarize count() by TestCategory, OesBuildName, OesTestAgentName, OesTestAppModel
| order by TestCategory asc, count_ desc
```

```kql
// Unique nodes accessed per cluster — verify tests are spreading across nodes
OverlakeCirrusResult
| where CirrusStartedDateUtc between (ago(7d) .. now())
| distinct TipNodeCluster, TipNodeNodeId
| summarize NodeCount = count() by TipNodeCluster
| order by TipNodeCluster
```

```kql
// Average completion time for non-aborted tests
OverlakeCirrusTestpass
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where CirrusCreationTimeUtc between (ago(7d) .. now())
| where CirrusStatus != "Aborted"
| extend Duration = CirrusCompletionTimeUtc - CirrusCreationTimeUtc
| summarize AvgDurationRaw = avg(Duration)
| extend AvgDurationMinutes = toint(AvgDurationRaw / 1m)
| extend AvgDuration = strcat(AvgDurationMinutes / 60, "h ", AvgDurationMinutes % 60, "m")
| project AvgDuration
```

##### Diagnostic Queries — OvlProd Cluster

**MCP Parameters:** `cluster-uri: https://azcore.centralus.kusto.windows.net`, `database: OvlProd`

The following OvlProd tables all use the same query pattern. Substitute `{table_name}` and add the appropriate filter:

**Base pattern:**
```kql
// Node-level diagnostics — substitute table and filter
{table_name}
| where TIMESTAMP between (ago(1d) .. now())
| where NodeId == '{tip_node_soc_id}' and Cluster == '{tip_node_cluster}'
| where {agent_filter}
| order by TIMESTAMP asc
```

| Table | `{agent_filter}` | When to use |
|-------|-------------------|-------------|
| `LinuxOverlakeSystemd` | `_SYSTEMD_UNIT contains '{agent_name}'` | Boot Health, Service Status failures (default) |
| `LinuxOverlakeSystemd` | `MESSAGE contains 'AVC avc' and MESSAGE contains '{agent_name}'` | SE Linux test failures only |
| `OverlakeServiceManagerStatus` | `ServiceName contains '{agent_name}'` | Systemctl status output |
| `OverlakeMemoryStatTable` | `Name contains '{agent_name}'` | Memory usage per agent |
| `OverlakeServiceHealthTable` | `Name contains '{agent_name}'` | Agent service health |
| `OverlakeUnitStatusTable` | `Name contains '{agent_name}'` | Systemd unit status |

For `LinuxOverlakeSystemd`, also project: `PreciseTimeStamp, _SYSTEMD_UNIT, MESSAGE, SYSLOG_IDENTIFIER, Cluster, TIMESTAMP`

```kql
// Linux Overlake version — OS and agent version installed on the node
LinuxOverlakeVersion
| where TIMESTAMP between (ago(1d) .. now())
| where NodeId == '{tip_node_soc_id}'
```

```kql
// Distinct Overlake versions on cluster(s) — check for version skew
LinuxOverlakeVersion
| where TIMESTAMP between (ago(7d) .. now())
| where Cluster in ('{cluster_name}')
| distinct product, PRETTY_NAME
```

```kql
// Count of Overlake versions per product on cluster(s)
LinuxOverlakeVersion
| where TIMESTAMP between (ago(7d) .. now())
| where Cluster in ('{cluster_name}')
| summarize Count = dcount(NodeId) by product
```

##### Diagnostic Queries — Cross-Cluster

> **Performance note:** Cross-cluster queries (joining OESBuild with AzureCM) can be slow. Narrow time range to 1d when possible. If queries time out, query each cluster separately and correlate manually.

**MCP Parameters:** Execute from OESBuild cluster: `cluster-uri: https://overlakees.westus2.kusto.windows.net`, `database: OESBuild`

```kql
// Test pass with unhealthy node correlation — flags test passes where the node
// went Unhealthy or HumanInvestigate during test execution window
// Requires cross-cluster join to AzureCM
let testResults = OverlakeCirrusResult
    | where CirrusStartedDateUtc between (ago(7d) .. now())
    | where OesBuildName in ('{oes_build_name}') or '{oes_build_name}' == '';
let nodes = testResults
    | distinct CirrusTestPassId, TipNodeNodeId, TipNodeSocId, TipNodeSessionId,
              CirrusStartedDateUtc, CirrusCompletedDateUtc;
let unhealthy = cluster('azurecm.kusto.windows.net').database('AzureCM').TMMgmtNodeStateChangedEtwTable
    | where PreciseTimeStamp between (ago(7d) .. now())
    | where BladeID in (nodes | project TipNodeNodeId)
    | where NewState == "Unhealthy" or NewState == "HumanInvestigate"
    | project stateChangeTime = PreciseTimeStamp, TipNodeNodeId = BladeID, NewState;
let unhealthyTestPassIds = nodes
    | join kind=inner unhealthy on TipNodeNodeId
    | where stateChangeTime between (CirrusStartedDateUtc .. CirrusCompletedDateUtc)
    | summarize UnhealthyCount = count() by CirrusTestPassId, TipNodeNodeId
    | project CirrusTestPassId, UnhealthyCount;
OverlakeCirrusTestpass
| where CirrusRequestName startswith "Cirrus-Functional" or CirrusRequestName startswith "Cirrus-Custom" or CirrusRequestName startswith "Cirrus_Unmanaged"
| where CirrusCreationTimeUtc between (ago(7d) .. now())
| join kind=fullouter unhealthyTestPassIds on CirrusTestPassId
| extend UnhealthyOrHI = iif(UnhealthyCount > 0, "Yes", "No")
| project-away CirrusTestPassId1, UnhealthyCount
```

```kql
// TiP Service Available Quota — cross-cluster join of cluster capacity + fabric settings
// Shows how many TiP sessions/nodes are still allocable per cluster
let OES_ClusterTipCapacity =
    cluster('azurecm.kusto.windows.net').database('AzureCM').AllocableVmCount
    | where PreciseTimeStamp between (ago(7d) .. now())
    | where vmType == "IOwnMachine" and deploymentType == "NewDeployment" and partitionType == "Cluster"
    | where Tenant in ('{cluster_name}')
    | where partitionName contains "PrdApp" or partitionName contains "PrdHPC"
        or partitionName contains "PrdGPC" or partitionName contains "PrdGPZ"
        or partitionName contains "PrdGPM" or partitionName contains "PrdFPG"
        or partitionName contains "PrdDDC"
    | summarize max(vmCount) by ClusterName=partitionName, bin(PreciseTimeStamp, 10m)
    | project-rename AllocableEmptyNodeCount=max_vmCount
    | join kind=inner hint.strategy=broadcast (
        cluster('azurecm.kusto.windows.net').database('AzureCM').LogNodeSnapshot
        | where PreciseTimeStamp between (ago(7d) .. now())
        | summarize arg_max(PreciseTimeStamp, tipNodeSessionId) by nodeId, ClusterName=Tenant, bin(PreciseTimeStamp, 10m)
        | extend IsTipSession = tipNodeSessionId != "00000000-0000-0000-0000-000000000000"
        | summarize TipSessionsCount=dcount(tipNodeSessionId), TipNodesCount=countif(IsTipSession) by ClusterName, bin(PreciseTimeStamp, 10m)
    ) on ClusterName, PreciseTimeStamp
    | project PreciseTimeStamp, ClusterName, TipSessionsCount, TipNodesCount, AllocableEmptyNodeCount;
let _FabricSettings =
    cluster('azurecm.kusto.windows.net').database('AzureCM').TMMgmtFabricSettingEtwTable
    | where PreciseTimeStamp between (ago(7d) .. now())
    | summarize arg_max(PreciseTimeStamp, *) by ClusterName=Tenant, Name
    | where Name in (
        "Fabric.TiP.AllowNewTipNodeSessions",
        "Fabric.TiP.MaxTipNodeSessionsPerCluster",
        "Fabric.TiP.MaxTipNodesPerCluster"
    )
    | extend p = pack(Name, Value)
    | summarize FabricSettings=make_bag(p) by ClusterName;
OES_ClusterTipCapacity
| project PreciseTimeStamp, ClusterName, TipNodesCount, TipSessionsCount
| join kind=inner (
    _FabricSettings
    | where ClusterName in ('{cluster_name}')
    | extend
        MaxTipNodesPerCluster = tolong(FabricSettings["Fabric.TiP.MaxTipNodesPerCluster"]),
        MaxTipNodeSessionsPerCluster = tolong(FabricSettings["Fabric.TiP.MaxTipNodeSessionsPerCluster"])
) on ClusterName
| extend
    AllocableTipNodes = MaxTipNodesPerCluster - TipNodesCount,
    AllocableTipSessions = MaxTipNodeSessionsPerCluster - TipSessionsCount
| summarize totalAvailableTipSessions = sum(AllocableTipSessions), TotalAvailableTipNodes = sum(AllocableTipNodes) by PreciseTimeStamp
```

For diagnostic deep links (Watson, Systemd, NodeStory, FabricResponse), use the Enhanced test results query in the Observe section.

##### Diagnostic Knowledge

###### Failure Patterns

Platform patterns (GatewayTimeout, capacity, TiP quota, cluster-to-AZ, EnvironmentSelection, node unhealthy, ClusterInInvalidState, Deploy App Over OM timeout) are in provider.md. Overlake-specific patterns:

| Symptom | SubCategory | Root Cause | Fix | TSG |
|---------|-------------|-----------|-----|-----|
| `DeploymentTimeout` in CER | `DeploymentTimeout` | PFClient OverlakeES deployment timed out — DABTOO timeout on target node | Increase `AppOverOMTimeoutInSecondsPostImageBuild` or investigate node-level OM deployment | [aka.ms/dabtootimeout](https://eng.ms/docs/products/autopilot/deployment/pfclientoverlake/usermanual/troubleshootdabtootimeout) |
| `PF-InvalidServiceConfigIni` in CER | `PF-InvalidServiceConfigIni` | Service verification failed during image build — invalid service config INI | Fix the service configuration in the agent's build definition | [Troubleshoot image building](https://eng.ms/docs/products/autopilot/autopilot/deployment-cookbook/troubleshooting-image-building-fails#service-verification-errors) |
| `PF-PathNotFound` in CER | `PF-PathNotFound` | Expected file path not found on the node — typically a build artifact issue | Verify agent repo produces the expected output paths; check if PR build succeeded | [Agent repo PR guide](https://eng.ms/docs/products/overlake/es/test/cirrus/common#2-agent-repo-pull-request) |
| Boot Health: `LoadState: actual='' expected='loaded'` | — | Agent service not loaded on the node — systemd unit file missing or failed to install | Check OvlProd.LinuxOverlakeSystemd for the agent's journalctl output; check OvlProd.OverlakeServiceManagerStatus for systemctl status; verify agent deployment completed. | — |
| Boot Health: `ActiveState: actual='inactive' expected='active'` | — | Agent installed but not running — service crashed or failed to start | Check OvlProd.LinuxOverlakeSystemd for crash logs; check OvlProd.OverlakeMemoryStatTable for OOM kills; check OvlProd.OverlakeServiceHealthTable for health status. | — |
| Memory monitor test failed — usage exceeds MEMORY_LIMIT | — | Agent consuming more memory than configured limit | Check OvlProd.OverlakeMemoryStatTable for memory trend; may indicate a memory leak in the agent build. | — |
| SE Linux test failed — AVC denial | — | SELinux policy blocks the agent's operations | Check OvlProd.LinuxOverlakeSystemd filtered for `AVC avc` messages containing the agent name; update SELinux policy in agent build. | — |
| Overlake version mismatch across cluster nodes | — | Nodes running different OS/agent versions — possible mid-rollout state | Check OvlProd.LinuxOverlakeVersion for version distribution across the cluster; may cause inconsistent test behavior. | — |

###### Known Candidate Clusters

| AppModel | Default Candidate Clusters |
|----------|--------------------------|
| 1908 | HKG20PrdApp18, HKG21PrdApp20, HKG23PrdApp08, HKG23PrdGPZ01, DZ6PrdApp15, DSM06PrdApp18 |
| 2008 | CVL02PrdApp12, MWH03PrdApp19, MWH03PrdApp20, PHX70PrdApp32, LVL08PrdApp36, DUB24PrdApp22 |

###### Known Agents

Target agents for Overlake SoC testing:

`ContainerService`, `HostPrepAgent`, `NodeService`, `shepherdfwupdater`, `vnetagent`, `mhpbuagent`, `sochwmon`, `sochwmon_rust`, `AutoPilotAttestationAgent`

###### Known Test Cases

Standard functional tests: `Boot Health test`, `Service Status test`, `Soc Pre-Reboot test`, `Soc Post-Reboot test`, `Memory monitor test`, `SE Linux test`

A test pass is considered fully passing when all configured test cases succeed.

###### Environment Checks

Platform environment checks (Cirrus cluster reachability, fabric settings, capacity, TiP quota) are in provider.md. Overlake-specific checks:

- Verify the developer has access to the Cirrus tenant (check CirrusTenants.json for their security group)
- Verify the OESBuild cluster is reachable: `https://overlakees.westus2.kusto.windows.net`
- Verify the OvlProd cluster is reachable: `https://azcore.centralus.kusto.windows.net` (required for systemd logs, service health, version queries)

###### Cascade Rules

Platform cascade rules (TiP session failure, launch failure, abort, parent action cascade, unhealthy node, TiP quota) are in provider.md. Overlake-specific rules:

- If `SubCategory` matches a known pattern in Failure Patterns table → **stop diagnostic cascade**, use the TSG URL, and report. If no SubCategory match → report raw ExceptionType + Message and continue diagnosis.
- If Boot Health or Service Status fails, check OvlProd systemd logs BEFORE concluding agent bug — service may not have been deployed correctly (check `OverlakeServiceManagerStatus` first).

---

<!-- PRIMITIVE:Report -->
#### Report

**Status:** passthrough
**Reason:** Report format will be defined in a future version. The Summarize phase in the agent handles result presentation for now.
