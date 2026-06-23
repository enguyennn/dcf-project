---
description: Generate the final review digest comment with all findings
agent: PROrchestrator
---

# Final Digest — Agent Prompt

Refresh the review digest comment on the PR with final results from all pipeline phases.

## Inputs

- **PR URL**: {{ workflow.input.pr_url }}

{% if fix_feedback is defined and fix_feedback.output is defined %}
### Address Feedback Results (Phase 5)
- Comments addressed: {{ fix_feedback.output.comments_addressed | default(0) }}
- Comments remaining: {{ fix_feedback.output.comments_remaining | default(0) }}
- Fix commits: {{ fix_feedback.output.fix_commits | default([]) | tojson }}
- All addressed: {{ fix_feedback.output.all_addressed | default(false) }}
{% endif %}

{% if scrape_fb_commits is defined and scrape_fb_commits.output is defined %}
### Scraped Commits
{{ scrape_fb_commits.output.stdout | default("No commit data") }}
{% endif %}

{% if scrape_fb_threads is defined and scrape_fb_threads.output is defined %}
### Scraped Thread State
{{ scrape_fb_threads.output.stdout | default("No thread data") }}
{% endif %}

{% raw %}
## Workflow

### 1. Build Phase 5 Merge Data

Save Phase 5 results to a JSON file for merging. Use the data from the fix_feedback agent output above:

```powershell
$phase5Data = @{
    pr_url = "{{ workflow.input.pr_url }}"
    address_feedback = @{
        comments_addressed = {{ fix_feedback.output.comments_addressed | default(0) }}
        comments_remaining = {{ fix_feedback.output.comments_remaining | default(0) }}
        fix_commits = @({{ fix_feedback.output.fix_commits | default([]) | map('tojson') | join(', ') }})
        all_addressed = {{ fix_feedback.output.all_addressed | default(false) | lower }}
    }
} | ConvertTo-Json -Depth 10
$phase5Data | Set-Content "$env:TEMP\phase5-data.json" -Encoding UTF8
```

If the template variables above didn't resolve (you see literal `{{` in the JSON), fall back to reading the scraped data files:

```powershell
# Fallback: build phase5-data.json from scraped files
$commits = if (Test-Path "$env:TEMP\scrape-fb-commits.json") { Get-Content "$env:TEMP\scrape-fb-commits.json" -Raw | ConvertFrom-Json } else { @{} }
$threads = if (Test-Path "$env:TEMP\scrape-fb-threads.json") { Get-Content "$env:TEMP\scrape-fb-threads.json" -Raw | ConvertFrom-Json } else { @{} }
$resolved = if ($threads.threads) { $threads.threads.resolved } else { @() }
$actionable = if ($threads.threads) { $threads.threads.actionable } else { @() }
@{
    pr_url = "{{ workflow.input.pr_url }}"
    address_feedback = @{
        comments_addressed = ($resolved | Measure-Object).Count
        comments_remaining = ($actionable | Measure-Object).Count
        fix_commits = @($commits.commits | ForEach-Object { $_.sha })
        all_addressed = (($actionable | Measure-Object).Count -eq 0)
    }
} | ConvertTo-Json -Depth 10 | Set-Content "$env:TEMP\phase5-data.json" -Encoding UTF8
```

### 2. Merge Phase 5 into Existing Digest Input (Deterministic Script)

Always rebuild the baseline from `upstream-data.json` (the authoritative Phase 4 state), then merge Phase 5 data onto it. This avoids trusting `digest-input.json` which may have been corrupted.

```powershell
$buildPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\build-digest-input.py"
$mergeArgs = @($buildPath, "$env:TEMP\phase5-data.json", "--output-file", "$env:TEMP\final-digest-input.json", "--upstream-fallback", "$env:TEMP\upstream-data.json")
if (Test-Path "$env:TEMP\digest-input.json") {
    $mergeArgs += @("--merge", "$env:TEMP\digest-input.json")
} else {
    # No digest-input.json from Phase 4 — rebuild baseline from upstream-data.json
    python $buildPath "$env:TEMP\upstream-data.json" --output-file "$env:TEMP\digest-input.json"
    $mergeArgs += @("--merge", "$env:TEMP\digest-input.json")
}
if (Test-Path "$env:TEMP\triage-output.json") {
    $mergeArgs += @("--triage-file", "$env:TEMP\triage-output.json")
}
& python @mergeArgs
if ($LASTEXITCODE -ne 0) { throw "build-digest-input.py failed (exit $LASTEXITCODE) — cannot produce a reliable digest" }
# DO NOT overwrite digest-input.json — it is the immutable Phase 4 baseline
```

### 3. Recompose the Digest (Deterministic Script)

```powershell
$composePath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\compose-digest.py"
python $composePath "$env:TEMP\final-digest-input.json" --output-file "$env:TEMP\final-digest.md"
```

### 4. Upsert the Final Digest

```powershell
$upsertPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\upsert-digest.py"
$platform = if ('{{ workflow.input.pr_url }}' -match 'github\.com') { 'github' } else { 'ado' }
python $upsertPath --platform $platform --pr-url "{{ workflow.input.pr_url }}" --content-file "$env:TEMP\final-digest.md"
```

### 5. Fix Encoding Artifacts (Deterministic Script)

On Windows, Conductor garbles Unicode characters. Run the encoding fix script:

```powershell
$scriptPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\fix-encoding.py"
python $scriptPath "$env:TEMP\final-digest.md"
```

If replacements were made, update the digest:
```powershell
$upsertPath = Join-Path $env:USERPROFILE ".copilot\installed-plugins\octane\octane-pr-orchestrator\skills\deterministic-scripts\scripts\upsert-digest.py"
$platform = if ('{{ workflow.input.pr_url }}' -match 'github\.com') { 'github' } else { 'ado' }
python $upsertPath --platform $platform --pr-url "{{ workflow.input.pr_url }}" --content-file "$env:TEMP\final-digest.md"
```

### 6. Report

> **NOTE:** Thread resolution (digest thread + feedback threads) is handled deterministically by the pipeline after this workflow completes. Do NOT manually call `az rest` to resolve threads.

```
PIPELINE_COMPLETE: verdict: {verdict} | fixes: {total_fixes} | comments: {total_comments}

✅ Final digest updated on PR.
PR: {{ workflow.input.pr_url }}
```

## Expected Output

- **final_verdict**: `approved`, `changes_requested`, or `pending`
- **pr_url**: PR URL
- **total_fixes_pushed**: Total fix commits across all phases
- **total_comments_addressed**: Total comments addressed in Phase 5
- **digest_updated**: `true` if digest was successfully updated
{% endraw %}
