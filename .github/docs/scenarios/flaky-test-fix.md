# Flaky Test Fix Scenario

## Overview

The Flaky Test Fix scenario provides a comprehensive workflow for fixing flaky tests. It uses the FlakyTestContextAnalyzer agent to collect contextual information about the test, uses the FlakyTestFixer agent to propose a fix for the targeted flaky test, and uses the FlakyTestSubmitFixPR agent to create a PR for the fix.

## What's Included

### Agents
- **FlakyTestContextAnalyzer** - Collects contextual information about the test
- **FlakyTestFixer** - Proposes a fix for the test
- **FlakyTestSubmitFixPR** - Creates a PR for the fix (ADO repositories only)
- **FlakyTestFullFix** - Runs an end-to-end process to analyze, propose a fix, and optionally create a PR
- **PRComplianceChecker** - Read-only reviewer that checks whether an Azure DevOps PR's title and description comply with the pr-description template and that the PR changes only test code; returns a true/false decision with reasons and records the result to Kusto

### Prompts
- **Octane.FlakyTestContextAnalyzer.analyze** - Generates a **Test Code Analysis** report providing a comprehensive analysis of the specified test code, including its context, intent, and behavior within the codebase.
- **Octane.FlakyTestFixer.fix** - Produces a minimal, deterministic fix for the given flaky test with high confidence that the fix resolves the flakiness without introducing new issues or changing test intent.
- **Octane.FlakyTestSubmitFixPR.submit** - Generates a Pull Request for the fix and creates PR title and description using the pr-description skill.
- **Octane.FlakyTestFullFix.Fix** - Orchestrates and triggers all three agents (FlakyTestContextAnalyzer,FlakyTestFixer,FlakyTestSubmitFixPR) to perform an end-to-end fix.

### Skills
- **analysis-report** - Structured report template for flaky test analysis results
- **pr-description** - Standardized PR title and description template for flaky test fixes
- **build-and-test** - Build and test execution for validating code changes (with generic .NET fallback for non-routed repos)
- **detect-default-branch** - Determine the repository's default branch
- **save-branch-and-push** - Create branch with correct naming and push
- **stress-test** - Stress test execution for validating test stability (cloud or local)
- **kusto-ingest-row** - Ingests a single row into a Kusto dev-database table (used by PRComplianceChecker to record evaluation results)

### MCP Servers (Optional)
The following MCP servers enhance the workflow but are **not required**. When unavailable, agents fall back to local workspace tools.

- **code-search** - For analyzing codebase structure and searching code. Falls back to workspace search.
- **Deflaker** - Utilities used by FlakyTestFixer and FlakyTestSubmitFixPR agents. Falls back to local tools.
- **azure-devops** - Used to interact with ADO and create pull requests.

## Prerequisites

- A Git repository with a flaky test to fix
- MCP servers configured as needed (see shared `mcp.json` for setup)

## Example Workflows

### Collect contextual information about a flaky test

1. Open GitHub Copilot Chat
2. Type: `@Octane.FlakyTestContextAnalyzer.analyze "test name"`
3. The FlakyTestContextAnalyzer agent will analyze your repository and generate:
   - Test Code Analysis report

### Propose a fix for the flaky test

1. Open GitHub Copilot Chat
2. Type: `@Octane.FlakyTestFixer.fix` (with the test context from the previous step). Optionally add a bug report URL (ADO work item or GitHub issue).
3. The FlakyTestFixer agent will:
   - Analyze the flaky test and its context
   - Identify the root cause of flakiness
   - Propose a minimal, deterministic fix

### Submit a PR for the fix

1. Open GitHub Copilot Chat
2. Type: `@Octane.FlakyTestSubmitFixPR.submit` (with the proposed fix from the previous step)
3. The FlakyTestSubmitFixPR agent will:
   - Create a branch with the fix
   - Generate a PR title and description using the pr-description skill
   - Submit the pull request

### Trigger an end-to-end process to fix a given flaky test.

1. Open GitHub Copilot Chat
2. Type: `@Octane.FlakyTestFullFix.Fix` "test name" (optionally add "bug report url")
3. The FlakyTestFullFix agent will trigger a multi-step process:
   - Collect contextual information about a flaky test (FlakyTestContextAnalyzer agent)
   - Propose a fix for the flaky test (FlakyTestFixer agent)
   - For ADO repos: submit a PR for the fix (FlakyTestSubmitFixPR agent)
   - For GitHub repos: provide a developer-friendly change summary with root cause, diffs, and validation results

### Check whether a PR complies with the fix template

1. Open GitHub Copilot Chat
2. Type: `@PRComplianceChecker` and provide an Azure DevOps PR URL (e.g. `https://msazure.visualstudio.com/One/_git/Azure-Compute/pullrequest/1234567`)
3. The PRComplianceChecker agent will:
   - Read the pr-description template and fetch the PR's title, description, and changed files
   - Verify the title/description match the template and that only test code changed
   - Return a `true`/`false` decision with specific reasons when non-compliant
   - Record the evaluation result to the `AgentPREvaluation` Kusto table (via the kusto-ingest-row skill)

## Use Cases

- Fixing flaky tests to improve CI/CD reliability
- Analyzing test code to understand flakiness patterns
- Automating the PR creation process for test fixes
- Improving overall test suite stability

## Difficulty

**Intermediate** - Requires understanding of testing frameworks and test analysis

## Tags

`testing` `flaky test` `test health` `test reliability`
