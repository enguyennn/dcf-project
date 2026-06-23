---
name: test-hardening-fixtures
description: Golden-output fixtures for the test-hardening scenario. Maintainers diff future prompt-run outputs against these fixtures to detect regressions when a prompt is edited.
---

# Test-Hardening Fixtures

This skill provides canonical example outputs for the three runnable prompts in the test-hardening scenario (Audit, Improve, End2End). Each fixture is a complete, well-formed emission against a synthetic test case described in the fixture itself.

Fixtures are **illustrative**, not load-bearing. The prompts do not read these files at runtime. They exist so a maintainer who edits a prompt can:

1. Run the prompt against the synthetic test case in the fixture.
2. Diff the actual output against the golden.
3. Investigate any unexpected delta before merging.

This is a lightweight stand-in for proper prompt-eval tooling. When such tooling lands, these fixtures graduate into its corpus.

## Fixtures

| Fixture | Phase | Synthetic case |
|---------|-------|----------------|
| [audit-golden.md](references/audit-golden.md) | Audit | A C# MSTest test with one assertion-strength gap, one stability-by-design gap, one parameterization opportunity. |
| [improve-golden.md](references/improve-golden.md) | Improve | The same test case, with the audit applied, showing per-finding diffs and a `LOCAL_BUILD_OK` outcome. |
| [end2end-golden.md](references/end2end-golden.md) | End2End | The full orchestrator block for the same case, with a successful ADO PR. |

## Usage

Maintainers, after editing any prompt in this scenario:

1. Re-run the affected prompt against the fixture's synthetic case (manually or via a future eval harness).
2. `diff` the actual output against the golden.
3. **Expected deltas**: changes to text the prompt was deliberately rewritten to emit (e.g., a reworded header). These are acceptable -- update the golden.
4. **Unexpected deltas**: missing fields, schema-violation, dropped findings, wrong next-action. These are regressions -- investigate before merging.

## Fixture Validity

Every fixture must:

- Start with the `Schema: RunSummary v1` header from `../run-summary/SKILL.md`.
- Use only enumerated values for enum-typed fields.
- Cover at least one non-trivial finding per category that the synthetic case exercises.

If a prompt change requires extending the schema, the fixture must be updated in the same commit so the golden stays parseable under the new version.
