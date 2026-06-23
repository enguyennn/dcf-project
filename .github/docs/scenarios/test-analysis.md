# Test Analysis Scenario

Intelligent test analysis and selective test execution. The `Tester`
agent analyzes test runs for coverage, reliability, and best practices, and
runs the unit tests impacted by a given scope.

## When to Use

- Analyzing test coverage, reliability, and quality for a file, area, or commit
- Identifying test gaps and getting prioritized, actionable recommendations
- Running only the unit tests impacted by a change before you commit
- Monitoring test-suite health and triaging flaky tests

## Prerequisites

- **MCP Server**: `code-search` (registered as `code-search` in
  [`artifacts/shared/mcp.json`](../../shared/mcp.json) for the VS Code
  extension; declared inline in this scenario's [`.mcp.json`](./.mcp.json) for
  the Copilot CLI plugin)
- Azure DevOps repository configured
- **Copilot CLI only**: the `code-search` server reads its target repository
  from environment variables. Export these before launching `copilot` so the
  `.mcp.json` headers resolve:

  ```bash
  export ADO_ORGANIZATION=<your-ado-org>
  export ADO_PROJECT=<your-ado-project>
  export ADO_REPOSITORY=<your-repo>
  export ADO_BRANCH=<your-branch>
  ```

  ```powershell
  $env:ADO_ORGANIZATION = "<your-ado-org>"
  $env:ADO_PROJECT = "<your-ado-project>"
  $env:ADO_REPOSITORY = "<your-repo>"
  $env:ADO_BRANCH = "<your-branch>"
  ```

  (In the VS Code extension these are prompted interactively, so no exports are
  needed.)
- A test suite configured in your project
- Understanding of testing frameworks and practices

## Workflows

### Analyze Test Quality

Analyze a scope of code, locate the tests that cover it, and score those tests
against the configured assessments (coverage, reliability, best practices),
ending in a structured Test Analysis report.

**Skill:** [`octane-tester-test-analysis`](./skills/octane-tester-test-analysis/SKILL.md) — owns the assessment workflow and the Test Analysis report template.
**Agent:** [`Tester`](./agents/Octane.Tester.agent.md) — carries the model, the `code-search/*` tool allow-list, and the step-compliance contract.

**Steps:**

1. Review the `Scope` and identify the code under test.
2. Use `code-search/*` to map code paths and locate existing tests.
3. Branch on whether tests exist (propose a test plan, or map scenarios to code paths).
4. Score each assessment and compile findings.
5. Offer to implement recommended changes and re-run tests to confirm they pass.

#### Invocation

```shell
/octane-tester-test-analysis
/octane-tester-test-analysis UserRepositoryTests.cs
/octane-tester-test-analysis UserRepository.cs
/octane-tester-test-analysis 59cb39f
```

### Run Impacted Tests

Identify and selectively run the unit tests impacted by a scope, then report the
results in a structured Test Execution Results table.

**Skill:** [`octane-tester-test-run`](./skills/octane-tester-test-run/SKILL.md) — owns the impacted-test selection and the Test Execution Results template.
**Agent:** [`Tester`](./agents/Octane.Tester.agent.md) — carries the model, the `code-search/*` tool allow-list, and the step-compliance contract.

**Steps:**

1. Review the `Scope` and identify the code under test.
2. Use `code-search/*` to map code paths and locate impacted tests.
3. Run the impacted tests per `${config:test-analysis.testing_instructions}`.
4. Document results and offer to fix any failures.

#### Invocation

```shell
/octane-tester-test-run UserRepository.cs
/octane-tester-test-run 59cb39f
```

## Expected Output

- **Analyze Test Quality** produces a Markdown **Test Analysis** report: an
  overview of the system under test and strategy, a per-assessment scoring table
  (1–10), detailed strengths/weaknesses/recommendations per assessment, and a
  prioritized list of recommended actions.
- **Run Impacted Tests** produces a Markdown **Test Execution Results** report:
  the execution context, a per-test results table (class, method, result,
  comments), and a prioritized list of recommended follow-up actions.

## Configuration

Out of the box, the analysis evaluates tests for reliability, coverage, and best
practices. Teams can customize the assessments and test-execution instructions
in this scenario's [`config/octane.yaml`](./config/octane.yaml). All settings are
namespaced under the scenario `id` (`test-analysis`):

| Setting | Description | Default |
|---------|-------------|---------|
| `test-analysis.analysis.assessments` | Assessment criteria used by **Analyze Test Quality**, referenced via `${config:test-analysis.analysis.assessments}`. | `test_coverage`, `reliability`, `best_practices` |
| `test-analysis.testing_instructions` | Per-language commands used by **Run Impacted Tests**, referenced via `${config:test-analysis.testing_instructions}`. | `dotnet`: run unit/integration tests with built-in tooling |

> When installed at the user level, `config/octane.yaml` is not deployed; the
> skills fall back to the defaults above.

## Custom Agents

### Tester

A Senior Quality Assurance Engineer specializing in automated testing and
quality validation. Analyzes test results, validates implementations against
requirements, and generates actionable quality reports. See
[`agents/Octane.Tester.agent.md`](./agents/Octane.Tester.agent.md).

## Tips and Best Practices

- Provide the most specific `Scope` you can (a file or commit) for tighter,
  faster analysis.
- Use **Run Impacted Tests** before committing to validate only what changed;
  use **Analyze Test Quality** to drive longer-term coverage improvements.
- Customize `config/octane.yaml` to focus the assessments on your team's
  priorities.

## Difficulty

**Intermediate** — Requires understanding of testing frameworks and test
analysis.

## Tags

`testing` `quality` `analysis` `test-results`

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version history and migration notes.
