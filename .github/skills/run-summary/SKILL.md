---
name: run-summary
description: Versioned output schema (RunSummary v1) for the test-hardening scenario. All four prompts emit a slice of this schema so downstream parsers see one stable contract instead of four drifting blocks.
---

# RunSummary v1

This skill defines the machine-parseable output contract used by the test-hardening prompts. Each phase (Audit, Improve, Submit, End2End) emits a **slice** of `RunSummary v1` -- the fields relevant to that phase. The End2End orchestrator assembles a full slice from its sub-prompts plus its own orchestration fields.

`RunSummary v1` is **additive only**: future versions may add fields, but no existing field is renamed or removed. Downstream parsers (the orchestrator, telemetry, the survey funnel) can rely on field names.

## Header Convention

Every emitted block starts with a fixed header line so a parser can dispatch on schema version and phase:

```
Schema: RunSummary v1 | Phase: <Audit | Improve | Submit | End2End | FolderAudit | FolderImprove | Folder>
```

The phase determines which fields are required, optional, or n/a. Fields that do not apply must be present with value `n/a` -- never omitted.

## Field Catalog

The full field catalog is below. Field names use kebab-case in the parser; the human-readable label (`Target:`, `Build outcome:`) is what the prompt emits. Each row lists which phase emits the field and whether the field is required (R) or optional (O).

| Field (label) | Audit | Improve | Submit | End2End | Notes |
|---------------|-------|---------|--------|---------|-------|
| `target` | R | R | n/a | R | Test name / class / file. |
| `test-framework` | R | n/a | n/a | n/a | MSTest, xUnit, NUnit, pytest, etc. |
| `files-inspected` | R | n/a | n/a | n/a | `N test files, M production files`. |
| `findings-kept` | R | n/a | n/a | n/a | Total kept with `(high=h, medium=m, low=l)` breakdown. |
| `findings-discarded` | R | n/a | n/a | n/a | Count that failed Bug Gate. |
| `production-blocked` | R | n/a | n/a | n/a | Count of `requires-production-change: true`. |
| `findings-overflow` | R | n/a | n/a | n/a | Kept findings beyond the top-15 cap. |
| `audit-findings` | n/a | n/a | n/a | R | `TOTAL (kept=K, discarded=D)` from Audit. |
| `avg-confidence` | R | n/a | n/a | R | 0-10. |
| `stability-evidence` | R | n/a | n/a | n/a | `not provided` / `unavailable` / `used`. |
| `target-file` | n/a | R | n/a | n/a | Path being edited. |
| `findings-applied` | n/a | R | R | R | `N of TOTAL` (Improve) / `N` (Submit, End2End). |
| `findings-skipped` | n/a | R | R | R | `M of TOTAL` (Improve) with reasons. |
| `build-outcome` | n/a | R | n/a | R | `LOCAL_BUILD_OK` / `LOCAL_BUILD_FAILED_BY_EDIT` / `LOCAL_BUILD_BLOCKED`. |
| `build-attempts` | n/a | R | n/a | R | `K of 3`. |
| `tests-pass-fail` | n/a | R | n/a | n/a | `P passed, F failed` or `n/a` if BLOCKED. |
| `stress-validation` | n/a | R | n/a | R | `<pass-rate%>` / `stress-failed` / `deferred-to-cloud` / `not-applicable`. |
| `cloud-validation` | n/a | R | R | n/a | `required` / `not-required`. |
| `working-tree` | n/a | R | n/a | R | `clean` / `drafted-edits-present`. |
| `hardening-status` | n/a | R | n/a | n/a | `completed` / `aborted` / `blocked-by-production-dependencies`. |
| `improve-outcome` | n/a | n/a | n/a | R | Mirror of `hardening-status` for orchestrator view. |
| `repository-platform` | n/a | n/a | n/a | R | `ADO` / `GitHub` / `unknown`. |
| `platform` | n/a | n/a | R | n/a | `ADO` / `GitHub` (Submit early-exit may emit `unknown`). |
| `branch` | n/a | n/a | R | n/a | Source branch name. |
| `target-branch` | n/a | n/a | R | n/a | Default branch from Submit step 3. |
| `pr-number` | n/a | n/a | R | n/a | `#NNNNN`. |
| `pr-url` | n/a | n/a | R | R | Full URL. |
| `pr-draft` | n/a | n/a | R | R | `true` / `false`. |
| `pr-created` | n/a | n/a | n/a | R | `#NNNNN` / `n/a`. |
| `linked-work-item` | n/a | n/a | R | n/a | `#NNNN` / `none`. |
| `files-changed` | n/a | n/a | R | n/a | Count; must be test-only. |
| `feedback-survey` | n/a | n/a | R | n/a | Survey URL. |
| `next-action` | n/a | R | n/a | R | One of the enumerated next-action values. |

