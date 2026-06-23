# End2End Golden Fixture

This fixture is a canonical End2End-phase emission against the synthetic case from `audit-golden.md` and `improve-golden.md`. The orchestrator's role is to compose the Audit -> Improve -> Submit chain and emit a single run-level summary. Maintainers diff future End2End orchestrator blocks against this file.

## Scenario

- Repository platform: ADO.
- All three audit findings apply cleanly (per `improve-golden.md`).
- Submit creates a non-draft PR successfully.
- No bug URL provided.

## Stage 1: Audit (delegated)

Output matches `audit-golden.md` verbatim.

## Stage 2: Improve (delegated)

Output matches `improve-golden.md` verbatim.

## Stage 3: Repository Platform Detection

```powershell
git remote get-url origin
# returns https://msazure.visualstudio.com/<project>/_git/<repo>
```

Result: ADO. Proceed to Submit.

## Stage 4: Submit (delegated)

Submit emits:

```
Schema: RunSummary v1 | Phase: Submit
Test Hardening -- Submit complete.
  Platform:           ADO
  Branch:             hardening/ordervalidatortests-2026-05-11
  Target branch:      main
  PR number:          #12345
  PR URL:             https://msazure.visualstudio.com/<project>/_git/<repo>/pullrequest/12345
  Draft:              false
  Cloud validation:   not-required
  Linked work item:   none
  Findings applied:   3
  Findings skipped:   0
  Files changed:      1 (test only)
  Feedback survey:    https://forms.office.com/r/thBs5xqGSi
```

## Stage 5: Developer Summary

After Submit, End2End emits the orchestrator block and a developer-friendly Next Steps section.

## Golden End2End Orchestrator Block

```
Schema: RunSummary v1 | Phase: End2End
Test Hardening -- Full run complete.
  Target:             OrderValidatorTests
  Repository platform:ADO
  Audit findings:     5   (kept=3, discarded=2)
  Avg confidence:     8.3
  Improve outcome:    completed
  Build outcome:      LOCAL_BUILD_OK
  Build attempts:     1 of 3
  Findings applied:   3
  Findings skipped:   0
  Stress validation:  100%
  Working tree:       clean
  PR created:         #12345
  PR draft:           false
  PR URL:             https://msazure.visualstudio.com/<project>/_git/<repo>/pullrequest/12345
  Next action:        merge-when-checks-pass
```

## What this fixture validates

- The End2End orchestrator block conforms to `RunSummary v1`.
- Field values aggregate correctly from sub-phases:
  - `audit-findings TOTAL` = kept + discarded from Audit (3 + 2 = 5).
  - `findings-applied` mirrors Improve's value (3).
  - `pr-created`, `pr-draft`, `pr-url` mirror Submit's values.
- `next-action` is `merge-when-checks-pass` because the conditions hold: `LOCAL_BUILD_OK` + ADO + non-draft PR.
- Sub-prompt outputs (Audit, Improve, Submit) remain intact upstream of the orchestrator block; the orchestrator does not rewrite them.

## Variant goldens (out of scope for this fixture)

Future fixture additions could cover:

- `end2end-blocked-by-production-dependencies.md` -- all findings `requires-production-change`, no PR.
- `end2end-stress-failed.md` -- F2 fails stress, Submit creates Draft PR with `### Cloud Validation Required`.
- `end2end-pr-creation-failed.md` -- ADO `repo_create_pull_request` fails; manual create URL emitted.
- `end2end-github.md` -- GitHub repo, Submit skipped, summary instructs manual PR.

This fixture covers only the happy path. The variant goldens above are the next maintenance addition.
