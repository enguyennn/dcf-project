---
name: custom-reviewers
description: >
  Guide for creating custom specialist reviewers. Explains the Octane agent format,
  required frontmatter fields, output schema, and how to register custom reviewers
  in gkpconfig.yml.
metadata:
  author: octane
  version: "2.0"
---

# Creating Custom Reviewers

Custom specialist reviewers extend the Gatekeeper review pipeline with domain-specific analysis. Each reviewer is a self-contained agent definition that runs autonomously against repository code.

## How to Create a Custom Reviewer

1. Create an agent file in the `agents/` directory following the naming convention: `Octane.{Name}Reviewer.agent.md` (e.g., `Octane.DocsQualityReviewer.agent.md`).
2. Include YAML frontmatter with at minimum: `name`, `description`, `scope_globs`, and `tools`.
3. Follow the same JSON output format as the built-in reviewers (violations array with `file_name`, `startline`, `endline`, `detection`, `violation`, `guideline`, `suggestion`, `severity`).
4. Include the autonomous execution and JSON output marker instructions.
5. Add the reviewer short name (derived from the filename: `Octane.{Name}Reviewer.agent.md` → lowercase `{name}`) to `reviewers` in `gkpconfig.yml`.

## Naming Convention

| Filename | Short Name | Config Key |
|----------|------------|------------|
| `Octane.SecurityReviewer.agent.md` | `security` | `security` |
| `Octane.ReliabilityReviewer.agent.md` | `reliability` | `reliability` |
| `Octane.DocsQualityReviewer.agent.md` | `docsquality` | `docsquality` |

The short name is derived by stripping `Octane.` prefix, `Reviewer.agent.md` suffix, and lowercasing.

## Frontmatter Schema

```yaml
---
name: {Name}Reviewer
description: <What this reviewer checks for>
scope_globs:
  - "**/*.ts"
  - "**/*.py"
tools:
  - read
  - search
---
```

The `scope_globs` field is **required** — it tells `prepare_review.py` which files to match for this reviewer. Without it, the agent file will not be recognized as a specialist reviewer.

## Output Format

Specialist reviewers must output their findings as a JSON object between markers:

```
========= JSON START =============
{
  "guidelines_reviewed": ["<name>-review"],
  "files_reviewed": ["file1.ts", "file2.ts"],
  "violations": [
    {
      "file_name": "src/auth.ts",
      "startline": "42",
      "endline": "48",
      "detection": "Brief description of what was detected",
      "violation": "Detailed explanation of the issue",
      "guideline": "<name>-review",
      "suggestion": "How to fix the issue",
      "severity": "Critical|High"
    }
  ],
  "non_violations": [
    {
      "file_name": "path/to/clean/file.ts",
      "reason": "No issues found"
    }
  ]
}
========= JSON END =============
```

## Built-in Reviewers

The following built-in reviewers are available in the `agents/` directory:

| Reviewer | File | Focus |
|----------|------|-------|
| Security | `Octane.SecurityReviewer.agent.md` | Injection, auth bypass, data exposure |
| Reliability | `Octane.ReliabilityReviewer.agent.md` | Error handling, null refs, resource mgmt |
| Performance | `Octane.PerformanceReviewer.agent.md` | Algorithmic issues, resource leaks, DB/IO |
| Quality | `Octane.QualityReviewer.agent.md` | Test coverage, feature flags, deployment safety |
| Domain | `Octane.DomainReviewer.agent.md` | Repo-local knowledge skills, contract violations, cross-component ripple |

## Enabling Custom Reviewers

After creating the agent file, add it to `gkpconfig.yml`:

```yaml
reviewers:
  guidelines_reviewer:
    model: claude-sonnet-4
    guidelines_root: .github/skills
  security:
    model: claude-sonnet-4
  docsquality:        # your custom reviewer
    model: claude-sonnet-4
```
