---
name: azure-test-toolkit
description: |
  Provider toolkit contract and reference files for the Azure Test Platform.
  Contains the template schemas, filled provider toolkits, and validation script
  that define how test providers are onboarded and how the AI agent navigates
  provider-specific queries, failure patterns, and diagnostic knowledge.
  Use when: onboarding a new provider, validating toolkit files, or understanding
  the primitive interface contract.
---

# Azure Test Toolkit

This skill contains the toolkit contract, provider reference files, and validation tooling for the Azure Test Platform scenario.

## Files

| File | Purpose | When to use |
|------|---------|-------------|
| [provider.template.md](references/provider.template.md) | Provider index scaffold — navigation, required settings, common metadata | Copy when onboarding a new provider |
| [test-type.template.md](references/test-type.template.md) | Test type scaffold — one per mode within a provider | Copy when adding a test type to a provider |
| [cirrus/provider.md](references/cirrus/provider.md) | Cirrus provider index — clusters, tables, settings, platform primitives | Reference implementation for provider onboarding |
| [cirrus/overlake.md](references/cirrus/overlake.md) | Overlake test type toolkit — queries, failure patterns, diagnostic knowledge | Reference implementation for test type onboarding |
| [cirrus/guest-agent.md](references/cirrus/guest-agent.md) | GuestAgent test type toolkit — workload phases, NuGet builds, performance metrics, and diagnostic knowledge | Reference implementation for workload-based test type onboarding |
| [validate-toolkit.ps1](scripts/validate-toolkit.ps1) | PowerShell validator — checks sentinel structure, passthrough rules, inheritance | Run after editing any toolkit file |

## The Primitive Interface

The active primitives are defined centrally in `config/octane.yaml` under `azure-test-platform.primitives`. Every provider file (flat mode) or test type file (typed mode) must have a sentinel-marked section for each primitive in that list. Currently active:

```
<!-- PRIMITIVE:Observe -->   — How the AI checks results
<!-- PRIMITIVE:Diagnose -->  — How the AI identifies root cause
```

Future primitives (not yet active — sentinels may exist as passthrough in toolkit files):

```
<!-- PRIMITIVE:Build -->     — How code gets built (planned)
<!-- PRIMITIVE:Run -->       — How tests execute (planned)
<!-- PRIMITIVE:Report -->    — How results are rendered (planned)
<!-- PRIMITIVE:Author -->    — How tests are created (planned)
```

Adding a new primitive means: add it to `primitives` in `octane.yaml` → add the sentinel to provider files (flat) or test type files (typed) → update the agent's Workflow Routing table.

### Consistent Fields

Every active (non-passthrough) primitive section must have:

| Field | Required | Description |
|-------|----------|-------------|
| **Method** | Yes | How this primitive executes: `pipeline`, `script`, `command`, `api`, `mcp`, `query`, `skill` |
| **Auth** | No | How it authenticates. Inherited from `provider.md` unless overridden. Options: `cli(tool)`, `env-var(VAR)`, `token-file(path)`, `none`, `custom` |

### Methods

| Method | When to use | Who provides it |
|--------|-------------|-----------------|
| `pipeline` | Standard ADO pipeline build | Platform |
| `script` | Complex launch logic | Provider (follows Script Contract) |
| `command` | Simple one-liner (e.g., `dotnet test`) | Provider |
| `api` | REST API integration | Provider |
| `mcp` | Typed MCP tool call — prevents hallucination | Provider |
| `query` | KQL or other query language | Provider |
| `skill` | Platform-provided execution engine | Platform |

### Passthrough

When a primitive doesn't apply to this provider or test type:

```markdown
<!-- PRIMITIVE:Run -->
#### Run
**Status:** passthrough
**Reason:** Execution is implicit in Build.
```

Rules:
- Must have `**Status:** passthrough` AND `**Reason:**`
- Must NOT have `**Method:**`, `**Auth:**`, or any execution fields
- Sentinel must still be present (keeps navigation deterministic)

## Provider Index (`provider.md`)

### Required

| Field | Description |
|-------|-------------|
| `<!-- NAVIGATION -->` sentinel | Machine-findable section boundary |
| `**Schema:**` | Schema version number (currently `1`) — enables backward-compatible parsing |
| `**Available Test Types:**` | Comma-separated list of test types (each must have a matching `.md` file), or `none` for flat providers |

### Required Settings Table