## Next-Action Enum

`next-action` must be exactly one of:

- `hand-off-to-submit`
- `developer-finish-manually`
- `production-refactor-required`
- `developer-create-pr-from-pushed-branch`
- `merge-when-checks-pass`
- `review-draft-pr-after-cloud-build`
- `manual-pr-on-github` (reserved for `platform: unknown`; not used when the remote is `github.com`)
- `none`

## Folder-Mode Field Catalog

Folder mode adds the fields below; existing fields keep the same semantics. All folder-mode fields use kebab-case in the parser; the human-readable label is what the prompt emits.

| Field (label) | FolderAudit | FolderImprove | Folder | Notes |
|---------------|-------------|---------------|--------|-------|
| `scope` | R | R | R | `folder` -- distinguishes folder-mode emissions from single-file. |
| `folder-path` | R | R | R | Absolute path of the scanned folder. |
| `files-discovered` | R | n/a | R | Test files discovered by the discovery skill. |
| `files-audited` | R | n/a | n/a | Files that successfully completed an audit sub-agent. |
| `files-with-findings` | R | n/a | R | Files where the audit returned `findings-kept > 0`. |
| `files-edited` | n/a | R | R | Files where Improve applied at least one finding. |
| `files-skipped` | n/a | R | R | Files where every finding was skipped or filtered. |
| `aggregate-findings-kept` | R | n/a | R | Sum of `findings-kept` across all files. |
| `aggregate-findings-applied` | n/a | R | R | Sum of `findings-applied` across all files. |
| `aggregate-findings-skipped` | n/a | R | R | Sum of `findings-skipped` across all files. |
| `aggregate-avg-confidence` | R | n/a | R | Weighted by per-file `findings-kept`. |
| `category-rollup` | R | R | R | Per-category counts `<applied / skipped>` -- six rows for the six hardening categories. |
| `build-outcome-folder` | n/a | R | R | Single folder-level build outcome (one build at the end). |
| `stress-outcomes` | n/a | R | R | Map of `<file>: <pass-rate% \| stress-failed \| deferred-to-cloud \| not-applicable>`. |
| `per-file-summary` | R | R | R | Table rows used as supplementary detail; not parsed for routing. |

## Phase Emission Templates

### Audit phase

```
Schema: RunSummary v1 | Phase: Audit
Test Hardening -- Audit complete.
  Target:             <test name / class / file>
  Test framework:     <MSTest | xUnit | NUnit | pytest | other>
  Files inspected:    <N test files>, <M production files>
  Findings kept:      <count>   (high=<h>, medium=<m>, low=<l>)
  Findings discarded: <count>   (failed Bug Gate)
  Production-blocked: <count>   (requires-production-change=true)
  Findings overflow:  <count>   (kept out of top-15 report)
  Avg confidence:     <0-10>
  Stability evidence: <not provided | unavailable | used>
```

### Improve phase

