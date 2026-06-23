# Specialist Reviewer Evaluation Rubric

Use this rubric to evaluate the output quality of Gatekeeper specialist reviewers (security, reliability, performance, or custom). Each review is scored across 5 categories on a 1.0–5.0 scale.

**Overall score** = arithmetic mean of 5 category scores, rounded to 1 decimal place.

Decimals are encouraged (e.g., 3.6) to capture nuance. Do not round to whole numbers.

---

## Category 1: Detection Accuracy

Does the reviewer report real issues that actually exist in the code?

| Score | Description |
|-------|-------------|
| 5.0 | Every reported violation is genuine and verifiable in the source code; no hallucinations |
| 4.0 | Nearly all findings are real; one minor false positive at most |
| 3.0 | Most findings are real, but 2–3 false positives or phantom code references |
| 2.0 | Multiple hallucinated violations; references to code that doesn't exist |
| 1.0 | Majority of findings are fabricated or based on imagined code patterns |

**Key signals:**
- Does the reviewer reference actual line numbers that exist?
- Are quoted code snippets present in the source file?
- Does the violation description match what the code actually does?
- Are there "phantom" findings about patterns not present in the diff?

---

## Category 2: Severity Calibration

Do the assigned severity levels (Critical/High/Medium/Low) match the actual risk and impact?

| Score | Description |
|-------|-------------|
| 5.0 | All severity ratings accurately reflect real-world impact; Critical = exploitable, Low = minor |
| 4.0 | Mostly well-calibrated; one severity over- or under-rated by one level |
| 3.0 | Several miscalibrated severities; some Medium issues rated Critical or vice versa |
| 2.0 | Systematic over- or under-rating; "everything is Critical" or "everything is Low" |
| 1.0 | Severity assignments appear random or inverted from actual impact |

**Key signals:**
- Critical findings should be immediately exploitable or cause data loss
- High findings should have clear security/reliability/performance impact
- Medium findings should be concerning but not immediately dangerous
- Low findings should be improvements or defense-in-depth measures
- Style nits should never appear (reviewers should not flag style)

---

## Category 3: Actionability

Can a developer fix the reported issue using only the suggestion provided?

| Score | Description |
|-------|-------------|
| 5.0 | Every suggestion is specific, implementable, and includes enough context to fix immediately |
| 4.0 | Nearly all suggestions are actionable; one may need minor clarification |
| 3.0 | Most suggestions point in the right direction but lack specifics (e.g., "add error handling") |
| 2.0 | Suggestions are vague ("improve this") or describe the problem without a solution |
| 1.0 | Suggestions are missing, circular ("fix the issue"), or technically incorrect |

**Key signals:**
- Does the suggestion name specific APIs, patterns, or techniques?
- Could a junior developer implement the fix from the suggestion alone?
- Does the suggestion avoid introducing new problems?
- Is the fix proportional to the issue (not over-engineered)?

---

## Category 4: Scope Discipline

Does the reviewer stay within its declared focus area and avoid duplicate work?

| Score | Description |
|-------|-------------|
| 5.0 | All findings are squarely within the reviewer's domain; no scope bleed |
| 4.0 | Nearly all findings are in scope; one borderline finding |
| 3.0 | Some findings overlap with other reviewers' domains (e.g., security reviewer flagging performance) |
| 2.0 | Significant scope bleed; reviewer acts as a general code reviewer |
| 1.0 | Reviewer ignores its declared focus; findings are random across domains |

**Key signals:**
- Security reviewer should not flag formatting or naming conventions
- Performance reviewer should not flag authentication patterns
- Reliability reviewer should not flag algorithm complexity (unless it causes crashes)
- Each reviewer should respect its `scope_globs` file patterns
- Findings should map to the analysis categories listed in the reviewer's prompt

---

## Category 5: Signal-to-Noise Ratio

What proportion of findings are genuinely important vs trivial, duplicate, or obvious?

| Score | Description |
|-------|-------------|
| 5.0 | Every finding is worth reading; high-value insights that a human reviewer might miss |
| 4.0 | Strong signal with at most one trivial finding; prioritization is clear |
| 3.0 | Mix of valuable and obvious findings; some that any linter would catch |
| 2.0 | Mostly noise; findings restate what the code already handles or flag non-issues |
| 1.0 | Pure noise; findings are trivial, redundant, or already addressed in the code |

**Key signals:**
- Are there findings that go beyond what static analysis tools detect?
- Does the reviewer avoid flagging code that already has proper guards?
- Are there duplicate findings for the same underlying issue?
- Does the reviewer avoid flagging intentional patterns (e.g., explicit `any` casts with documented reasons)?

---

## Output Format

When evaluating a specialist reviewer's output, produce results in this format:

```markdown
# Specialist Reviewer Evaluation

**Reviewer:** <reviewer name>
**Files reviewed:** <count>
**Violations reported:** <count>
**Overall score:** X.X / 5.0
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

### Severity Calibration
- **Rationale:** <1 short sentence>
- **Findings:** <1–2 bullets with specific examples>

### Actionability
- **Rationale:** <1 short sentence>
- **Findings:** <1–2 bullets with specific examples>

### Scope Discipline
- **Rationale:** <1 short sentence>
- **Findings:** <1–2 bullets with specific examples>

### Signal-to-Noise Ratio
- **Rationale:** <1 short sentence>
- **Findings:** <1–2 bullets with specific examples>

## Top Improvements (max 3)
- <improvement 1>
- <improvement 2>
- <improvement 3>
```

---

## Evaluation Guidelines

1. **Ground truth required** — Always compare reviewer output against the actual source code. Never evaluate output in isolation.
2. **Severity anchoring** — Use the severity definitions from the reviewer's own prompt as the baseline for calibration scoring.
3. **Domain expertise** — Evaluators should have working knowledge of the reviewer's domain (security, reliability, or performance).
4. **Sample size** — Evaluate across at least 3 different files or code changes for a reliable score.
5. **Version tracking** — Record the reviewer version (from scenario.json) with each evaluation for trend analysis.

---

## Baseline Reference Scores

The following scores were established by running each specialist reviewer against the golden test fixtures in `reviewers/references/golden-test/`. These serve as regression baselines — significant drops from these scores indicate a reviewer prompt regression.

| Reviewer | Detection | Severity | Actionability | Scope | Signal:Noise | Overall | Version |
|----------|:---------:|:--------:|:------------:|:-----:|:------------:|:-------:|:-------:|
| Security | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | **5.0** | v3.2.0 |
| Reliability | 5.0 | 4.0 | 5.0 | 4.5 | 4.5 | **4.6** | v3.2.0 |
| Performance | 4.0 | 3.5 | 5.0 | 5.0 | 4.5 | **4.4** | v3.2.0 |

**Quality gate thresholds:**
- ≥ 4.0 — Pass (findings accepted as-is)
- 3.0–3.9 — Warn (findings annotated with quality advisory)
- < 3.0 — Flag (reviewer output needs manual review)

**Key observations at baseline:**
- All reviewers pass the quality gate
- Security reviewer achieves perfect scores across all categories
- Reliability reviewer shows minor severity overcalibration (High→Critical on 2 items)
- Performance reviewer missed one Low-severity finding and shows severity inflation on 3 items
- Zero false positives from any reviewer at baseline
