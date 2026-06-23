---
name: pr-templates
description: |
  PR description, review digest, and validation report templates for the PR Orchestrator workflow.
  Use when generating Phase 1 validation reports, Phase 2 PR descriptions, or Phase 4 review digest comments.
  Contains structured templates with placeholder variables for validation evidence,
  gate results, advisory findings, and reviewer guidance.
---

# PR Templates

Templates for generating structured PR descriptions and review digest comments.

## References

| File | Used By | Purpose |
|------|---------|---------|
| [pr-body.md](references/pr-body.md) | Phase 2 (Create PR) | Structured PR description with validation evidence |
| [review-summary.md](references/review-summary.md) | Phase 4 (Review Digest) | Single digest comment with verdict table and upsert marker |
| [prevalidate-report.md](references/prevalidate-report.md) | Phase 1 (Pre-Validate) | Structured validation report with digests, gates, advisory, and review findings |
| [digest-upsert.md](references/digest-upsert.md) | Phase 5 (Address Feedback) | Instructions for updating the digest comment in-place after fixing review feedback |

## Usage

Phase 2 (`Octane.PROrchestrator.CreatePr.prompt.md`) fills in `pr-body.md` placeholders with:
- Intent summary, change groups, gate results, advisory findings, test results, reviewer guidance

Phase 4 (`Octane.PROrchestrator.ReviewDigest.prompt.md`) fills in `review-summary.md` placeholders with:
- Overall verdict, summary table, gate results, auto-fix diffs, advisory findings, human focus items

The `review-summary.md` template includes a `<!-- ai-agent:pr-orchestrator-digest -->` HTML marker for idempotent comment upsert.
