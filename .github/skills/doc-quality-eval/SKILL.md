---
name: doc-quality-eval
description: >
  Evaluate documentation against quality criteria and produce a structured
  report. Use to assess documentation health, identify gaps, and measure
  improvement over time. Outputs a JSON evaluation report.
compatibility: Requires PowerShell 7+. Windows or Linux.
metadata:
  author: Azure Build Health
  version: "1.0"
---

# Doc Quality Evaluation Skill

Produces a structured quality evaluation of documentation against defined criteria.

## When to Use

- After generating or reviewing documentation to measure quality
- As part of the orchestrator's pipeline to decide if another refine pass is needed
- To produce a quality dashboard or report for stakeholders

## Evaluation Structure

```
┌────────────────────────────────┐
│     HARD GATES (Pass/Fail)     │
│  HG1: No Hallucination         │
│  HG2: No Contradiction         │
└────────────────────────────────┘
              │
              ▼
┌────────────────────────────────┐
│   QUALITY DIMENSIONS (1-5)     │
│  Q1: Groundedness              │
│  Q2: Completeness              │
│  Q3: Relevance                 │
│  Q4: Clarity                   │
│  Q5: Actionability             │
└────────────────────────────────┘
```

## Hard Gates

Any gate failure = document is unacceptable.

- **HG1: No Hallucination** — all referenced APIs, parameters, behaviors exist in source code
- **HG2: No Contradiction** — no internal contradictions or misrepresentations of code behavior

## Quality Dimensions (1-5)

| Score | Label | Meaning |
|-------|-------|---------|
| 1 | Poor | Significant issues |
| 2 | Below Average | Notable gaps |
| 3 | Acceptable | Meets minimum expectations |
| 4 | Good | Minor issues only |
| 5 | Excellent | No issues |

### Dimensions

- **Q1 Groundedness** — claims supported by source context
- **Q2 Completeness** — covers required elements for its type
- **Q3 Relevance** — content useful, not filler
- **Q4 Clarity** — scannable, well-structured, understandable
- **Q5 Actionability** — reader can act on the information

## Output Format

Evaluation report at `<docs-dir>/.meta/evaluations/eval-<date>.json`:

```json
{
  "timestamp": "ISO-8601",
  "pages_evaluated": [
    {
      "path": "services/auth.md",
      "hard_gates": { "HG1": true, "HG2": true },
      "quality_scores": { "Q1": 4, "Q2": 3, "Q3": 4, "Q4": 5, "Q5": 3 },
      "page_average": 3.8,
      "recommendation": "accept"
    }
  ],
  "overall": {
    "total_pages": 12,
    "hard_gate_pass": true,
    "average_quality_score": 3.9,
    "recommendation": "accept"
  }
}
```

## References

See [evaluation criteria](references/evaluation-criteria.md) for detailed scoring rubrics.
