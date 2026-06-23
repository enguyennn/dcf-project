# Repository Overview

Generate comprehensive repository documentation, architecture analysis, and a
contributor Team Playbook from your codebase and PR history. Uses a deep-research
workflow orchestrated by the `Octane.RepoAnalyst` agent.

## When to Use

- Onboarding new team members to an unfamiliar codebase
- Producing high-level project documentation (purpose, architecture, components)
- Understanding the design patterns and technology stack of a repository
- Generating a Team Playbook that teaches contributors what reviewers care about

## Prerequisites

- **Repository**: hosted on GitHub or Azure DevOps
- **MCP Servers**:
  - `code-search` — for analyzing codebase structure and searching code
  - `ado-stdio` — for Azure DevOps PR history (auto-detected from git remote)
  - `ms-learn` — for Microsoft Learn content and documentation support

  These are registered in [`artifacts/shared/mcp.json`](../../shared/mcp.json)
  for the VS Code extension (via the `mcp_servers` key in
  [`scenario.json`](./scenario.json)) and declared inline in this scenario's
  [`.mcp.json`](./.mcp.json) for the Copilot CLI plugin.
- **For GitHub repos**: `gh` CLI installed and authenticated (`gh auth login`)
- **For ADO repos**: the `ado-stdio` MCP server connected
- **Copilot CLI only**: the `code-search` and `ado-stdio` servers read their
  target organization/project/repository/branch from environment variables.
  Export these before launching `copilot` so the `.mcp.json` headers and args
  resolve:

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

## Workflows

### Generate Repository Overview

Run a deep-research analysis of the repository and produce a comprehensive
overview document (plus an embedded Team Playbook).

**Skill:** [`octane-repository-overview`](./skills/octane-repository-overview/SKILL.md)
— owns input collection, deep research, parallel sub-agent analysis, drafting,
and review against the mandatory template.

**Agent:** [`Octane.RepoAnalyst`](./agents/Octane.RepoAnalyst.agent.md) — carries the
declared model, tool allow-list, and step-compliance guarantees.

**Steps:**

1. Invoke the skill from Copilot Chat (VS Code) or the CLI (e.g.,
   `/octane-repository-overview`).
2. Optionally provide an **output path** (`OutputPath`) and whether to include
   the Team Playbook (`IncludeTeamPlaybook`).
3. `Octane.RepoAnalyst` performs deep research, delegates the Team Playbook to the
   `octane-team-playbook` skill, runs parallel sub-agent analysis, drafts the
   document, and reviews it against the mandatory template.

**Expected Output:**

A `repository_overview.md` document covering project purpose, architecture and
design patterns, key components, development setup, and technology stack — plus
`docs/team-playbook.md` when the Team Playbook is included.

#### Invocation

```shell
# You'll be asked for an optional output path and Team Playbook preference
/octane-repository-overview
```

### Generate Team Playbook Only

Mine the repository's PR review history to produce a standalone contributor
Team Playbook.

**Skill:** [`octane-team-playbook`](./skills/octane-team-playbook/SKILL.md) —
owns platform detection, PR comment fetching, categorization/scoring, and
report generation. Builds on the shared
[`pr-review-mining`](../../shared/skills/pr-review-mining/SKILL.md) skill.

**Agent:** [`Octane.RepoAnalyst`](./agents/Octane.RepoAnalyst.agent.md)

**Steps:**

1. Invoke the skill from Copilot Chat (VS Code) or the CLI (e.g.,
   `/octane-team-playbook`).
2. `Octane.RepoAnalyst` detects the platform from the git remote, fetches the last
   50 merged PRs with review threads, categorizes feedback, and writes the
   playbook.

**Expected Output:**

`docs/team-playbook.md` with top rejection patterns, quality bar by area,
tribal knowledge, and reviewer mapping.

#### Invocation

```shell
/octane-team-playbook
```

## Custom Agents

### Octane.RepoAnalyst

Senior technical lead that orchestrates repository analysis and documentation
generation. `Octane.RepoAnalyst` follows the step-by-step research and drafting
protocols defined in this scenario's skills and produces output against
standardized templates. The agent is vendored locally with this scenario (see
[`agents/Octane.RepoAnalyst.agent.md`](./agents/Octane.RepoAnalyst.agent.md)).

## Use Cases

- Onboarding new team members
- Creating project documentation
- Understanding unfamiliar codebases
- Documenting architecture and technical decisions

## Difficulty

**Beginner** — simple to use, requires minimal setup.

## Tags

`documentation` `planning` `repository` `overview` `onboarding` `team-playbook`

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version history and migration notes. The
`1.x → 2.0` entry documents the prompt → skill migration.
