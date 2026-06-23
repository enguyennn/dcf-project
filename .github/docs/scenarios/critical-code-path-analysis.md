# Critical Code Path Analysis

**AI-powered identification of critical code path coverage gaps, targeted test generation, and coverage verification using the CodeQuality MCP.**

## Overview

This scenario orchestrates two specialized sub-agents behind a single user-facing agent to:

1. **Identify** uncovered critical paths in a target file (via the CodeQuality MCP `get_critical_code_paths` tool — actual CI coverage data, not source heuristics).
2. **Write** a focused unit test for each gap, matching the repo's existing test framework, mock library, and style conventions.
3. **Verify** that the newly added tests cover the previously uncovered lines.

It is framework-agnostic: the agents **do not hardcode** build / test / coverage commands. Instead, they discover them from the target repo's instruction files (`.github/copilot-instructions.md`, `AGENTS.md`, `README.md`, `.github/instructions/*.md`, `CONTRIBUTING.md`) and project manifests (`*.csproj`, `package.json`, `pyproject.toml`, `pom.xml`, `Makefile`, etc.).

## When to Use

- You want to close high-value coverage gaps (catch blocks, validation, auth checks, error paths) without writing tests manually.
- You have an Azure DevOps-hosted repo with CI builds that produce coverage data.
- You want to generate tests that match the repo's **existing** conventions (framework, mocking, naming) rather than a generic template.

## Prerequisites

- **Azure DevOps-hosted repo.** The CodeQuality MCP keys off ADO organization/project/repository. GitHub-hosted repos are not supported by the MCP server.
- **CI builds producing coverage data.** The MCP reads coverage from completed CI builds; builds without coverage collection won't surface gaps.
- **CodeQuality MCP server configured.** Auto-configured when this scenario is installed via Octane (entry in `artifacts/shared/mcp.json`). The `x-mcp-codequality-organization`, `-project`, and `-repository` headers are populated from your Octane config.
- **Repo instruction files (recommended).** Agents work best when the target repo has at least one of: `.github/copilot-instructions.md`, `AGENTS.md`, or a README with explicit Build / Test sections. Without these, the agents fall back to inferring from project manifests.

## What's Included

### Agents

| Agent | Invocable | Purpose |
|-------|-----------|---------|
| **CriticalCodePathGapFiller** | Yes (entry point) | Orchestrates the full workflow: discovers repo conventions once, calls the CodeQuality MCP for gap analysis, then dispatches sub-agents. |
| CriticalCodePathTestWriter | Internal | Writes one unit test per gap, matching the repo's framework and style. |
| CriticalCodePathVerifier | Internal | Runs tests with coverage and verifies the target lines are now hit. |

**Only the orchestrator is intended for direct user invocation.** The two sub-agents are invoked by the orchestrator via `handoffs`.

### MCP Server

- **`code-quality-mcp`** — Provides `get_critical_code_paths`, `get_file_coverage`, `get_coverage_improvement_areas`, `search_anti_patterns`, `fix_anti_pattern_issues`, and related tools. Configured via `artifacts/shared/mcp.json`.

## Workflow

```
User → @CriticalCodePathGapFiller <path/to/file>
          │
          ├─ Phase 1: Discover repo (once)
          │     - Read .github/copilot-instructions.md / AGENTS.md / README.md
          │     - Detect build, test, and coverage commands
          │     - Parse git remote for ADO org/project/repo
          │     - Gather commitSha, branch, commitDate, defaultBranch
          │
          ├─ Phase 2: Analysis (orchestrator)
          │     - Calls code-quality-mcp/get_critical_code_paths
          │     - Builds structured JSON of gaps (prioritized)
          │
          ├─ Phase 3: Test Writing → CriticalCodePathTestWriter (per gap)
          │     - Matches repo's test framework, mocks, style
          │     - Builds, runs the new test, reports pass/fail/needs-review
          │
          ├─ Phase 4: Verification → CriticalCodePathVerifier
          │     - Runs tests with coverage
          │     - Parses coverage output (Cobertura, lcov, JaCoCo, etc.)
          │     - Verifies each gap: COVERED / PARTIAL / NOT COVERED
          │
          └─ Final report: test status + coverage deltas + remaining work
```

## Example Usage

**Full workflow on a single file:**
```
@CriticalCodePathGapFiller src/api/Controllers/DeploymentController.cs
```

**Analysis only (no tests written):**
```
@CriticalCodePathGapFiller src/api/Controllers/DeploymentController.cs --analyze-only
```

**Target only catch blocks, top 5 priority gaps:**
```
@CriticalCodePathGapFiller src/domain/NodeGrain.cs --filter catch-block --max-gaps 5
```

**Verify coverage of existing tests without adding new ones:**
```
@CriticalCodePathGapFiller src/api/Controllers/DeploymentController.cs --verify-only
```

## Configuration Flags

| Flag | Description |
|------|-------------|
| `--analyze-only` | Run analysis phase only; don't write tests. |
| `--verify-only` | Skip analysis and test writing; only verify existing coverage. |
| `--max-gaps N` | Only address the N highest-priority gaps. |
| `--filter TYPE` | Target a specific path type: `catch-block`, `validation`, `auth-check`, `error-response`, `logging`. |
| `--no-verify` | Skip the final verification phase. |

