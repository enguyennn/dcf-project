---
description: Post a single review digest comment collecting all automated findings
agent: PROrchestrator
---

# Review Digest — Agent Prompt

Collect all automated findings from prior phases and produce a single human-readable review digest comment on the PR.

## Inputs

- **PR URL**: {{ workflow.input.pr_url }}
- **State file**: {{ workflow.input.state_file }}

{% if validate_digest is defined and validate_digest.output and not validate_digest.output.valid %}
### ⚠️ Validation Failures (Previous Attempt — MUST FIX)

Your previous digest failed format validation. The validator script found these violations:

{{ validate_digest.output.violations | json }}

**You MUST fix ALL violations in this attempt.** The validator checks:
- 7-column "What Was Fixed" tables: `# | File | Finding | Found By | Fixed By | Commit | Status`
- Validation Timeline: 5 phase rows, no em-dash (`—`) durations
- Mechanically Verified: 2 gate rows (Code Review + CI Build)
- All 9 required section headings present

Re-read the `review-summary.md` template in Step 1 and follow it exactly.
{% endif %}

## Skill Location

Read `skills/watch-and-validate/SKILL.md` (search `**/skills/watch-and-validate/SKILL.md` if needed).

## Workflow

### 1. Save Upstream Data

{% if workflow.input.state_file %}
**Primary source: State file from prior phases.**

The orchestrator accumulated structured outputs from all prior phases into a state file. Read it first:

```powershell
$stateFile = "{{ workflow.input.state_file }}"
if (Test-Path $stateFile) {
  $state = Get-Content $stateFile -Encoding UTF8 | ConvertFrom-Json
  Write-Host "State file loaded: $(($state | Get-Member -MemberType NoteProperty).Count) keys"
} else {
  Write-Host "WARNING: State file not found at $stateFile — falling back to defaults"
  $state = @{}
}
```

Copy the state file verbatim to `upstream-data.json`, adding only `pr_url`, `pr_title`, and `platform` if missing:

```powershell
# Start from the raw state — do NOT restructure, rename, or reconstruct any fields
$upstream = $state | ConvertTo-Json -Depth 10 | ConvertFrom-Json

# Add workflow inputs only if not already present
if (-not $upstream.pr_url) { $upstream | Add-Member -NotePropertyName 'pr_url' -NotePropertyValue '{{ workflow.input.pr_url }}' -Force }
if (-not $upstream.platform) {
  $platform = if ('{{ workflow.input.pr_url }}' -match 'github\.com') { 'github' } else { 'ado' }
  $upstream | Add-Member -NotePropertyName 'platform' -NotePropertyValue $platform -Force
}
if (-not $upstream.pr_title) {
  # Fetch from PR API if not in state
  $upstream | Add-Member -NotePropertyName 'pr_title' -NotePropertyValue '' -Force
}

$upstream | ConvertTo-Json -Depth 10 | Set-Content "$env:TEMP\upstream-data.json" -Encoding UTF8
Write-Host "upstream-data.json saved: $(($upstream | Get-Member -MemberType NoteProperty).Count) keys"
```

> ⚠️ **CRITICAL**: Copy the state JSON as-is. Do NOT manually construct `watch_and_fix`, `code_fix`, or `code_review_findings` objects from flat keys. The `build-digest-input.py` script handles normalization. If you reconstruct these objects, you WILL get incorrect data (wrong commit links, phantom findings for skipped phases).
{% else %}
Build `upstream-data.json` from the data you collected during earlier phases. The PR URL is provided as an input; gather remaining data from conversation context (Phase 1 validation results, Phase 3 watch-and-fix results, etc.).

Use this exact schema:

```json
{
  "pr_url": "{{ workflow.input.pr_url }}",
  "pr_title": "<PR title — fetch from PR if not in context>",
  "platform": "<ado or github — infer from PR URL>",
  "code_review_findings": { "<raw JSON from code review phase — include tier, important, suggestions>" },
  "code_fix": { "fixes_applied": 0, "fix_commits": [] },
  "risk_level": "<low|medium|high from risk classifier>",
  "risk_signals": ["<signal1>"],
  "advisory_security": {},
  "advisory_breaking": {},
  "advisory_docs": {},
  "advisory_coverage": {},
  "watch_and_fix": { "build_status": "<passed|failed>", "fixes_pushed": 0, "fix_summaries": [], "elapsed_minutes": 0 }
}
```

