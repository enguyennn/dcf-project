---
agent: TestHardening
description: Folder-mode test hardening — discover all test files under a folder, fan out audits in parallel, apply edits sequentially, and open a single PR. Test code only; production code is never modified.
model: Claude Opus 4.6 (copilot)
tools: [vscode, read, edit, search, execute/runInTerminal, execute/getTerminalOutput, agent, todo, 'code-search/*', 'deflaker/*', ado-stdio/repo_create_pull_request, ado-stdio/wit_get_work_item, ado-stdio/repo_get_repo_by_name_or_id, ado-stdio/wit_link_work_item_to_pull_request]
---

## Inputs

- `test path` (string, required): a folder path **or** a single test-file path. Folder mode fans out audits across every test file under the folder; a single-file path is short-circuited to `Octane.TestHardening.End2End`.
- `category filter` (string, optional): comma-separated subset of hardening categories to apply (e.g., `assertion-strength,stability-by-design`). Forwarded to every per-file Improve invocation.
- `stability evidence URL` (string, optional): an ADO work item or issue URL containing observed intermittent failures. Forwarded to every per-file Audit invocation.
- `max files` (integer, optional, default 30, hard ceiling 100): fan-out cap. Folders above the soft cap require an explicit raise; folders above the ceiling are refused outright.

If you do not have a `test path`, stop and request it. Do not provide an example request.

## Goal

Process every test file under a folder in one invocation: a **parallel** audit (one sub-agent per file), a **sequential** improve (file-by-file, with build at the end), and a **single** PR covering the whole folder.

The single-file flow (`Octane.TestHardening.End2End`, `Octane.TestHardening.Audit`, `Octane.TestHardening.Improve`, `Octane.TestHardening.Submit`) is unchanged; this prompt composes those prompts without modifying them.

## Hybrid Execution Model

| Phase | Mode | Reason |
|-------|------|--------|
| Discovery & Classify | Single agent | The classification result determines whether to fan out at all. |
| Audit | **Parallel** (fan-out via `agent` tool) | Audits are read-only and independent per file; fan-out cuts wall-clock time. |
| Improve | **Hybrid**: parallel across **different test projects** (one sub-agent per project), sequential within a project | Build artifacts are project-scoped; different projects can be edited concurrently. Within a project, fixtures and build outputs are shared — sequential preserves assertion-preservation cross-checks and the monotonic skip-set. |
| Build | **One per project** (one build inside each project sub-agent) | Already amortized at the project level; cross-project builds run concurrently. |
| Stress | **Parallel across different test classes** (one sub-agent per class) | Different test classes use different fixtures; per-class pass-rate stays statistically valid. Methods inside one class stay serial. |
| Submit | Single | One branch, one PR, one merge for the whole folder. |

## Workflow

### Todo List Template

Create your todo list from the template below. Do not add, rename, or reorder items.

```
Todo 1:  Create todo list strictly from this template.
Todo 1b: Pre-flight `git status --porcelain`. If non-empty, stop and request stash/commit.
Todo 2:  Discover & classify `test path` via `../skills/test-file-discovery/SKILL.md`. Dispatch on the `Classification:` line per the routing table below.
Todo 3:  Parallel Audit fan-out: spawn one sub-agent per discovered test file, each calling `Octane.TestHardening.Audit.prompt.md` with the file path. Collect every sub-agent's `RunSummary v1 | Phase: Audit` block.
Todo 4:  Reduce the N audit blocks into a folder-level `RunSummary v1 | Phase: FolderAudit` block. If every file's findings is zero, emit the Standalone Stop-Gate and stop.
Todo 5:  Group worklist by **owning test project** (`.csproj` / `pyproject.toml` / `package.json` boundary). For each project, spawn one Improve sub-agent; sub-agents run in parallel. Within a project sub-agent: iterate files in audit order, applying findings per the protocol in `Octane.TestHardening.Improve.prompt.md`. Each sub-agent builds **once** at the end of its project and classifies via `../skills/build-outcome-classification/SKILL.md`. Collect per-file `applied`/`skipped` rows from every sub-agent.
Todo 6:  Reduce per-project build outcomes into a single folder-level classification (`LOCAL_BUILD_BLOCKED` > `LOCAL_BUILD_FAILED_BY_EDIT` > `LOCAL_BUILD_OK`). If any project failed to build, the folder-level outcome reflects that worst case.
Todo 7:  Group files with applied `stability-by-design` findings by **owning test class**. Spawn one stress sub-agent per class; sub-agents run in parallel per `../skills/stress-validation-protocol/SKILL.md`. Methods within a class stay serial inside their sub-agent. Partial-revert per class on regression.
Todo 8:  Pre-Submit invariant: `git diff --stat` must show test files only. Any production file in the diff → stop and report.
Todo 9:  Single Submit: call `Octane.TestHardening.Submit.prompt.md` with `$phaseTag = "harden-folder"` and the aggregated folder-level summary as the PR description data source. One branch, one PR.
Todo 10: Emit `RunSummary v1 | Phase: Folder` (orchestrator block) plus the per-file rows table and the Next Steps section per the Routing Decision Table.
```

