# {test_type_name}
<!--
  INSTRUCTIONS FOR PROVIDER TEAMS:

  Replace {test_type_name} with the test type name (e.g., tip, functional, qemu).
  This filename must match the test_type value in octane.yaml.

  This file must have a sentinel section for EVERY primitive listed in
  config/octane.yaml under azure-test-platform.primitives.
  Currently active: Observe, Diagnose. Future (passthrough): Build, Run, Report, Author.

  EVERY active (non-passthrough) section follows the same pattern:
    Method  — how it executes (pipeline, script, command, api, mcp, query, skill)
    Auth    — how it authenticates (inherited from provider.md unless overridden)

  See the SKILL.md in the azure-test-toolkit skill for the full contract.
  Remove this comment block when done.
-->

**Schema:** 1
**Description:** {Brief description of what this test type covers}

---

<!-- PRIMITIVE:Build -->
#### Build

**Method:** {pipeline | script | command | api | mcp}
**Auth:** {auth method — inherited from provider.md unless overridden}

##### Parameters

| Parameter | Source | Description |
|-----------|--------|-------------|
| `{param_name}` | {config setting, user input, or hardcoded} | {What this parameter does} |

---

<!-- PRIMITIVE:Run -->
#### Run

<!--
  If test execution is implicit in the Build step, declare passthrough.
  Otherwise, specify Method and Auth like any other primitive.

  If provider.md defines a Platform Primitive for Run, you can inherit or extend it:
  - **Inherits:** provider — Use provider's Run as-is (thin section, no Method needed)
  - **Extends:** provider — Merge provider + this section
  - No marker — Override: define everything here, ignore provider
-->

**Status:** passthrough
**Reason:** {Why Run is implicit in Build, or remove these lines and fill in Method/Auth below}

<!-- If inheriting from provider:
**Inherits:** provider
{Brief description of why no override is needed}
-->

<!-- If NOT passthrough and NOT inheriting:
**Method:** {pipeline | script | command | api | mcp}
**Auth:** {auth method}

##### Parameters

| Parameter | Source | Description |
|-----------|--------|-------------|
| `{param_name}` | {source} | {description} |
-->

---

<!-- PRIMITIVE:Observe -->
#### Observe

<!--
  If provider.md defines a Platform Primitive for Observe, you can inherit or extend it:
  - **Inherits:** provider — Use provider's Observe as-is
  - **Extends:** provider — Merge provider + this section (provider handles platform queries,
    this section adds test-type-specific queries)
  - No marker — Override: define everything here
-->

**Method:** {query | api | mcp | script}
**Auth:** {auth method — inherited from provider.md unless overridden}
**Data Source:** {Kusto cluster+database, REST API, MCP tool name, etc.}
**Portal URL:** {URL to the provider's results portal, if applicable}

<!-- If extending provider:
**Extends:** provider
**Data Source:** {additional data sources beyond provider}
{Description of what this test type adds to the platform Observe}
-->

<!-- If Method is mcp, include these fields:
**MCP Server:** {MCP server name from .vscode/mcp.json, e.g., azure-mcp}
**Tool:** {MCP command name, e.g., kusto_query}
-->

##### Tool Discovery

<!--
  How the AI discovers and invokes the MCP tool at runtime.
  Use tool_search_tool_regex to find the tool, then call with learn=true.
  Example:
  ```
  tool_search_tool_regex("mcp_azure.*kusto")   → finds the kusto MCP tool
  <kusto_tool>(learn=true)                       → confirms kusto_query command exists
  ```
-->

##### MCP Parameters (per query)

<!--
  If the provider uses multiple data sources (e.g., multiple Kusto clusters),
  specify default parameters here and override per-query below.
-->

| Parameter | Value | Source |
|-----------|-------|--------|
| `{param}` | `{value}` | provider.md |

##### Discovery

<!--
  How the AI finds what to work on when the developer provides no identifier.
-->

{Discovery query, MCP tool call, or API call here}

##### Query Flow

1. {First step — e.g., "Query TestPassV2 for the most recent test pass"}
2. {Second step — e.g., "If failed, query ActionResults for failed actions"}
3. {Continue as needed}

##### Queries

<!--
  The actual queries, MCP tool calls, or API calls referenced by the Query Flow.
  Use code blocks for KQL. For MCP, reference the tool name and parameters.
  Mark each query with its data source if using multiple clusters.
-->

```kql
// {Description of what this query returns}
{TableName}
| where {conditions}
| project {columns}
```

---

<!-- PRIMITIVE:Diagnose -->
#### Diagnose

<!--
  If provider.md defines a Platform Primitive for Diagnose, you can inherit or extend it:
  - **Inherits:** provider — Use provider's Diagnose as-is
  - **Extends:** provider — Merge provider + this section (provider handles platform diagnostics,
    this section adds test-type-specific queries, failure patterns, and cascade rules)
  - No marker — Override: define everything here
-->

**Method:** {query | api | mcp | script}
**Auth:** {auth method — inherited from provider.md unless overridden}

<!-- If extending provider:
**Extends:** provider
{Description of what this test type adds to the platform Diagnose}
-->

<!-- If Method is mcp, include:
**MCP Server:** {MCP server name}
**Tool:** {MCP command name}
-->

##### Tool Discovery

<!--
  Same tool as Observe — if already discovered, skip.
-->

##### Diagnostic Queries

<!--
  The queries or MCP tool calls that fetch failure telemetry.
  The AI runs these, then matches results against Diagnostic Knowledge below.
-->

```kql
// {Description — e.g., "Get error details for failed actions"}
{TableName}
| where {conditions}
| project {columns}
```

##### Diagnostic Knowledge

<!--
  The provider's encoded expertise. The AI matches telemetry against this.
  Failure Patterns table is REQUIRED.
  Environment Checks and Cascade Rules are optional but recommended.
-->

###### Failure Patterns

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| {What the developer sees} | {Why it happens} | {What to do} |

###### Environment Checks

<!--
  Optional: preconditions to verify before querying.
  Remove if not needed.
-->

###### Cascade Rules

<!--
  Optional: dependency chains — which failures are downstream of which.
  Remove if not needed.
-->

---

<!-- PRIMITIVE:Report -->
#### Report

**Method:** {skill | mcp | custom}
**Extra Sections:** {none, or list additional sections the report should include}
