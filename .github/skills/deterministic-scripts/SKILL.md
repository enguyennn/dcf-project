---
name: deterministic-scripts
description: |
  Deterministic Python scripts for PR Orchestrator operations.
  These scripts replace LLM-based operations that are 100% deterministic —
  pattern matching, template filling, format validation, API calls.
  Use when: called by PR Orchestrator prompts and workflow agents.
---

# Deterministic Scripts

> Python scripts that handle operations too important to leave to LLM judgment.

## Scripts

Two tables: **core operation scripts** (single-purpose JSON-in/JSON-out helpers) and
**pipeline & phase-driver scripts** (orchestration entry points invoked by Conductor
workflows or `run-phases.py`).

### Core operation scripts

| Script | Purpose | Input | Output |
|--------|---------|-------|--------|
| `classify-risk.py` | File path → risk level | JSON array of file paths | `{ risk_level, signals, expertise_needed }` |
| `compose-digest.py` | Structured data → digest markdown | JSON object with findings, gates, timeline | Complete markdown matching review-summary.md template |
| `detect-platform.py` | Git URL → platform info | URL string or auto-detect | `{ platform, org, project, repo }` |
| `fix-encoding.py` | Fix Conductor Unicode garble | Markdown file path | Fixed file (in-place) |
| `upsert-digest.py` | Find/create/update digest comment | `--platform`, `--pr-url`, `--content-file` | `{ action, comment_id, thread_id }` |
| `fix-pr-body.py` | Rebuild PR body from canonical template (post-LLM cleanup) | `--state-file`, `--pr-body-file` | Fixed markdown (pure transform, no API calls) |
| `validate-digest-format.py` | Check digest format compliance | Markdown file path | `{ valid, violations }` |
| `validate-pr-description.py` | Check PR description integrity | Markdown string (stdin) | `{ valid, overwritten_by, missing_sections }` |
| `build-digest-input.py` | Upstream data → digest-input JSON | JSON object with code review, gates, etc. | `digest-input.json` matching compose-digest.py schema |
| `post-findings.py` | Post inline review comments to PR | `--pr-url`, `--findings-file` | `{ posted_count, skipped_count }` |
| `scrape-commits.py` | Extract commit metadata from PR branch | `--base-sha`, `--head-sha` | `{ commits: [{ sha, message, files }] }` |
| `scrape-threads.py` | Scrape PR threads and build resolution state | `--pr-url`, `--baseline-file` | `{ threads, addressed_details, resolved_count }` |
| `triage-threads.py` | Classify PR threads for address-feedback | `--pr-url`, `--pr-author` | `{ actionable: [...], skipped: [...] }` |

### Pipeline & phase-driver scripts

These orchestrate the multi-phase pipeline (or wrap a core script with platform I/O).
They are invoked by Conductor workflow steps and by `run-phases.py`, not typically by hand.

| Script | Purpose | Input | Output |
|--------|---------|-------|--------|
| `run-phases.py` | Deterministic phase driver — runs Conductor workflows in strict, forward-only order, merging state after each phase | `--mode {yolo,yolo-fast}`, `--target-branch`, `--output-file` | Merged cross-phase state JSON |
| `bootstrap.py` | Collect deterministic PR bootstrap metadata (git/PR context) | git + PR args | Bootstrap metadata JSON |
| `merge-state.py` | Merge a Conductor phase's output into the cross-phase state file (robust JSON merge) | `--output-file`/stdin, `--state-file`, `--phase`, `--dry-run` | One-line summary; updated state file |
| `review-digest.py` | Phase 4 pipeline: build → compose → validate → post inline findings → upsert digest | `--pr-url`, `--platform`, `--state-file`, `--dry-run` | Posted digest + inline comments |
| `final-digest.py` | Phase 5 pipeline: build → merge onto Phase 4 baseline → compose → upsert → fix-encoding → resolve threads | `--pr-url`, `--platform`, `--state-file` | Posted final digest + resolved threads |
| `apply-pr-body-template.py` | Enforce PR-body template (wraps `fix-pr-body.py` with platform I/O); optionally replaces `DIGEST_LINK_PLACEHOLDER` | `--pr-url`, `--state-file`, `--digest-url`, `--work-dir` | Updated PR body |
| `apply-lint-fix.py` | Apply scoped lint auto-fixes to PR-changed files only (dotnet/node/python) | `--changed-files`, project-type | `{ formatters_run, files_fixed }` (in-place) |
| `post-digest-placeholder.py` | Post a placeholder digest thread so the digest is the first PR comment | `<pr_url> <platform>`, `--workspace-dir` | `{ thread_id }` + injected digest link |
| `resolve-pr-threads.py` | Resolve (Fixed/WontFix) PR comment threads on ADO/GitHub | `--pr-url`, `--thread-ids`/`--from-file`/`--digest-thread-id`, `--dry-run` | `{ resolved_count }` |
| `load-findings.py` | Load and validate a JSON findings file | findings JSON path (argv) | Validated JSON to stdout |
| `validate-phase1c-output.py` | Validate + normalize raw Phase 1c output before downstream use | raw output file/stdin, `--output-file` | Normalized phase1c JSON |
| `validate-phase1d-output.py` | Validate + normalize raw Phase 1d output before downstream use | raw output file/stdin, `--output-file` | Normalized phase1d JSON |

> **Note:** The two tables above list every user-facing entry-point script. The remaining files are internal modules (`encoding_utils.py`, `phase_contracts.py`, `phase_models.py`, `phase_output_validation.py`, `pr_platform.py`, `pr_url_utils.py`, `retry_utils.py`) — implementation details imported by the scripts above, not invoked directly.

## Usage

All scripts follow the same pattern: JSON in → JSON out. Run from any directory.

```powershell
# Find scripts
$scriptDir = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts"
if (-not (Test-Path $scriptDir)) { $scriptDir = Join-Path $env:USERPROFILE ".copilot\skills\deterministic-scripts\scripts" }

# Example: classify risk
'["src/Middleware/Auth.cs"]' | python "$scriptDir\classify-risk.py"
```

## Testing

```bash
cd skills/deterministic-scripts/scripts
pytest test_scripts.py -v
```