### Routing Decision Table (Todo 2 dispatch)

The discovery skill returns one of seven classifications. This table is authoritative for what happens next.

| Classification | Folder action | Next |
|----------------|---------------|------|
| `single-test-file` | route to `Octane.TestHardening.End2End` with the same arguments | end |
| `folder-of-tests` (count ≤ `max files`) | proceed to Todo 3 | continue |
| `folder-of-tests` (count > `max files` AND ≤ 100) | emit the soft-cap ambiguity message from the discovery skill; stop | end |
| `folder-empty` | emit the discovery-skill ambiguity message; stop | end |
| `folder-no-test-files` | emit the discovery-skill ambiguity message; stop | end |
| `production-file` | emit the discovery-skill ambiguity message; stop | end |
| `non-existent-path` | emit the discovery-skill ambiguity message; stop | end |
| `ambiguous-too-large` | emit the discovery-skill ambiguity message; stop | end |

### 1. Discover & Classify (Todo 2)

Invoke the [test-file-discovery skill](../skills/test-file-discovery/SKILL.md) with the `test path` and `max files` inputs. Read its full output, then dispatch on the `Classification:` line per the routing table above.

**You may not skip classification.** Auditing a production file would be a guardrail violation; the discovery step is what prevents that.

### 2. Parallel Audit Fan-Out (Todo 3)

For each discovered test file, spawn a sub-agent via the `agent` tool. Each sub-agent receives:

- The agent identifier `TestHardening`.
- The prompt file `Octane.TestHardening.Audit.prompt.md`.
- The input bindings: `test name = <file path>`, `test folder = <folder path>`, `stability evidence URL = <forwarded value or n/a>`.

Run all sub-agents **in parallel**. The audit prompt is read-only, so concurrent execution is safe.

Each sub-agent returns a `RunSummary v1 | Phase: Audit` block plus the per-finding bullets. Collect all N blocks before proceeding.

### 3. Reduce to FolderAudit (Todo 4)

Aggregate the N audit blocks into a single `RunSummary v1 | Phase: FolderAudit` block per the [run-summary skill](../skills/run-summary/SKILL.md). Sum the `findings-kept`, `findings-discarded`, `production-blocked` fields; average the `avg-confidence` weighted by `findings-kept`.

**Folder-level Standalone Stop-Gate**: if every file's `findings-kept` is zero, emit:

> Test Hardening -- Folder audit complete. No hardening findings across `<N>` test files in `<folder path>`. All audited tests are already well-structured.

and stop. Do not proceed to Improve.

### 4. Improve (Hybrid: cross-project parallel, in-project sequential) (Todo 5 - Todo 7)

Group the worklist by **owning test project**, identified by the nearest ancestor `.csproj`, `pyproject.toml`, `package.json`, or `go.mod`. Files that share a project go into one bucket; different projects go into different buckets.

For each project bucket, spawn an Improve sub-agent via the `agent` tool. **Project sub-agents run in parallel.** Each sub-agent receives:

- Agent identifier `TestHardening`.
- Prompt file `Octane.TestHardening.Improve.prompt.md`.
- Per-file audit blocks from Todo 3 (filtered to this project's files).
- Forwarded `category filter` if supplied.

Inside each project sub-agent (sequential, one file at a time, preserving discovery order):

1. Parse the file's audit block into a worklist.
2. Apply the per-file `category filter` (if supplied).
3. Run the Per-Finding Application Protocol from [`Octane.TestHardening.Improve.prompt.md`](Octane.TestHardening.Improve.prompt.md). The protocol's assertion-preservation, proportionality, and Bug-Gate cross-checks all apply unchanged.
4. Record per-file rows: `file`, `applied`, `skipped (reasons)`, `production-blocked`.

After every file in the project is edited:

5. The project sub-agent runs build **once** for that project via the [build-and-test skill](../skills/build-and-test/SKILL.md). Classify per [build-outcome-classification skill](../skills/build-outcome-classification/SKILL.md). Run each target test once.
6. Return the per-file rows and the project-level build outcome to the parent.

**Todo 6 (parent reduce).** Collect every project sub-agent's build outcome. Folder-level outcome is the worst case: `LOCAL_BUILD_BLOCKED` > `LOCAL_BUILD_FAILED_BY_EDIT` > `LOCAL_BUILD_OK`.

**Todo 7 (per-class stress fan-out).** Group files with applied `stability-by-design` findings by their **owning test class** (e.g., `MyServiceTests`). Spawn one stress sub-agent per class via the `agent` tool. **Class sub-agents run in parallel.** Each sub-agent stress-validates the test methods belonging to its class per [`stress-validation-protocol`](../skills/stress-validation-protocol/SKILL.md), following the partial-revert rules. Methods within a single class stay serial inside their sub-agent (shared fixtures). The parent aggregates per-class pass rates into the folder-level stress outcome.

### 5. Pre-Submit Invariant (Todo 8)

Run:

```powershell
git diff --stat
```

Every changed path **must** be inside a test file (matches one of the discovery globs OR resides under a Tests / tests / __tests__ subtree). If any production file appears in the diff:

- Stop immediately.
- Emit `RunSummary v1 | Phase: Folder` with `hardening-status: aborted` and `next-action: developer-finish-manually`.
- Do not call Submit.

### 6. Single Submit (Todo 9)

Call [`Octane.TestHardening.Submit.prompt.md`](Octane.TestHardening.Submit.prompt.md) once for the whole folder. Inputs:

- `$phaseTag = "harden-folder"` → branch name `dev/<username>/harden-folder<8-char-hex>`
- PR description data source: the aggregated `RunSummary v1 | Phase: FolderImprove` block from Todo 5–7
- PR title: `(AI Generated) Test hardening: <folder name> (<N> files)`

Draft state follows the same rules as single-file Submit: `true` when any file reports `Cloud validation: required` OR `Stress validation: stress-failed`; `false` otherwise.

### 7. Aggregate Output (Todo 10)

Emit, in order:

1. `RunSummary v1 | Phase: Folder` orchestrator block (see [run-summary skill](../skills/run-summary/SKILL.md)).
2. Per-file rows table: `file | findings (applied/skipped) | build | stress | status`.
3. Next Steps section per the End2End next-action enum. The folder-level next action is the **strongest** per-file next action, in this priority order:
   1. `developer-finish-manually` (any file's build failed)
   2. `production-refactor-required` (every file required production changes)
   3. `developer-create-pr-from-pushed-branch` (Submit failed)
   4. `review-draft-pr-after-cloud-build` (any file required cloud validation)
   5. `merge-when-checks-pass` (all files clean)
   6. `none` (zero findings across all files)

## PR Body Composition

The folder PR body MUST fit in 4,000 characters. To stay under the limit when `N` is large, use the per-file totals format below in the PR description; the full per-finding detail stays in the chat output only.

```markdown
## Test Hardening (Folder Mode)

### Scope
**Folder:** `<resolved folder path>`
**Files audited:** <N>
**Files edited:** <M of N>

### Aggregated Findings
| Category | Applied | Skipped |
|----------|---------|---------|
| assertion-strength | <a1> | <s1> |
| edge-case-coverage | <a2> | <s2> |
| stability-by-design | <a3> | <s3> |
| parameterization | <a4> | <s4> |
| naming-and-intent | <a5> | <s5> |
| mock-saturation | <a6> | <s6> |

### Per-File Summary
| File | Applied | Skipped | Build | Stress |
|------|---------|---------|-------|--------|
| <file1> | <a> | <s> | <outcome> | <pass-rate / n/a> |
| <file2> | <a> | <s> | <outcome> | <pass-rate / n/a> |
| ... | ... | ... | ... | ... |

### AI Tool Used
**AI-Model:** Claude Opus 4.6 (copilot)
**AI-Agent:** TestHardening (folder mode)
**Prompt:** Octane.TestHardening.Folder

### Validation
**Build outcome:** <LOCAL_BUILD_OK | LOCAL_BUILD_FAILED_BY_EDIT | LOCAL_BUILD_BLOCKED>
**Cloud validation required:** <yes | no>

### Production Code Changed
None -- hardening scope is test code only across all <N> files.
```

If the per-file table would push the body over 4,000 chars, fall back to listing only files where `applied > 0` and add `<X files had zero applied findings; see chat output for details>`.

## Phase-Unique Skill Files

| Skill | Path | Purpose |
|-------|------|---------|
| test-file-discovery | [`../skills/test-file-discovery/SKILL.md`](../skills/test-file-discovery/SKILL.md) | Classify the `test path` input and enumerate test files in a folder. |
| build-and-test | [`../skills/build-and-test/SKILL.md`](../skills/build-and-test/SKILL.md) | Single build at end of Todo 5. |
| build-outcome-classification | [`../skills/build-outcome-classification/SKILL.md`](../skills/build-outcome-classification/SKILL.md) | Classify the single build outcome (Todo 6). |
| stress-validation-protocol | [`../skills/stress-validation-protocol/SKILL.md`](../skills/stress-validation-protocol/SKILL.md) | Per-file stress validation (Todo 7). |
| save-branch-and-push (shared) | [`../../../shared/skills/save-branch-and-push/SKILL.md`](../../../shared/skills/save-branch-and-push/SKILL.md) | One branch for the whole folder; `$phaseTag = "harden-folder"`. |
| detect-default-branch (shared) | [`../../../shared/skills/detect-default-branch/SKILL.md`](../../../shared/skills/detect-default-branch/SKILL.md) | Default-branch detection (Submit). |
| pr-description | [`../skills/pr-description/SKILL.md`](../skills/pr-description/SKILL.md) | PR template (adapted via the PR Body Composition section above). |

Universal skills (`hardening-guardrails`, `run-summary`) are loaded automatically per the agent file.

## Rules of Engagement

Universal invariants live in [`../skills/hardening-guardrails/SKILL.md`](../skills/hardening-guardrails/SKILL.md) (always loaded). Folder-mode-specific enforcement:

- **Classification first.** No file may be audited until the discovery skill has returned `folder-of-tests`. Production files, empty folders, and non-existent paths must stop with the classification message.
- **No reordering after fan-out.** Improve order matches discovery order so the developer's `git log` mirrors the file-list ordering they saw in the audit.
- **One branch, one PR.** Folder mode never opens per-file PRs. If the developer wants per-file PRs, they re-run with a single file argument.
- **Build once.** Per-file build runs are wasteful at this scale. Build at the end and revert files whose individual edits broke compilation.
- **Stress per file.** Stress validation runs **per file** for any file with applied `stability-by-design` edits. Do not pool stress runs.
- **Production diff guardrail (Todo 8).** Pre-Submit `git diff --stat` is the last line of defense. Any production file in the diff aborts the Submit step.
- **Hard ceiling 100.** Above 100 test files the discovery skill returns `ambiguous-too-large`; this prompt refuses to proceed. Split the run.

## Output Format

Follow [`../skills/run-summary/SKILL.md`](../skills/run-summary/SKILL.md) for the `RunSummary v1 | Phase: Folder` template. Emit the orchestrator block before the per-file rows table and Next Steps section. Use `n/a` for fields that do not apply.