For any field where data is unavailable, use the defaults shown above. Do NOT invent data.
{% endif %}

Save to `$env:TEMP\upstream-data.json`.

> ⚠️ The script in Step 2 does all classification, verdict computation, and formatting. Do NOT write digest markdown directly.

### 2. Build Digest Input (Deterministic Script)

```powershell
$buildPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\build-digest-input.py"
python $buildPath "$env:TEMP\upstream-data.json" --output-file "$env:TEMP\digest-input.json"
```

This script deterministically:
- Maps code review findings → table rows with proper numbering, status, commit links
- Computes verdict from code review findings (no LLM judgment)
- Detects review engine from tier
- Builds timeline with actual durations
- Formats advisory results

### 3. Compose the Digest Markdown (Deterministic Script)

> ⚠️ **HARD GATE**: You MUST run `compose-digest.py` to generate the digest markdown. Do NOT write markdown directly. Do NOT improvise the digest format. The script guarantees correct structure (7-column tables, 5-phase timeline, 2-gate rows, all required sections). If you skip the script, the validator will reject the digest and force a retry.

```powershell
$scriptPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\compose-digest.py"
python $scriptPath "$env:TEMP\digest-input.json" --output-file "$env:TEMP\digest-output.md"
```

> ⚠️ Always use `--output-file` to write directly to disk. Do NOT pipe through PowerShell (`| Set-Content`) — PowerShell's cp1252 encoding garbles UTF-8 emoji in the output.

### 4. Validate the Digest (Deterministic Script)

```powershell
$validatePath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\validate-digest-format.py"
python $validatePath "$env:TEMP\digest-output.md"
```

If validation fails, fix the JSON input and re-run compose + validate. The violations tell you exactly what's wrong.

### 5. Post Inline Findings as PR Comments (Deterministic Script)

Before posting the digest, post each non-mechanical code review finding as an **inline PR comment** at the correct file and line. This gives reviewers findings in context, not just in the digest table.

{% if code_review is defined and code_review.output and code_review.output.code_review_findings %}
Save the raw code review findings JSON to a temp file — do NOT reconstruct or reclassify findings manually:
```powershell
@'
{{ code_review.output.code_review_findings | json }}
'@ | Set-Content "$env:TEMP\code-review-findings.json" -Encoding UTF8
```

Then run the post-findings script:
```powershell
$postPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\post-findings.py"
$platform = if ('{{ workflow.input.pr_url }}' -match 'github\.com') { 'github' } else { 'ado' }
python $postPath --platform $platform --pr-url "{{ workflow.input.pr_url }}" --findings-file "$env:TEMP\code-review-findings.json"
```

The script:
- Posts Important and Suggestion findings as inline comments at the file/line
- **Skips** mechanical Critical/Important findings (those were already auto-fixed by code_fix)
- Falls back to PR-level comments if the file path contains `...` or has no line number

> ⚠️ Do NOT manually reconstruct findings or change the `mechanical` classification. The script reads what code_review output produced.
{% else %}
> ℹ️ No code review findings available — skipping inline comment posting.
{% endif %}

### 6. Post the Digest (Deterministic Script)

```powershell
$upsertPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\upsert-digest.py"
$platform = if ('{{ workflow.input.pr_url }}' -match 'github\.com') { 'github' } else { 'ado' }
python $upsertPath --platform $platform --pr-url "{{ workflow.input.pr_url }}" --content-file "$env:TEMP\digest-output.md"
```

> ⚠️ If any script is not found, fall back to composing the digest manually using the review-summary.md template and posting via az CLI. But the script path should work if installed plugins were copied correctly.

> ⚠️ **Do NOT use `reply_to_comment`** — that adds a child comment, not an in-place update.

## Expected Output

Populate these output fields:

- **digest_comment_id**: ID of the posted/updated digest comment
- **digest_body**: The full markdown content of the digest that was posted (needed by validate_digest — pass it through so the validator doesn't need to re-fetch)
- **overall_verdict**: `ready`, `warnings`, `changes_needed`, or `running`
- **bot_threads_found**: Count of bot comment threads processed
- **risk_level_displayed**: Risk level shown in digest header (from top-level state keys, or `unknown` if unavailable)
- **checks_summary**: Summary table data for each check type (object with check name → status mapping)