## How Agents Discover Build / Test / Coverage Commands

Agents read these files (in order) and stop when they have enough signal:

1. `.github/copilot-instructions.md`
2. `AGENTS.md` (repo root)
3. `CLAUDE.md` (repo root)
4. `README.md` — sections titled Build, Test, Getting Started, Development
5. `.github/instructions/*.md`
6. `CONTRIBUTING.md`
7. Project manifests: `package.json` scripts, `*.csproj`, `*.sln`, `pyproject.toml`, `pom.xml`, `Cargo.toml`, `go.mod`, `Makefile`

The orchestrator performs discovery **once** and passes the result as a context packet to each sub-agent, so sub-agents don't re-read the same files.

### What to Include in Your Repo Instructions

For best results, document in `.github/copilot-instructions.md` or `AGENTS.md`:

- The exact **build command** (e.g., `dotnet build src/Project.sln -c Debug`)
- The exact **test command** and its **coverage variant** (e.g., `dotnet test src/Tests.csproj --collect:"XPlat Code Coverage"`)
- The **test framework** (MSTest, xUnit, Jest, Pytest, …) and **mocking library** (Moq, jest.mock, unittest.mock, …)
- **Style rules** the agent must follow (e.g., "use explicit types, no `var`")
- The location where **coverage results** are produced (e.g., `TestResults/**/coverage.cobertura.xml`)

## Supported Frameworks

The agents are **framework-agnostic** and work with any ecosystem whose build/test/coverage commands are discoverable from repo files. Verified patterns include:

- **.NET** — MSBuild / `dotnet build` + MSTest / xUnit / NUnit + coverlet (Cobertura)
- **JavaScript / TypeScript** — Jest / Vitest + jest.mock / sinon (lcov / coverage-final.json)
- **Python** — Pytest + unittest.mock / pytest-mock + pytest-cov (Cobertura XML)
- **Go** — `go test` + table-driven tests (`coverage.out`)
- **Java** — Maven / Gradle + JUnit + Mockito + JaCoCo

Other ecosystems work as long as the test command, coverage output, and framework are documented in the target repo.

## Expected Output

After a full run, the orchestrator produces a summary report with:

1. **Gap Summary** — Table listing each critical code path gap found, its type (catch block, validation, auth check, etc.), priority, and the method/line range.
2. **Tests Written** — For each gap, the new test file path, test method name, and pass/fail status from the initial build+run.
3. **Coverage Deltas** — Before and after coverage percentages for the target file, with per-gap status: `COVERED`, `PARTIAL`, or `NOT COVERED`.
4. **Remaining Gaps** — Any gaps that could not be closed (with reasoning — e.g., requires integration test, external service dependency).
5. **Next Steps** — Suggested follow-up analyses (e.g., other files in the same module with low critical path coverage).

Example snippet:

```
| # | Gap Type     | Method / Lines             | Test File                        | Status   |
|---|-------------|----------------------------|----------------------------------|----------|
| 1 | catch-block | ProcessPayment:L45-52      | Tests/PaymentProcessorTests.cs   | COVERED  |
| 2 | validation  | ValidateInput:L78-85       | Tests/PaymentProcessorTests.cs   | COVERED  |
| 3 | auth-check  | AuthorizeRequest:L112-120  | —                                | SKIPPED  |

Coverage: 62% → 78% (+16%)
```

## When to Use This vs. Unit Test Generation

This scenario and [Unit Test Generation](../unit-test-generation/README.md) both produce unit tests, but target different needs:

| | Critical Code Path Analysis | Unit Test Generation |
|---|---|---|
| **Data source** | CodeQuality MCP — real CI coverage data from Azure DevOps builds | Unit Test MCP — local analysis |
| **Scope** | Only critical paths (catch blocks, validation, auth, error handling) | General-purpose coverage for any code |
| **Hosting** | Azure DevOps repos only | Any repo |
| **Goal** | Close the highest-risk gaps first | Broad coverage improvement |

**Use Critical Code Path Analysis** when you want to target the most impactful coverage gaps in an ADO-hosted repo using actual CI data. **Use Unit Test Generation** for general-purpose test creation in any repo.

## Limitations

- **Azure DevOps only.** The CodeQuality MCP server requires an ADO-hosted repo.
- **Requires CI coverage data.** Gaps are sourced from MCP-provided CI coverage, not local runs. A repo with no CI coverage pipeline will return no gaps.
- **One test per invocation of CriticalCodePathTestWriter.** The orchestrator calls CriticalCodePathTestWriter once per gap; batching is deliberate to minimize conflicts.
- **The orchestrator is the entry point.** Directly invoking sub-agents (`CriticalCodePathTestWriter`, `CriticalCodePathVerifier`) is not supported -- they expect a context packet from the orchestrator.

## Authoring Notes

This scenario was adapted from the critical-code-path agents in the OneDeploy-OMv2 repo and generalized to work with any Azure DevOps repo. Hardcoded `.NET 8.0 + MSTest + coverlet` commands, specific project paths, and repo-specific namespaces were replaced with a **discovery-first** approach (repo instruction files → project manifests) so a single scenario works across the full Azure-Core portfolio.