```
Schema: RunSummary v1 | Phase: Improve
Test Hardening -- Improve complete.
  Target file:        <path>
  Findings applied:   <N> of <TOTAL>
  Findings skipped:   <M> of <TOTAL>   (reasons: requires-production-change=<a>, requires-helper=<b>, non-minimal-diff=<c>, edit-does-not-close-gap=<d>, category-filter-excluded=<e>, low-confidence-after-audit=<f>)
  Build outcome:      <LOCAL_BUILD_OK | LOCAL_BUILD_FAILED_BY_EDIT | LOCAL_BUILD_BLOCKED>
  Build attempts:     <K> of 3
  Tests pass/fail:    <P> passed, <F> failed   (or n/a if BLOCKED)
  Stress validation:  <pass-rate% | stress-failed | deferred-to-cloud | not-applicable>
  Cloud validation:   <required | not-required>
  Working tree:       <clean | drafted-edits-present>
  Hardening status:   <completed | aborted | blocked-by-production-dependencies>
  Next action:        <hand-off-to-submit | developer-finish-manually | production-refactor-required | none>
```

### Submit phase (success)

```
Schema: RunSummary v1 | Phase: Submit
Test Hardening -- Submit complete.
  Platform:           <ADO | GitHub>
  Branch:             <source branch name>
  Target branch:      <default branch name>
  PR number:          <#NNNNN>
  PR URL:             <full URL>
  Draft:              <true | false>
  Cloud validation:   <required | not-required>
  Linked work item:   <#NNNN | none | n/a>
  Findings applied:   <N>
  Findings skipped:   <M>
  Files changed:      <count> (test only)
  Feedback survey:    https://forms.office.com/r/thBs5xqGSi
```

Notes:
- `Linked work item` is `n/a` for GitHub (work-item linking is ADO-only).
- `PR URL` is the full `https://github.com/<owner>/<repo>/pull/<NNN>` or `https://msazure.visualstudio.com/.../_git/.../pullrequest/<NNN>`.

### Submit phase (unknown-platform skip)

```
Schema: RunSummary v1 | Phase: Submit
Test Hardening -- Submit skipped.
  Platform:           unknown
  Reason:             non-ADO/non-GitHub remote -- manual PR submission required
  Branch (local):     <current branch name>
  Files changed:      <count> (test only)
```

### Submit phase (PR creation failure)

```
Schema: RunSummary v1 | Phase: Submit
PR creation failed.
  Platform:           <ADO | GitHub>
  Branch (pushed):    <source branch name>
  Target branch:      <default branch name>
  Failure reason:     <exact error from MCP response or `gh` stderr>
  Manual create URL:  <ADO pullrequestcreate URL | GitHub compare URL>
  Next action:        developer-create-pr-from-pushed-branch
```

### End2End phase (orchestrator)

```
Schema: RunSummary v1 | Phase: End2End
Test Hardening -- Full run complete.
  Target:             <test name>
  Repository platform:<ADO | GitHub | unknown>
  Audit findings:     <TOTAL>   (kept=<K>, discarded=<D>)
  Avg confidence:     <0-10>
  Improve outcome:    <completed | aborted | blocked-by-production-dependencies>
  Build outcome:      <LOCAL_BUILD_OK | LOCAL_BUILD_FAILED_BY_EDIT | LOCAL_BUILD_BLOCKED>
  Build attempts:     <K> of 3
  Findings applied:   <N>
  Findings skipped:   <M>
  Stress validation:  <pass-rate% | stress-failed | deferred-to-cloud | not-applicable>
  Working tree:       <clean | drafted-edits-present>
  PR created:         <#NNNNN | n/a>
  PR draft:           <true | false | n/a>
  PR URL:             <full URL | n/a>
  Next action:        <next-action enum value>
```

### FolderAudit phase (reduce of N parallel audits)

```
Schema: RunSummary v1 | Phase: FolderAudit
Test Hardening -- Folder audit complete.
  Scope:                folder
  Folder path:          <absolute path>
  Files discovered:     <N>
  Files audited:        <M of N>
  Files with findings:  <K of M>
  Aggregate findings kept:      <count>   (high=<h>, medium=<m>, low=<l>)
  Aggregate findings discarded: <count>   (failed Bug Gate, summed across files)
  Aggregate production-blocked: <count>   (requires-production-change=true)
  Aggregate avg confidence:     <0-10>    (weighted by findings-kept per file)
  Category rollup:              <assertion-strength=<a>, edge-case-coverage=<b>, stability-by-design=<c>, parameterization=<d>, naming-and-intent=<e>, mock-saturation=<f>>
  Per-file summary:
    <file 1>: <kept>/<discarded> findings, avg-confidence <0-10>
    <file 2>: ...
```