```markdown
| Key | Description | Example |
|-----|-------------|---------|
| `subscription` | Azure subscription ID | `xxxxxxxx-xxxx-...` |
```

The dev-setup skill reads this table to know what to ask developers during configuration.

### Inheritable Metadata

These fields in `provider.md` are inherited by all test type files (typed mode) unless overridden:

- `**Cluster:**` — Kusto cluster URL
- `**Database:**` — Kusto database name
- `**Auth:**` — authentication method

### Provider-Only Primitives (Flat Mode)

When a provider declares `Available Test Types: none`, or when the user chooses general provider diagnostics instead of a specific test type, the agent reads primitive sentinels directly from `provider.md`.

Requirements for provider.md primitives in flat mode:
- All primitives from `azure-test-platform.primitives` must have sentinel sections in `provider.md`
- Each sentinel section must have `**Method:**` and optionally `**Auth:**` (no inheritance — this IS the source)
- Passthrough rules apply the same as test type files

### Platform Primitives & Inheritance (Typed Mode)

> This section applies only to providers with test types. When using `provider.md` directly (flat mode), there is no inheritance — `provider.md` is the single source.

Providers with test types can optionally define **platform-level primitive defaults** in `provider.md` under a `## Platform Primitives` section.

Test type files declare how they interact with each provider primitive:

| Marker | Meaning | Test type section contains |
|--------|---------|---------------------------|
| `**Inherits:** provider` | Use provider's primitive as-is | Brief description only — no Method, no queries |
| `**Extends:** provider` | Merge provider + test type content | Test-type-specific queries, patterns, and rules that supplement the provider |
| *(no marker)* | Override — test type defines everything | Full Method, Auth, queries, Diagnostic Knowledge — provider primitive is ignored |

**Rules:**
- Platform primitives are OPTIONAL in `provider.md` for typed providers (required for flat providers)
- All primitive sentinels (active + future/passthrough) are still REQUIRED in every test type file regardless of inheritance mode
- `Inherits` sections must NOT have `**Method:**`
- `Extends` sections must NOT have `**Method:**`
- Override sections (no marker) must have `**Method:**`

## Test Type File Header

```markdown
# test-type-name
**Schema:** 1
**Description:** Brief description.
```

- `**Schema:**` enables backward-compatible parsing when the schema evolves
- All v1 toolkits use `Schema: 1`

## Diagnostic Knowledge

The `#### Diagnose` section must include `##### Diagnostic Knowledge` with at least a **Failure Patterns** table:

| Subsection | Required | Purpose |
|-----------|----------|--------|
| **Failure Patterns** | Yes | Symptom → Root Cause → Fix |
| **Environment Checks** | No | Preconditions to verify first |
| **Cascade Rules** | No | Dependency chains — focus on root failures |

The Failure Patterns table is static, provider-authored knowledge. The AI matches telemetry against it — it never invents root causes beyond what's in this table.

## MCP Integration

Any primitive can use `**Method:** mcp`. When it does, include these fields:

| Field | Required | Description |
|-------|----------|-------------|
| `**MCP Server:**` | Yes | Name of the MCP server from `.vscode/mcp.json` |
| `**Tool:**` | Yes | MCP command name (e.g., `kusto_query`) |
| `##### Tool Discovery` | Yes | Instructions for discovering the tool at runtime |
| `##### MCP Parameters` | Yes | Default parameters table (cluster-uri, database, etc.) |

## Validation

Toolkits are validated by [validate-toolkit.ps1](scripts/validate-toolkit.ps1). Key rules:

**Flat providers (Available Test Types: none):**
- All primitive sentinels present in `provider.md`
- Each sentinel has `Method` (no inheritance in flat mode)
- Passthrough sections have `Status` + `Reason`, no execution fields
- `Diagnose` has `Diagnostic Knowledge` with a Failure Patterns table

**Typed providers (Available Test Types has entries):**
- All primitive sentinels present in every test type file
- Passthrough sections have `Status` + `Reason`, no execution fields
- Non-passthrough sections have `Method` (unless using `Inherits` or `Extends`)
- `Inherits` and `Extends` sections must NOT have `Method`
- `Diagnose` has `Diagnostic Knowledge` with a Failure Patterns table (unless `Inherits: provider`)
- Each listed test type has a matching `.md` file
- If provider declares `Platform Primitives`, sentinel format matches test type conventions
