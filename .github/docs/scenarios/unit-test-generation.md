# Unit Test Generation

**AI-powered unit test generation, execution, and coverage improvement across multiple frameworks.**

## Overview

This scenario integrates the [Unit Test MCP](https://github.com/gim-home/UnitTestMCP) server to provide intelligent, automated unit test workflows directly inside GitHub Copilot. It supports four major testing ecosystems:

| Framework | Language | Scope |
|-----------|----------|-------|
| **Jest** | JavaScript / TypeScript / React | Unit & integration tests |
| **Vitest** | JavaScript / TypeScript / Vue | Unit & integration tests |
| **Pytest** | Python | Unit tests |
| **.NET** (xUnit / NUnit / MSTest) | C# | Unit tests |

Unlike test *analysis* or *flaky test fixing* scenarios, this scenario **generates new tests** — filling the gap in the testing lifecycle.

## When to Use

- You need to create unit tests for a source file that has no tests
- You want to improve coverage on an existing test file
- You need batch test generation across an entire folder or project
- You want automated coverage gap analysis and targeted test creation
- You need consistent, high-quality tests following framework best practices

## Prerequisites

### Required

- **Unit Test MCP Server** — The `unittest-mcp` MCP server must be configured. It is auto-configured when you install this scenario via Octane. The server runs via `npx unittest-mcp` (requires Node.js 18+).

  Or install the [Unit Test MCP VS Code Extension](https://marketplace.visualstudio.com/items?itemName=KennethHuang.unittest-mcp) for zero-setup integration.

### Activation modes

- **VS Code / Octane extension users** — The instruction file at `instructions/Octane.UnitTestMcp.instructions.md` fires automatically when a JS/TS source or test file is in context. It's written as **guidance** (not a hard gate), so the agent still follows the user's lead when their repo has different conventions.
- **Copilot CLI plugin consumers** — The instruction file is not distributed via the plugin path. To use the MCP tools from the CLI, explicitly invoke the agent: `@UnitTestEngineer generate tests for src/foo.ts`.

#### Scope of `applyTo` and framework confidence

The instruction's `applyTo` is scoped to JS/TS files only (`**/*.{ts,tsx,js,jsx,mjs,cjs}`). **Jest** is the primary path the authors are confident in today; **Vitest** should work in most cases. Pytest and .NET are supported by the MCP tools but are best-effort — the instructions do not fire automatically on `.py` or `.cs` files. Users working in those stacks can still invoke the `UnitTestEngineer` agent explicitly.

#### Documented exception to [`instructions.md §3.2`](../../../docs/guidelines/instructions.md#32-applyto-must-prevent-collisions)

§3.2 flags `**/*.ts` as too broad. The scope used here — `**/*.{ts,tsx,js,jsx,mjs,cjs}` — is in the same spirit. We are deliberately keeping it as an exception rather than narrowing further. Rationale:

- **Primary activation point is the source file, not the test file.** A test-generation request typically opens with *"write tests for `src/foo.ts`"* — the test file doesn't exist yet, so narrower globs like `**/*.{test,spec}.{ts,js}` or `**/{__tests__,tests}/**` miss the entry point.
- **The instruction is framed as guidance, not a gate.** The file explicitly says *"This file is guidance, not a hard gate. Follow the user's lead."* It does not prescribe style rules that would conflict with another scenario's opinions on the same source file; it only describes when to prefer the `unittest-mcp` MCP tools over a manual flow. Two additive instructions on the same TS file (e.g., this one + a future TS-style scenario) are merged by Copilot, not treated as conflicts.
- **Tone and language are softened.** MUST / NEVER / CRITICAL language has been removed. The file uses "prefer", "reasonable", and "suggest" throughout, so if another scenario's instruction fires on the same file, neither wins by force.

**Compensating controls:**

1. **Collision survey** — maintained below; refreshed whenever this file is materially changed.
2. **Narrowed from the initial proposal** — we dropped `.py` and `.cs` from `applyTo` (they remain supported via explicit `@UnitTestEngineer` invocation) to reduce surface.
3. **Scenario owners monitor eval output** — if another scenario files an `applyTo` that overlaps, owners commit to re-scoping to a test-file-only glob within one minor version bump.

**Collision survey (April 2026):** no other Octane scenario declares an `applyTo` that overlaps with JS/TS source files. Existing scenario instructions scope to markdown (`*.req.md`, `*.prd.md`, `*.doc.md`), agent cards (`*.agent-card.json`), scenario-specific paths (`artifacts/scenarios/eng-docs/**`), or toolkit templates. If a future scenario targets the same file types, this exception must be re-evaluated and the scope tightened.

### Framework-Specific

- **Jest/Vitest**: Node.js 18+, project with `package.json` containing test configuration
- **Pytest**: Python 3.8+, `pytest` installed, project with `pyproject.toml` or `pytest.ini`
- **.NET**: .NET SDK 6+, project with `.csproj` or `.sln`

## What's Included

### Agent

- **UnitTestEngineer** — Senior Test Engineer specializing in automated test generation, coverage analysis, and test quality. Uses the `unittest-mcp` MCP tools to generate, run, and improve tests.

### Prompts

| Prompt | Purpose |
|--------|---------|
| `Octane.UnitTestEngineer.Generate` | Generate tests for a single source file |
| `Octane.UnitTestEngineer.Batch` | Generate tests for all untested files in a folder |
| `Octane.UnitTestEngineer.Coverage` | Analyze coverage and generate tests to fill gaps |

### Skills

- **unit-test-generation** — Powers the UnitTestEngineer agent with framework detection and quality standards. Framework-specific best practices are provided automatically by the `generate_test` MCP tool.

### MCP Tools

The `unittest-mcp` server provides five tools:

| Tool | Description |
|------|-------------|
| `run_tests` | Execute tests with optional coverage collection |
| `generate_test` | Get framework-aware guidance for test creation |
| `generate_tests_batch` | Scan a folder and identify files needing tests |
| `find_test_files` | Discover existing test files in a directory |
| `inspect_coverage` | Read coverage artifacts and identify uncovered lines |

## Workflows

### 1. Generate Tests for a Single File

Generate comprehensive unit tests for any source file.

**Steps:**
1. Open GitHub Copilot Chat
2. Run: `@Octane.UnitTestEngineer.Generate`
3. Provide the source file path when prompted
4. The agent will:
   - Auto-detect the testing framework
   - Call `generate_test` for framework-aware guidance
   - Read the source to understand logic and edge cases
   - Create a test file following repo conventions
   - Run tests and iterate on coverage until target is met

**Example:**
```
@Octane.UnitTestEngineer.Generate src/services/UserService.ts
```

### 2. Batch Test Generation

Generate tests for all untested files in a directory.

**Steps:**
1. Run: `@Octane.UnitTestEngineer.Batch`
2. Provide the folder path
3. The agent will:
   - Scan the folder for source files without tests
   - Process each file one at a time (generate → write → validate → next)
   - Ensure all generated tests pass before moving on

**Example:**
```
@Octane.UnitTestEngineer.Batch src/utils/
```

### 3. Coverage Improvement

Analyze existing coverage and generate targeted tests for uncovered paths.

**Steps:**
1. Run: `@Octane.UnitTestEngineer.Coverage`
2. Provide the source file or folder
3. The agent will:
   - Run tests with coverage collection
   - Identify uncovered lines and branches
   - Generate targeted tests for error handling, edge cases, and conditional branches
   - Iterate until coverage target is met (up to 5 rounds)

**Example:**
```
@Octane.UnitTestEngineer.Coverage src/components/DataGrid.tsx
```

## Example Prompts

```
@Octane.UnitTestEngineer.Generate src/services/UserService.ts
```

```
@Octane.UnitTestEngineer.Batch src/utils/
```

```
@Octane.UnitTestEngineer.Coverage src/components/DataGrid.tsx
```

## Customization

### Framework Instruction Overrides

Override the built-in framework guides with your team's standards by providing custom instruction files. See the [Unit Test MCP Custom Instructions Guide](https://github.com/gim-home/UnitTestMCP/blob/main/CUSTOM_INSTRUCTIONS.md) for details.

### Repo-Level Instructions

Add glob-matched instruction files at `.github/instructions/` with framework-specific frontmatter:

```markdown
---
applyTo: "src/api/**"
framework: jest
priority: 50
---

- Always mock HTTP clients with `nock`
- Use factory functions for test data
- Minimum 90% branch coverage for API routes
```

## Configuration

The scenario supports the following settings via `config/octane.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `coverage-target` | `80` | Coverage percentage target (0–100). Tests iterate until this is met. |
| `max-coverage-iterations` | `5` | Maximum coverage improvement rounds before stopping. |
| `coverage-timeout-ms` | `600000` | Timeout in milliseconds for test runs with coverage. |
| `ai-attribution` | `true` | Include `Generated by AI (UnitTest MCP)` comment on generated test files. |

Override in your workspace's `.config/octane.yaml`:

```yaml
unit-test-generation:
  coverage-target: 90
  max-coverage-iterations: 3
```

## Expected Output

After running any workflow, the agent produces:

1. **Test files** — Complete, compilable test files with `Generated by AI (UnitTest MCP)` attribution, following repo conventions
2. **Test execution results** — All generated tests pass before reporting done
3. **Coverage summary** — Line and branch coverage percentages for the target scope
4. **Gap analysis** — Any remaining uncovered paths with explanations (unreachable code, platform-specific, etc.)

## Related Scenarios

- [Test Analysis](../test-analysis/README.md) — Analyze test quality and identify gaps
- [Coverage-Only Test Analysis](../coverage-only-test-analysis/README.md) — Find tests that only inflate coverage metrics
- [Flaky Test Fix](../flaky-test-fix/README.md) — Diagnose and fix flaky tests
- [MSTest v4](../mstest-v4/README.md) — MSTest v4 best practices and migration

## Difficulty

**Beginner** — Zero-setup with auto-detection of frameworks and conventions

## Tags

`testing` `coverage` `jest` `vitest` `pytest` `dotnet` `test-generation`
