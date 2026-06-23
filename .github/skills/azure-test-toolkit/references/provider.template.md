# {Provider Name}
<!-- 
  INSTRUCTIONS FOR PROVIDER TEAMS:
  
  Replace {Provider Name} with your test system name (e.g., Cirrus, CloudTest).
  Fill in each section below. Lines starting with {placeholder} need your input.
  Remove this comment block when done.

  NAMING RULES:
  - Provider directory name must match: ^[a-zA-Z0-9_-]+$
  - Test type file names must also match this pattern (e.g., overlake.md, guest-agent.md)
  - No spaces, dots, or path separators allowed
-->

**Schema:** 1

<!-- NAVIGATION -->
**Available Test Types:** {comma-separated list of test type names (each must have a matching .md file), or "none" for flat providers}
**Reading Order:** Read this file first. If a test type is resolved, read the test type file next.
**Platform Primitives:** {list of primitives defined in this file — e.g., Observe, Diagnose}
<!-- /NAVIGATION -->

## Required Settings

<!-- 
  Settings a developer provides in octane.yaml. Split into required vs optional.
  The dev-setup skill reads these tables to know what to ask.
  "Required for" tells the developer which primitives need this setting.
-->

| Key | Description | Example | Required for |
|-----|-------------|---------|-------------|
| `{key}` | {What this setting is for} | `{example}` | {which primitives need it} |

## Optional Settings

| Key | Description | Example | When needed |
|-----|-------------|---------|------------|
| `{key}` | {What this setting is for} | `{example}` | {When this setting is relevant} |

## MCP Data Source

<!--
  If primitives use Method: mcp, describe how the AI discovers and invokes the tool.
  Include: MCP server name, tool discovery pattern, available commands, default parameters.
  See cirrus/provider.md for a reference implementation.
-->

**VS Code Tool Discovery:**
```
tool_search_tool_regex("{pattern}")   → finds the MCP tool
<tool>(learn=true)                    → returns available commands
```

**Available Commands:**

| MCP Command | Required Parameters | Notes |
|-------------|-------------------|-------|
| `{command}` | `{params}` | {description} |

**Default Parameters for this provider:**

| Parameter | Value |
|-----------|-------|
| `{param}` | `{value}` |

## Common Metadata

<!--
  Values here are inherited by all test type files unless overridden.
  The AI reads these once, then uses them across all primitives.
-->

