---
name: dev-setup
description: |
  First-time developer setup for the Azure Test Platform.
  Discovers available providers, collects required settings via interactive interview,
  and generates a valid octane.yaml configuration.
  Use when: setting up a new workspace, adding a provider, or reconfiguring settings.
user-invocable: true
---

# Dev Setup

First-time developer setup for the Azure Test Platform. Discovers available provider toolkits, collects required settings, and writes a valid `.config/octane.yaml` configuration.

## Inputs

- `provider` (string, optional): Which provider to configure. If omitted, discovered from available provider toolkits.

## Workflow

### Step 1 — Discover Available Providers

1. List directories under `skills/azure-test-toolkit/references/` (exclude template files like `*.template.md`)
2. For each directory, read `skills/azure-test-toolkit/references/{provider}/provider.md`
3. Extract from `<!-- NAVIGATION -->`:
   - Provider name (H1 heading)
   - Available test types (`none` means flat provider — no test types)
4. Present the list to the developer:

   > **Available providers:**
   > | Provider | Available Test Types |
   > |----------|---------------------|
   > | cirrus   | overlake            |
   >
   > Which provider(s) do you want to configure?

5. If `provider` input was specified, skip this and use it directly

> **Note:** Provider directories and toolkits are located under `skills/azure-test-toolkit/references/` in the workspace root (installed by octane).

### Step 2 — Collect Settings

For each selected provider:

1. Read `skills/azure-test-toolkit/references/{provider}/provider.md`
2. Extract the **Required Settings** table
3. Extract the **Optional Settings** table
4. Ask the developer for each required setting:

   > **Configuring cirrus:**
   >
   > I need these required settings:
   > | Setting | Description | Example |
   > |---------|-------------|---------|
   > | `cirrus_tenant` | Cirrus tenant name | `OverlakeES` |
   > | `subscription_id` | Cirrus subscription ID | `xxxxxxxx-xxxx-...` |
   >
   > Please provide values for each.

5. After required settings, ask:

   > **Optional settings** (press Enter to skip each):
   > | Setting | Description | When needed |
   > |---------|-------------|------------|
   > | `requested_by` | Your alias for query filtering | To scope queries by requestor |
   > | `ado_organization` | ADO org | If using ADO Pipeline Extension |
   > | ... | ... | ... |

6. Ask about test type (only if the provider has Available Test Types other than `none`):

   > This provider supports these test types: **{available_types}**. Which one applies to your team?

   If the developer says "none of these" or skips, omit `test_type` from config — the agent will use the provider's general primitives.

7. Ask about context files:

   > Do you have any personal notes, KQL queries, or docs files you want loaded as context? (Optional — provide file paths, or skip)

### Step 3 — Confirm

Present the complete configuration to the developer:

```yaml
azure-test-platform:
  primitives:
    - Observe
    - Diagnose

  test_providers:
    {provider}:
      enabled: true
      test_type: {test_type}        # omit this line for flat providers or if developer skipped test type
      settings:
        {key}: {value}
        ...
      context:
        - {path}
```

Ask: "Does this look correct? I'll write it to `.config/octane.yaml`."

### Step 4 — Write Configuration

1. Read the existing `.config/octane.yaml` (if it exists)
2. Merge the new provider configuration under `azure-test-platform.test_providers`
   - If the provider already exists, ask before overwriting
   - Preserve any existing providers the developer didn't reconfigure
3. Write the updated file to `.config/octane.yaml`
4. Confirm:

   > Configuration saved to `.config/octane.yaml`.
   >
   > **Next steps:**
   > - Say `@AzureTestEngineer check status` to verify connectivity
   > - Say `@AzureTestEngineer what failed?` to check for failures

### Step 5 — Verify MCP Server

1. Check if `.vscode/mcp.json` exists and contains `azure-mcp`
2. If missing, tell the developer:

   > The `azure-mcp` MCP server is required for Kusto queries. Add it to `.vscode/mcp.json`:
   > ```json
   > {
   >   "servers": {
   >     "azure-mcp": {
   >       "type": "stdio",
   >       "command": "npx",
   >       "args": ["--registry", "https://registry.npmjs.org", "-y", "@azure/mcp@latest", "server", "start", "--namespace", "kusto"]
   >     }
   >   }
   > }
   > ```

3. If present, confirm: "MCP server `azure-mcp` is configured."

## Expected Output

A valid `.config/octane.yaml` file with the developer's provider settings, written after confirmation. The file contains the `azure-test-platform` block with enabled providers, settings, and optional context paths. The `test_type` field is included only for providers that have test types and where the developer selected one.

## Rules

- Ask one section at a time — don't dump all settings at once
- Show examples from the provider's Required Settings table
- Never write config without developer confirmation
- If a provider directory doesn't have `provider.md`, skip it and warn
- Preserve existing config — merge, don't replace