### FolderImprove phase (sequential apply across files, single build)

```
Schema: RunSummary v1 | Phase: FolderImprove
Test Hardening -- Folder improve complete.
  Scope:                folder
  Folder path:          <absolute path>
  Files edited:         <M of N>
  Files skipped:        <S of N>
  Aggregate findings applied:   <N>   (applied counts summed across all files)
  Aggregate findings skipped:   <M>   (skipped counts summed across all files; reasons rolled up: requires-production-change=<a>, requires-helper=<b>, non-minimal-diff=<c>, edit-does-not-close-gap=<d>, category-filter-excluded=<e>, low-confidence-after-audit=<f>)
  Category rollup (applied/skipped):
    assertion-strength:   <a_app>/<a_skip>
    edge-case-coverage:   <b_app>/<b_skip>
    stability-by-design:  <c_app>/<c_skip>
    parameterization:     <d_app>/<d_skip>
    naming-and-intent:    <e_app>/<e_skip>
    mock-saturation:      <f_app>/<f_skip>
  Build outcome (folder): <LOCAL_BUILD_OK | LOCAL_BUILD_FAILED_BY_EDIT | LOCAL_BUILD_BLOCKED>
  Build attempts:         <K> of 3
  Tests pass/fail:        <P> passed, <F> failed   (or n/a if BLOCKED)
  Stress outcomes:
    <file 1>: <pass-rate% | stress-failed | deferred-to-cloud | not-applicable>
    <file 2>: ...
  Cloud validation:       <required | not-required>
  Working tree:           <clean | drafted-edits-present>
  Hardening status:       <completed | aborted | blocked-by-production-dependencies>
  Next action:            <hand-off-to-submit | developer-finish-manually | production-refactor-required | none>
```

### Folder phase (orchestrator)

```
Schema: RunSummary v1 | Phase: Folder
Test Hardening -- Folder run complete.
  Scope:                  folder
  Folder path:            <absolute path>
  Repository platform:    <ADO | GitHub | unknown>
  Files discovered:       <N>
  Files with findings:    <K of N>
  Files edited:           <M of N>
  Files skipped:          <S of N>
  Aggregate findings applied: <N>
  Aggregate findings skipped: <M>
  Aggregate avg confidence:   <0-10>
  Category rollup (applied/skipped):  <one line, six categories>
  Build outcome (folder): <LOCAL_BUILD_OK | LOCAL_BUILD_FAILED_BY_EDIT | LOCAL_BUILD_BLOCKED>
  Stress outcomes:        <summarized: pass=<a>, failed=<b>, deferred=<c>, n/a=<d>>
  Working tree:           <clean | drafted-edits-present>
  PR created:             <#NNNNN | n/a>
  PR draft:               <true | false | n/a>
  PR URL:                 <full URL | n/a>
  Next action:            <next-action enum value>
```

Folder-mode `next-action` resolution: take the **strongest** per-file next action in this priority order (highest wins): `developer-finish-manually` > `production-refactor-required` > `developer-create-pr-from-pushed-branch` > `review-draft-pr-after-cloud-build` > `merge-when-checks-pass` > `none`.

## Versioning Policy

- Adding a new field is **non-breaking** and stays at v1.
- Renaming a field is **breaking** and requires v2 (with a corresponding compat shim in the orchestrator).
- Removing a field is **breaking** and requires v2.
- Changing the semantics of an enum value (e.g., re-defining `LOCAL_BUILD_OK`) is **breaking** and requires v2.

Maintainers: when bumping to v2, keep this file at v1 and add `run-summary-v2/SKILL.md` so old prompts continue to parse.
