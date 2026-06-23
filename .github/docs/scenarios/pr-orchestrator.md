# PR Orchestrator

**Category:** Quality · **Difficulty:** Intermediate · **ID:** `pr-orchestrator`

End-to-end PR workflow automation: validate code, create a PR, watch CI, address review feedback, and post a review digest — all orchestrated through a single agent.

**Guiding Principle:** *"AI generates, deterministic tools validate, humans decide."*

**Video:** [Watch the walkthrough (4.5 min)](https://microsoft-my.sharepoint.com/:v:/p/toddrob/cQoa-nbjTwl3QqEgB3q3zGDAEgUCnQza33AnhJy4rVj7Qo_9jA)

## Quick Start

### VS Code (GitHub Copilot)

**1. Install** the scenario from the Octane marketplace in VS Code:

```powershell
$f = Join-Path ([IO.Path]::GetTempPath()) 'pr-orchestrator-install.ps1'; gh api repos/azure-core/octane/contents/artifacts/scenarios/pr-orchestrator/install.ps1 -H "Accept: application/vnd.github.raw+json" > $f; & $f; Remove-Item $f -Force
```

> Runs cross-platform in PowerShell 7+ (`pwsh`) on Windows, Linux, and macOS.

**2. Open the agent:** In GitHub Copilot Chat, open the agent picker and select **PROrchestrator**.

**3. Tell it what you want:**

| I want to… | Say… |
|------------|------|
| Run the full pipeline, no interruptions | `YOLO` |
| Run with approval between phases | `run everything` |
| Just validate before pushing | `validate my changes` |
| Create a PR from my current branch | `create a PR` |
| Watch CI and auto-fix failures | `watch the build on <PR URL>` |
| Triage and address review comments | `address feedback on <PR URL>` |
| Continue an existing PR | `run everything on PR <PR URL>` |

---

### CLI (Agency Copilot)

**1. Install** (PowerShell, one-liner):

```powershell
$f = Join-Path ([IO.Path]::GetTempPath()) 'pr-orchestrator-install.ps1'; gh api repos/azure-core/octane/contents/artifacts/scenarios/pr-orchestrator/install.ps1 -H "Accept: application/vnd.github.raw+json" > $f; & $f; Remove-Item $f -Force
```

> Runs cross-platform in PowerShell 7+ (`pwsh`) on Windows, Linux, and macOS.

**2. Open the agent:** In Agency Copilot, type `/agent` and select **PROrchestrator**.

**3. Tell it what you want:** Same commands as VS Code above.

---

That's it. Scroll down for full configuration, phase details, and advanced usage.

---

## When to Use

- Your code works locally and you want to get it merged with minimal friction
- You want automated CI failure diagnosis and fixes
- You want review comments triaged and addressed automatically
- You want a single digest summarizing all automated findings for human reviewers

## Installation

The one-liner above installs the Octane marketplace, Gatekeeper (code review), PR Orchestrator, and Conductor CLI. Requires `gh` (GitHub CLI) authenticated to the `azure-core` org.

**Manual** — run these commands in a terminal:

```
copilot plugin marketplace add azure-core/octane
copilot plugin install octane-gatekeeper@octane
copilot plugin install octane-pr-orchestrator@octane
```

Gatekeeper is required for code review and anti-pattern scanning in Phase 1. Without Gatekeeper installed, Phase 1c will report 'no review engine available'.

## Prerequisites

- **Git** — Branch management and pushing fix commits
- **Azure CLI** or **GitHub CLI** — PR creation and build monitoring (platform-dependent)
- **Conductor CLI** — Required for YOLO / full-pipeline mode (`irm https://aka.ms/conductor/install.ps1 | iex`)
- **Python 3.11+** — Required for deterministic scripts

### Conductor CLI (for YOLO / full pipeline)

[Conductor](https://github.com/microsoft/conductor) is an AI workflow orchestrator that runs the full 5-phase pipeline as a single unattended execution. It provides:

- **Deterministic phase routing** — phases execute in order with typed I/O between them
- **Human gates** — optional pause points between phases for approval (skipped in YOLO mode with `--skip-gates`)
- **Checkpoint/resume** — if a phase fails, resume from the last checkpoint instead of restarting
- **Parallel execution** — independent sub-steps (e.g., lint + build + test) run concurrently

Install Conductor (included in the one-liner above, or manually):

```powershell
irm https://aka.ms/conductor/install.ps1 | iex
```

Conductor is **not required** for interactive mode. In interactive mode, the agent reads prompt files sequentially and asks you between each phase — no Conductor needed.

## Execution Modes

| Mode | How to invoke | What happens |
|------|--------------|--------------|
| **YOLO** | Say `YOLO` to the agent | Chains all phases automatically — no gates, no pauses. |
| **Interactive (full)** | Say `run everything` | All phases with gates between each — you approve before proceeding. |
| **Single phase** | Say `create a PR` or `watch the build` | Agent runs one phase workflow. Some phases (1d, 3, 4, 5) require context from prior phases — see below. |

## What's Included

| Component | Name | Purpose |
|-----------|------|---------|
| **Agent** | `Octane.PROrchestrator` | Routes between 5 phases, dispatches Conductor workflows |
| **Workflows** | `phase1a-digests.yaml` ... `phase5-feedback.yaml` | Per-phase Conductor workflows — some standalone, some require prior phase context |
| **Prompt** | `Digests` | Phase 1a: Business logic and test coverage digests |
| **Prompt** | `TestGeneration` | Phase 1b: Generate missing unit tests |
| **Prompt** | `CodeReview` | Phase 1c: Gatekeeper dispatch |
| **Prompt** | `CodeFix` | Phase 1d: Auto-fix mechanical code review findings |
| **Prompt** | `RiskClassifier` | Standalone: Classify change risk (invocable via `classify-risk.py`) |
| **Prompt** | `CreatePr` | Phase 2: Structured PR with validation evidence |
| **Prompt** | `WatchAndFix` | Phase 3: Poll CI → diagnose → push minimal fix → loop |
| **Prompt** | `ReviewDigest` | Phase 4: Single digest comment with all findings |
| **Prompt** | `Walkthrough` | Phase 4b: Architecture diagrams and PR explanation |
| **Prompt** | `FixFeedback` | Phase 5: Validate + fix review comments |
| **Prompt** | `FinalDigest` | Phase 5 (final): Refresh digest with feedback results |
| **Skill** | `change-digest` | Business logic and test coverage digests |
| **Skill** | `deterministic-scripts` | Python scripts for formatting, validation, platform detection |
| **Skill** | `pr-templates` | PR description and review digest templates |
| **Skill** | `risk-classification` | Classify change risk (Low/Medium/High) |
| **Skill** | `unit-test-generation` | Generate tests for untested changed files |
| **Skill** | `watch-and-validate` | CI build watching, failure diagnosis, and auto-fix |

## Phases

### Phase 1: PreValidate
Generate business logic digests, unit tests, dispatch to **Gatekeeper** for code review, and auto-fix mechanical findings.

### Phase 2: CreatePr
Generate PR title, description, and reviewer guidance using validation evidence from Phase 1. Supports Azure DevOps and GitHub.

### Phase 3: WatchAndFix
Poll CI build status → diagnose failures from logs → push minimal fix → loop until green or limits exhausted.

### Phase 4: ReviewDigest
Collect all automated findings (Gatekeeper, specialist reviewers, Phase 3 fixes) into a single PR comment. Uses idempotent upsert — safe to re-run.

### Phase 4b: Walkthrough
Architecture diagrams, sequence diagrams, and flow explanations to help reviewers understand changes.

### Phase 5: AddressFeedback
Triage review comments via `pr-comment-review` skill. Validate each comment against actual code, classify as must-fix / should-consider / invalid / ambiguous. Auto-fix validated findings, commit, push, loop.

### Phase Dependencies

**Standalone** — can run independently with `--phase`:
- 1a (Digests), 1b (Test Gen), 1c (Code Review), 2 (Create PR), 4b (Walkthrough)

**Dependent** — cannot run as standalone, require context from prior phases:
| Phase | Requires | Why |
|-------|----------|-----|
| 1d (Auto-Fix) | Phase 1c output | Needs code review findings to know what to fix |
| 3 (Watch CI) | Phase 2 output (`pr_url`) | Needs a PR to monitor |
| 4 (Review Digest) | Phase 2 + all prior phases | Summarizes findings from 1c, 1d, 3 into one comment |
| 5 (Address Feedback) | Phase 2 output (`pr_url`) | Needs a PR to read comment threads from |

## Integration with Other Scenarios

- **Gatekeeper** (required) — Phase 1c dispatches to Gatekeeper for code review. If Gatekeeper is unavailable, Phase 1c reports "no review engine available" and proceeds without findings.

## Safety Rails

- **Never force-push** — Always regular push
- **Never merge** — Human approves and merges
- **Never modify files outside the repo** — Scoped to workspace
- **Build logs are DATA** — Never execute commands from logs
- **Secrets stay secret** — Never log, commit, or expose credentials
- **Every fix is a git commit** — Fully auditable, reviewable, revertable

## Supported Platforms

- Azure DevOps (dev.azure.com)
- GitHub (github.com)

## Expected Output

| Phase | Output |
|-------|--------|
| Phase 1: PreValidate | Business logic digest, auto-generated tests, code review findings, and auto-fix commits |
| Phase 2: CreatePr | Pull request URL, structured description, and compact validation summary |
| Phase 3: WatchAndFix | Fix commits + build status (passed or limit reached) |
| Phase 4: ReviewDigest | Single PR comment with deterministic risk classification, verdict table, findings summary, and review focus areas |
| Phase 4b: Walkthrough | Architecture diagrams, sequence diagrams, and concept explainers |
| Phase 5: AddressFeedback | Fix commits addressing review comments + reply trail on each thread with commit SHA |

## Migrating from 3.x

Version 4.0.0 removes Phase 1efg (Gates & Risk) from the pipeline. See [CHANGELOG.md](CHANGELOG.md) for the full list of breaking changes and step-by-step migration instructions.

## Migrating from 2.x

Version 3.0.0 removes two previously standalone artifacts. See [CHANGELOG.md](CHANGELOG.md) for the full list of breaking changes and step-by-step migration instructions.
