---
name: reviewer-eval
description: >
  Evaluate specialist reviewer output quality against a 5-category rubric.
  Scores detection accuracy, severity calibration, actionability, scope discipline,
  and signal-to-noise ratio. Use after Stage 3.5 to quality-gate reviewer findings
  before aggregation.
metadata:
  author: octane
  version: "1.0"
---

# Reviewer Eval Skill

Scores the output of specialist reviewers (security, reliability, performance, or custom) against a structured evaluation rubric. Produces per-reviewer quality scores that can be used to filter low-quality findings before they reach the final report.

## When to Use

Use this skill **after specialist reviewers complete (Stage 3.5)** and **before result aggregation (Stage 4)**. It acts as a quality gate — findings from reviewers scoring below a configurable threshold can be flagged or excluded.

Typical trigger points:
- **Automated**: Orchestrator invokes after all specialist dispatches return
- **Manual**: User runs `/reviewer-eval` to score a specific reviewer's last output
- **CI/CD**: Post-review quality check before posting PR comments

## How to Invoke

### From the orchestrator (Stage 3.6)

The orchestrator queries completed specialist review results, then dispatches an eval agent for each:

```sql
SELECT reviewer_name, model, findings, non_findings
FROM gk_specialist_reviews
WHERE status = 'completed';
```

For each row, the eval agent:
1. Reads the rubric from `references/evaluation-criteria.md`
2. Compares findings against the actual source files (ground truth)
3. Produces a scored evaluation

### Manual invocation

```
/reviewer-eval <reviewer-name>
```

Evaluates the most recent output from the named reviewer.

## Input

The eval skill requires:

| Input | Source | Description |
|-------|--------|-------------|
| Reviewer output | `gk_specialist_reviews` table | The `findings` and `non_findings` JSON from a completed review |
| Source files | Repository working tree | The actual code files referenced in findings (for ground-truth verification) |
| Reviewer prompt | `reviewers/<name>.reviewer.md` | The reviewer's declared scope, categories, and severity definitions |
| Rubric | `references/evaluation-criteria.md` | The 5-category scoring criteria |

## Evaluation Process

### Step 1 — Ground Truth Check

For each reported finding:
1. Verify the referenced file exists
2. Verify the line range exists and contains the pattern described
3. Check if the code snippet quoted matches actual source
4. Flag any hallucinated findings (references to code that doesn't exist)

### Step 2 — Category Scoring

Score each of the 5 categories (1.0–5.0 scale, decimals encouraged):

| Category | What it measures |
|----------|-----------------|
| **Detection Accuracy** | Are findings real and verifiable in source code? |
| **Severity Calibration** | Do severity levels match actual risk/impact? |
| **Actionability** | Can a developer fix issues from the suggestions alone? |
| **Scope Discipline** | Does the reviewer stay within its declared domain? |
| **Signal-to-Noise** | Are findings worth reading vs trivial/obvious? |

See `references/evaluation-criteria.md` for detailed scoring rubrics per category.

### Step 3 — Compute Overall Score

**Overall score** = arithmetic mean of 5 category scores, rounded to 1 decimal place.

### Step 4 — Quality Gate Decision

| Overall Score | Action |
|---------------|--------|
| ≥ 4.0 | **Pass** — All findings included in final report |
| 3.0 – 3.9 | **Warn** — Findings included with quality warning annotation |
| < 3.0 | **Flag** — Findings included but marked as `low_confidence`; user notified |

> **Note:** No findings are silently dropped. Low scores add metadata to help users prioritize, not censor output.

## Output

### SQL Storage

```sql
INSERT INTO gk_reviewer_evals (
  reviewer_name, model, overall_score,
  detection_accuracy, severity_calibration, actionability,
  scope_discipline, signal_to_noise,
  summary, improvements, evaluated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'));
```

### Markdown Report

Produces a per-reviewer evaluation in this format:

```markdown
# Specialist Reviewer Evaluation

**Reviewer:** <name>
**Model:** <model or "default">
**Files reviewed:** <count>
**Violations reported:** <count>
**Overall score:** X.X / 5.0
**Quality gate:** Pass | Warn | Flag
**Summary:** <one sentence, max 25 words>

## Scores

| Category | Score |
|----------|-------|
| Detection Accuracy | X.X |
| Severity Calibration | X.X |
| Actionability | X.X |
| Scope Discipline | X.X |
| Signal-to-Noise Ratio | X.X |

## Category Notes

### Detection Accuracy
- **Rationale:** <1 short sentence>
- **Findings:** <1–2 bullets with specific examples>

[... repeat for each category ...]

## Top Improvements (max 3)
- <improvement 1>
- <improvement 2>
- <improvement 3>
```

## Integration with Multi-Model Review

When multi-model dispatch is enabled, each reviewer × model combination gets its own eval score. This surfaces which models produce higher-quality output for which review domains:

```sql
-- Compare model quality per reviewer
SELECT reviewer_name, model, overall_score
FROM gk_reviewer_evals
ORDER BY reviewer_name, overall_score DESC;
```

Deduplication (Stage 3.5 step 8) runs **before** eval — the eval scores the deduplicated output, not raw per-model output.
