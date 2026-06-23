# Anti-Pattern Fixer

**Detect code anti-patterns using the CodeQuality MCP and apply automated fixes with build verification.**

## Overview

This scenario provides a single agent that scans your codebase for anti-patterns (bad practices flagged by static analysis), retrieves automated fix instructions from the CodeQuality MCP, applies the fixes surgically, and verifies the build still passes.

It is framework-agnostic: the agent **does not hardcode** build or test commands. Instead, it discovers them from the target repo's instruction files (`.github/copilot-instructions.md`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`) and project manifests.

## When to Use

- You want to clean up anti-patterns flagged by your team's static analysis rules without manually reviewing each one.
- You have an Azure DevOps-hosted repo with CodeQuality analysis configured.
- You want automated fixes that are verified against your build before committing.

## Prerequisites

- **Azure DevOps-hosted repo.** The CodeQuality MCP keys off ADO organization/project/repository.
- **CodeQuality analysis configured.** Your repo must have anti-pattern rules configured in the CodeQuality system.
- **CodeQuality MCP server configured.** Auto-configured when this scenario is installed via Octane.
- **Repo instruction files (recommended).** The agent works best when the target repo has build/test commands documented in `.github/copilot-instructions.md`, `AGENTS.md`, or `README.md`.

## What's Included

### Agents

| Agent | Invocable | Purpose |
|-------|-----------|---------|
| **AntiPatternFixer** | ✅ Yes | Scans for anti-patterns, gets fix instructions, applies fixes, verifies build. |

### Prompt

| Prompt | Description |
|--------|-------------|
| `Octane.AntiPatternFixer.FixIssues` | Entry point from VS Code `/` menu — routes to the AntiPatternFixer agent with structured inputs. |

### MCP Server

- **`code-quality-mcp`** — Provides `search_anti_patterns` (find issues) and `fix_anti_pattern_issues` (get fix instructions).

## Workflow

```
User → @AntiPatternFixer <path/to/file> [--severity High] [--dry-run]
          │
          ├─ Step 1: Discover repo build/test commands
          │     - Read instruction files (copilot-instructions.md, AGENTS.md, README.md)
          │
          ├─ Step 2: Search anti-patterns
          │     - Call code-quality-mcp/search_anti_patterns
          │     - Filter by file, severity, rule, service
          │
          ├─ Step 3: Present issues table
          │     (stop here if --dry-run)
          │
          ├─ Step 4: Get fix instructions
          │     - Call code-quality-mcp/fix_anti_pattern_issues
          │
          ├─ Step 5: Apply fixes surgically
          │     - Follow MCP instructions exactly
          │     - Skip ambiguous fixes
          │
          ├─ Step 6: Verify build + tests
          │     - Revert any fix that breaks the build
          │
          └─ Step 7: Summary report
```

## Example Usage

**Fix all anti-patterns in a file:**
```
@AntiPatternFixer src/Services/PaymentProcessor.cs
```

**Show high-severity issues only (dry run):**
```
@AntiPatternFixer src/Services/PaymentProcessor.cs --severity High --dry-run
```

**Fix a specific rule across a service:**
```
@AntiPatternFixer --service MyService --rule AvoidEmptyCatchBlocks
```

**Scan by file name (partial match):**
```
@AntiPatternFixer --file PaymentProcessor
```

## Expected Output

After a full run, the agent produces a summary report:

```
## Anti-Pattern Fix Report

Files scanned: 3
Issues found: 8
Fixes applied: 5
Fixes skipped: 2 (manual review needed)
Fixes reverted: 1 (caused test failure)
Build status: ✅ Passing

### Applied Fixes
| # | Rule                    | File                     | Line | Status    |
|---|-------------------------|--------------------------|------|-----------|
| 1 | AvoidEmptyCatchBlocks   | PaymentProcessor.cs      | L45  | ✅ Fixed  |
| 2 | UseStringInterpolation  | PaymentProcessor.cs      | L112 | ✅ Fixed  |
| 3 | DisposePattern          | ConnectionManager.cs     | L67  | ✅ Fixed  |

### Skipped (Manual Review Needed)
| # | Rule            | File              | Line | Reason                        |
|---|-----------------|-------------------|------|-------------------------------|
| 6 | ComplexMethod   | OrderService.cs   | L200 | No automated fix available    |
| 7 | GodClass        | BaseController.cs | L1   | Requires architectural refactor |

### Remaining
Run `@AntiPatternFixer <file> --severity Low` to address lower-severity issues.
```

## Configuration Flags

| Flag | Description |
|------|-------------|
| `--severity LEVEL` | Filter by severity: `Low`, `Medium`, `High`, `Critical` |
| `--rule NAME` | Filter to a specific anti-pattern rule |
| `--file NAME` | Filter by file name (partial match) |
| `--service NAME` | Filter by service name |
| `--dry-run` | List issues without applying fixes |

## When to Use This vs. Other Scenarios

| | Anti-Pattern Fixer | Critical Code Path Analysis |
|---|---|---|
| **What it fixes** | Static analysis anti-patterns (bad practices, code smells) | Coverage gaps in critical code paths |
| **Data source** | `search_anti_patterns` + `fix_anti_pattern_issues` | `get_critical_code_paths` |
| **Output** | Refactored source code | New unit tests |
| **Goal** | Clean up code quality issues | Improve test coverage of high-risk paths |

**Use Anti-Pattern Fixer** when you want to clean up code smells and bad practices. **Use Critical Code Path Analysis** when you want to write tests for uncovered critical paths.

## Limitations

- **Azure DevOps only.** The CodeQuality MCP requires an ADO-hosted repo.
- **Requires CodeQuality analysis.** Anti-pattern rules must be configured for your repo in the CodeQuality system.
- **Not all issues have automated fixes.** Some anti-patterns require manual refactoring — the agent will flag these as "manual review needed."
- **Build verification requires discoverable commands.** If the repo has no documented build/test commands, the agent will ask the user.

## Authoring Notes

This scenario uses the CodeQuality MCP's `search_anti_patterns` and `fix_anti_pattern_issues` tools. The fix instructions are authoritative — the agent follows them exactly rather than inventing its own fix logic.
