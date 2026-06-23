---
name: risk-classification
description: |
  Classify PR risk level (Low/Medium/High) based on file sensitivity, blast radius,
  change type, and security relevance. Determines review requirements.
  Use when: assessing change risk during pre-validation or PR creation.
---

# Risk Classification

> Classify change risk to determine review requirements.

> **Attribution**: Adapted from the [self-serve-bugfix](https://github.com/azure-core/octane/tree/main/artifacts/scenarios/self-serve-bugfix) `risk_classifier` Conductor workflow stage.

## Execution Rules

- You MUST produce a risk classification — never skip this step
- Use `grep` and `glob` to assess downstream impact
- Distinguish security hardening from security-adjacent feature work (see Classification Rules)

## Inputs

- Changed file list
- Business Logic Digest (for blast radius info)
- Detected project context

## Risk Signals

| Signal | How to Assess |
|--------|---------------|
| **File sensitivity** | Auth/security files, infrastructure/config (CI, Dockerfiles, IaC), database schemas/migrations, public API surface |
| **Change scope** | Number of files changed, lines added/removed, number of modules touched |
| **Blast radius** | Downstream callers/consumers of changed code (use `code-search` if available), cross-package imports |
| **Change type** | New feature, bug fix, refactor, dependency update, documentation-only |
| **Security relevance** | Changes to auth, crypto, input validation, secrets handling, network-facing code |

## Risk Levels

| Level | Icon | Criteria | Review Requirement |
|-------|------|----------|--------------------|
| **Low** | 🟢 | Docs-only, config tweaks, test-only changes, single-file fixes with no downstream callers, dependency patches | AI review sufficient — human review optional |
| **Medium** | 🟡 | Multi-file changes, internal API changes, new features with tests, refactors with limited blast radius, security hardening (fixing vulnerabilities, tightening controls) | Standard human review recommended |
| **High** | 🔴 | New auth/security features, public API signature changes, infrastructure/deployment changes, database migrations, changes with 5+ downstream callers, dependency major version bumps, expanding attack surface | SME review required — flag specific expertise needed |

## Classification Rules

1. **Security-adjacent feature work bumps to High** — new auth flows, new crypto, new secrets handling, new network-facing endpoints, or expanding the attack surface
2. **Security hardening stays at Medium** — fixing existing vulnerabilities (XSS, injection, quoting), adding input validation to existing code, tightening existing security controls. These changes *reduce* risk, not introduce it.
3. **Public API breaks always bump to High** — removed/renamed exports, changed function signatures
4. **Blast radius escalation** — 5+ downstream callers/consumers bumps to at least Medium
5. **Docs/tests-only stays Low** — unless the tests reveal a behavior change

## Output

```
Risk Level: {🟢 Low | 🟡 Medium | 🔴 High}
Signals: {list of signals that determined the level}
Review Requirement: {AI review sufficient | Standard human review | SME review required}
Expertise Needed: {specific domain if High, e.g., "Security", "Database", "API Design"}
```