**Cluster:** {Kusto cluster URL, e.g., https://clustername.kusto.windows.net}
**Database:** {Kusto database name}
**Auth:** {auth method — cli(az), env-var(VAR), token-file(path), none, or custom}

<!-- INTERVIEW: If your provider has a web portal, add it here -->
**Portal:** {portal URL, or remove this line if none}

### Common Tables

<!--
  List all Kusto tables the AI may need across primitives.
  Group by cluster if your provider uses multiple clusters.
  Include deployment/event tracking tables (e.g., DeploymentEvent) if applicable.
-->

| Table | What it contains |
|-------|-----------------|
| `{TableName}` | {Brief description of what's in this table} |
<!-- INTERVIEW: Include deployment event tables if your provider tracks deployments across test passes (e.g., DeploymentEvent with TenantName, Schedule, RunGuid mapping). -->

### Key Functions

<!-- INTERVIEW: List any Kusto functions that return pre-aggregated or convenience views. -->

| Function | What it returns |
|----------|----------------|
| `{FunctionName(params)}` | {What it returns} |

### Error Records

<!-- INTERVIEW: If your provider has a centralized error store (like Cirrus CER / ErrorBuckets), describe the table and key fields here. -->

| Field | Description |
|-------|-------------|
| `{FieldName}` | {Description} |

## Skills Used

<!--
  List the platform skills this provider uses.
  Fill in when skills are available.
  Format: skill name, which primitives use it, path to SKILL.md
-->

| Skill | Used for | Path |
|-------|----------|------|
| | | |

## Query Conventions

<!--
  These conventions apply to ALL primitives and test types that use Kusto queries.
  Fill in each subsection with your provider's specifics.
-->

### Schema Discovery

<!--
  Table schemas can be discovered at runtime using KQL.
  This works on all clusters your provider uses.
  Use schema discovery when constructing new queries or when a column name is uncertain.
-->

Table schemas can be discovered at runtime using KQL. Use this instead of hardcoding column lists:

```kql
// Discover columns for any table
{table_name} | getschema | project ColumnName, ColumnType
// Or: .show table {table_name} schema as json
```

<!-- INTERVIEW: List all clusters where schema discovery applies (e.g., "Works on Primary, Secondary, and Diagnostics clusters"). -->

### Common ID Mapping

<!--
  The same entity often has different column names across clusters or views.
  Document all ID mappings so queries can bridge across data sources.
  This is critical for cross-cluster joins and parameter chaining.
-->

| Concept | {Primary Cluster} | {Secondary Cluster} | Notes |
|---------|-------------------|---------------------|-------|
| {entity ID, e.g., Test pass ID} | `{ColumnName}` ({type}) | `{ColumnName}` ({type}) | {Same value? Different format? Bridge query needed?} |
<!-- INTERVIEW: Add one row per entity that appears across multiple clusters or views. Include column types (long, guid, string) and note any bridge queries required (e.g., "Run | project RunId, RunGuid"). -->

### Parameter Chain

<!--
  Query placeholders ({param}) come from these sources.
  Document where each parameter originates so the AI can chain queries correctly.
-->

| Parameter | Source | How to get it |
|-----------|--------|---------------|
| `{param_name}` | {Required Setting / Optional Setting / Query output / Bridge query} | {Description of how to obtain the value} |
<!-- INTERVIEW: List every query placeholder your provider uses. Include parameters from Required Settings, Optional Settings, and values obtained from prior query outputs. -->

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

<!--
  Define the execution hierarchy and status values for your provider.
  Include all entity types: test pass, run set, run, action, etc.
-->

| Term | Scope | Table | Status Field | Values |
|------|-------|-------|-------------|--------|
| {Term} | {Scope description} | `{Table}` | `{StatusField}` | {Comma-separated status values} |

<!-- INTERVIEW: If your provider has external views or projections that use different status values than the platform tables, document the mapping here. For example, OESBuild uses CirrusStatus (Succeeded, Failed, Aborted) and CirrusOutcome (Successful, Failed, Aborted) — where Aborted maps to Canceled in platform tables and CirrusOutcome "Successful" maps to CirrusStatus "Succeeded". -->

#### Execution Hierarchy

<!-- INTERVIEW: Show the nesting of execution entities. Example:
```
TestPass → 1+ RunSets (sequential by SequenceId)
  RunSet → 1+ Runs (parallel, controlled by Count)
    Run → 1+ Actions (sequential by SequenceId)
```
-->

```
{top-level entity} → {child entities}
  {child entity} → {grandchild entities}
```

#### FailureHandling Modes

<!--
  If your provider supports per-action or per-entity failure handling modes,
  document them here. This is critical for diagnosis — the AI needs to know
  whether a failure rolls up to the parent entity or is handled locally.
-->

| Mode | Behavior |
|------|----------|
| `{ModeName}` | {What happens when this mode is active and the entity fails} |
<!-- INTERVIEW: Common modes include AbortOnFailure (default — stops immediately), ContinueOnFailure (logs failure but continues), FastFailOnFailure (fails entire test pass). Document which property controls this (e.g., FailureHandlingOnException) and the diagnostic implication: if ContinueOnFailure is set, failures may not roll up to parent status — inspect individual results separately. -->

#### Early Failure Detection

<!-- INTERVIEW: If your provider has early failure indicators (e.g., a ContainsFailure boolean that is set while the parent is still Executing), document it here. This allows the AI to detect failures without waiting for terminal state. -->

### Presentation Guidelines

<!--
  Rules for how the AI formats Observe and Diagnose output.
-->

These apply to both Observe and Diagnose reports:

1. Use the time range from the developer's request. Default is `ago(1d)`.
2. Always show builds first. Never skip the build inventory.
3. Don't aggregate across builds unless explicitly asked.
<!-- INTERVIEW: Add provider-specific presentation rules (e.g., filter by build definition, show deep links to portal/ADO, use correct terminology for status vs outcome). -->

## Provider Notes

<!--
  Provider-wide context the AI should know.
  Include: known limitations, credentials/access requirements, launch methods,
  content repo location, support channels.
  Remove subsections that don't apply to your provider.
-->

<!-- INTERVIEW: Fill in the subsections below that apply to your provider. Remove any that don't. -->

### Permissions & Access

<!-- INTERVIEW: Document how developers get access to your provider's resources (security groups, Kusto access, content repo write access, common permission errors and fixes). -->

### Support Channels

<!-- INTERVIEW: List support channels — Stack Overflow tags, Teams channels, email, office hours, ICM service/team. -->

## Platform Primitives

<!--
  Define primitive sections here using sentinel format.

  For FLAT providers (Available Test Types: none):
    All primitives MUST be defined here. This file is the only source of truth.
    Each sentinel section must have Method and Auth.

  For TYPED providers (Available Test Types has entries):
    Platform primitives are OPTIONAL shared defaults that test type files can inherit.
    Test type files declare how they interact with each provider primitive:
    - **Inherits:** provider — Use provider's primitive as-is (thin test type section)
    - **Extends:** provider — Merge provider + test type content (provider gives platform
      queries/patterns, test type adds its own)
    - No marker (Override) — Test type defines everything; provider primitive is ignored

  See cirrus/provider.md for a reference implementation.
-->

These sentinel-marked sections provide platform-level defaults for primitives. Test type files can:
- **Inherit** (`**Inherits:** provider`) — use this section as-is, no test-type-specific content needed
- **Extend** (`**Extends:** provider`) — add test-type-specific content; agent reads provider section first, then test type section
- **Override** (no marker) — provide a complete replacement; agent ignores the provider section for this primitive

---

<!-- PRIMITIVE:Observe -->
#### Observe

<!-- INTERVIEW: Fill in the method, tool, and auth for your Observe primitive. -->

**Method:** mcp
**MCP Server:** `{mcp_server_name}`
**Tool:** `{tool_name}`
**Auth:** {auth method — inherited from Common Metadata}
**Data Source:** {cluster/database reference}
**Portal URL:** {portal URL}

##### Tool Discovery

```
tool_search_tool_regex("{pattern}")   → finds the MCP tool
<tool>(learn=true)                    → returns available commands
```

##### MCP Parameters (per query)

<!-- INTERVIEW: Default parameters for platform queries. Test type files may override per-query. -->

| Parameter | Value | Source |
|-----------|-------|--------|
| `{param}` | `{value}` | {source — e.g., Common Metadata} |

##### Platform Discovery

<!-- INTERVIEW: Add queries to find recent launch activity when no specific identifier is provided. -->

```kql
// {description of discovery query}
{your discovery KQL here}
```

##### Platform Query Flow

<!-- INTERVIEW: Describe the ordered flow of platform-level observation queries. -->

1. **{Step 1}** — {what to query and why}
2. **{Step 2}** — {what to query and why}
3. **If failures detected** — proceed to Diagnose

Test type files extend this flow with test-type-specific queries.

##### Platform Queries

<!-- INTERVIEW: Add all platform-level Observe KQL queries here, grouped by cluster if multiple. -->

**MCP Parameters:** `cluster-uri: {cluster_url}`, `database: {database_name}`

```kql
// {description}
{your KQL here}
```

---

<!-- PRIMITIVE:Diagnose -->
#### Diagnose

<!-- INTERVIEW: Fill in the method, tool, and auth for your Diagnose primitive. -->

**Method:** mcp
**MCP Server:** `{mcp_server_name}`
**Tool:** `{tool_name}`
**Auth:** {auth method — inherited from Common Metadata}

##### Tool Discovery

Same tool as Observe — if already discovered, skip.

```
tool_search_tool_regex("{pattern}")   → finds the MCP tool
```

##### Platform Diagnostic Flow

<!--
  IMPORTANT: Empty results are meaningful. The diagnostic flow must handle empty results
  at each step — do not skip them, do not automatically widen time range, do not
  hallucinate explanations. Interpret empty results in context of prior steps.

  For steps that are not yet implemented, mark them as "Under construction" so the AI
  knows not to attempt them.
-->

**Empty results are meaningful.** Do not skip empty results, do not automatically widen time range, do not hallucinate explanations. Interpret in context of prior steps.

<!-- INTERVIEW: Define each diagnostic step. For each step, include:
  - What to check and which table/query to use
  - What an empty result means (e.g., "Launch not found — verify schedule name, check time range")
  - What to do next based on the result
  Mark any steps not yet implemented as: 🚧 Under construction
-->

1. **{Step 1 — e.g., Did the launch succeed?}** → {query/table to check}
   - *If empty:* {what empty means and what to do}
2. **{Step 2}** → {query/table to check}
   - *If empty:* {what empty means and what to do}
3. **{Step 3}** → {query/table to check}
   - *If empty:* {what empty means and what to do}
4. **{Step 4 — e.g., Which action failed?}** → {Walk hierarchy, check error records}
   - *If error records empty AND entity failed:* {guidance — e.g., retry after delay for ingestion lag}
5. **{Step 5 — e.g., Node health / infra checks}** → 🚧 Under construction — {describe what will be added later}

Test type files extend this flow with test-type-specific diagnostic steps.

##### Platform Diagnostic Queries

<!--
  INTERVIEW: Add all platform-level Diagnose KQL queries here, grouped by cluster.
  Include:
  - Launch status queries
  - Environment/allocation queries
  - Error record queries (CER or equivalent)
  - ActionStatus query — current status of each action, including FailureHandlingOnException
  - Performance/metrics queries
  - Schedule attempt queries
  - Completion summary queries
  - Resource lifecycle queries (GC, TiP sessions, etc.)
  - Node health queries (if applicable, on diagnostics cluster)
  - Cluster config queries (if applicable)
  - Quota queries (if applicable)
-->

**MCP Parameters:** `cluster-uri: {cluster_url}`, `database: {database_name}`

```kql
// {description — e.g., Launch request status}
{your KQL here}
```

```kql
// ActionStatus — current status of each action in a test pass
// Use after error records to see which actions failed, succeeded, or were not started
// INTERVIEW: Adapt this query for your provider's action/step status table.
// Include the failure handling mode column so the AI can determine rollup behavior.
{ActionStatus_or_equivalent}
| where {test_pass_filter}
| project {ActionId}, {Status}, {FailureHandlingMode}, {StartTime}, {EndTime}, {Description}
| order by {sort_fields}
```

##### Platform Diagnostic Knowledge

###### Platform Failure Patterns

<!-- INTERVIEW: Document known failure patterns specific to your provider. -->

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| {error message or symptom} | {what causes it} | {how to fix it} |

###### Platform Cascade Rules

<!-- INTERVIEW: Document how failures cascade through the execution hierarchy. -->

<!-- Examples of cascade rules:
- If environment setup fails → all downstream actions will fail. Focus on setup, not action results.
- If launch fails (no test pass ID) → don't query error records.
- If a parent action fails, child actions may cascade-fail. Focus on the first failing action.
- If action's FailureHandlingOnException is ContinueOnFailure, that failure may not roll up to parent status — check individual action results via ActionStatus separately.
- If ContainsFailure=True but Status=Executing → cleanup is still running. Report failure early but note cleanup in progress.
-->

###### Platform Environment Checks

<!-- INTERVIEW: List environment/connectivity checks the AI should verify during diagnosis. -->

- Verify {cluster/service} is reachable: `{URL}`
