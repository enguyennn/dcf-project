---
name: octane-coder-review
description: >-
  Review implementation changes against a PRD's requirements and generate a
  comprehensive `.review.md` validation report with requirement traceability,
  scope-compliance tracking, gap analysis, and a pass/fail verdict. Use when
  the user says "review this implementation", "validate against the PRD",
  "check my changes", or wants the validation phase of Spec-Driven
  Development.
metadata:
  type: operational
  agent: SddCoder
  version: "1.0"
---

# Review Implementation Against PRD

Conduct a comprehensive review of implementation changes against a Product
Requirements Document (PRD) and generate a detailed validation report. This
is the validation phase of the Spec-Driven Development (SDD) workflow:
Requirements → Plan → Implement → Review.

## When to Use

- The user says "review this implementation", "validate against the PRD", or
  "check my changes"
- The user has a `.prd.md` file and a set of changes (commits, branch, or
  files) to validate
- The agent should be `SddCoder` (see
  [agents/Octane.SddCoder.agent.md](../../agents/Octane.SddCoder.agent.md)); it
  carries the declared model, tool allow-list, and the scope-compliance
  guarantees this skill depends on. If a different agent is active, this
  skill will delegate — see [Agent Delegation](#agent-delegation-mandatory).

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `PRD` | Yes | A link to a PRD file (e.g. `.prd.md`) that contains the requirements and implementation plan to validate against. |
| `Scope` | Yes | The scope of changes to review: a commit hash or range (e.g. `abc123` or `abc123..def456`), a branch name (e.g. `feature/embedded-artifacts`), a list of specific modified files, or the string `workspace` to review all current changes. |

If `PRD` or `Scope` is missing, stop and ask. Do not provide an example
request — just state that the inputs are required.

## Agent Delegation (MANDATORY)

This skill is designed to run under the `SddCoder` agent (see
[agents/Octane.SddCoder.agent.md](../../agents/Octane.SddCoder.agent.md)), which
carries the model declaration, the `code-search/*` tool allow-list, and the
scope-compliance + traceability guarantees this review workflow assumes.

**Before executing any step below, check the active agent:**

- **If the active agent IS `SddCoder`** → proceed to
  `## Primary Directive`.
- **If the active agent is NOT `SddCoder`** → you MUST delegate this
  skill's execution to `SddCoder` instead of running it yourself. Use the
  host's agent-switching mechanism:
  - **VS Code Copilot Chat**: instruct the user to re-invoke under the target
    agent (e.g., `@SddCoder /octane-coder-review …`) and stop.
  - **Copilot CLI**: re-invoke with `--agent SddCoder` (e.g.,
    `copilot --agent SddCoder -p "/octane-coder-review …"`) or launch
    `SddCoder` as a sub-agent for this task and pass through the inputs.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch to
    `SddCoder` as a sub-agent and forward `PRD` and `Scope`.

Do **not** silently execute the workflow under a generic or unrelated agent
— the review quality contract (traceability matrix, scope-compliance
checks) assumes the `SddCoder` tool allow-list and guarantees, and
running it elsewhere may miss untraced changes or fabricate compliance.

## Primary Directive

Conduct a comprehensive review of the implementation changes specified in
`${input:Scope}` against ALL requirements, goals, and specifications defined
in the `${input:PRD}` document. Generate a detailed validation report that:

- **Verifies complete implementation** of all requirements and tasks
- **Identifies gaps, deviations, or missing implementations**
- **Validates quality standards** including tests, documentation, and best
  practices
- **Provides actionable recommendations** for addressing any findings

## Steps

Present the following steps as **trackable todos** to guide progress.

1. **Load and Parse PRD**
   - Read the complete PRD document from `${input:PRD}`.
   - Extract all requirements (REQ-, SEC-, CON-, GUD-, PAT- prefixed items).
   - Extract all EPICs and their associated tasks (ITEM- prefixed).
   - Identify success criteria, constraints, and quality standards.
   - Note risk classifications and mitigation strategies.

2. **Analyze Scope of Changes**
   - Identify all files modified within `${input:Scope}`.
   - If scope is a branch/PR: get diff against base branch.
   - If scope is commits: analyze all changes in the commit range.
   - If scope is "workspace": review all uncommitted changes.
   - Generate a comprehensive list of all modified files and their change
     types (added/modified/deleted).

3. **Deep Implementation Review**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Use the `code-search/*` tools to perform deep code analysis on all
       changed files.
     - Map each change to the corresponding PRD requirements, EPICs, and
       tasks.
     - Create a traceability matrix linking PRD items to actual changes.
     - Verify each implemented feature matches PRD specifications exactly.
     - Check that removed/deleted components listed in the PRD are actually
       removed.
     - Validate that architectural decisions align with the Solution
       Architecture section.
     - Confirm file modifications match the Files section (FILE- items).
     - Verify no unintended side effects or breaking changes.
     - Identify any changes that don't map to PRD requirements (scope creep)
       — flag each as an "Untraced Change".
     - Flag files modified that are NOT listed in the PRD's Files section
       (Section 12).
     - Flag any drive-by changes: formatting, style, comment rewrites,
       refactoring, or "improvements" outside the stated scope.
     - Respond with a structured JSON or markdown summary of all findings.

4. **Requirements & Quality Validation**
   - Use the `agent` tool to invoke a sub-agent that will:
     - Validate each requirement category against the implementation:
       - **Functional Requirements (REQ-)**: Verify feature implementation
         completeness.
       - **Security Requirements (SEC-)**: Validate security controls are in
         place.
       - **Constraints (CON-)**: Check performance, size, compatibility
         limits.
       - **Guidelines (GUD-)**: Verify adherence to best practices.
       - **Patterns (PAT-)**: Confirm design patterns are correctly applied.
     - Verify all tests specified in the Quality & Testing section are
       implemented.
     - Check test coverage meets requirements.
     - Validate documentation updates match the Documentation section.
     - Confirm build/deployment changes align with the Deployment section.
     - Review error handling and edge cases.
     - Respond with a structured compliance report for each requirement.

5. **Generate Validation Report**
   - Synthesize findings from sub-agent reviews into a comprehensive
     `.review.md` report.
   - Perform gap analysis: identify all PRD requirements NOT met by the
     implementation.
   - List all EPIC tasks that are incomplete or missing.
   - Assess risk of identified issues.
   - Provide prioritized recommendations for remediation.
   - Calculate metrics on implementation completeness.
   - Save the report following the file naming convention.

## Review Criteria

Evaluate implementation against these standards:

### Completeness
- All EPICs are fully implemented
- All tasks (ITEM-) are completed as specified
- All requirements (REQ-, SEC-, CON-, etc.) are satisfied
- All specified files are modified/created/deleted as planned

### Containment (Scope Compliance)
- Every changed line traces to a specific EPIC, ITEM, or requirement
- No files were modified outside the PRD's Files section without
  justification
- No drive-by changes: formatting, style, comment rewrites, or refactoring
  outside scope
- No unnecessary abstractions, configurability, or flexibility beyond what
  the PRD specifies

### Correctness
- Implementation matches PRD specifications exactly
- No logic errors or bugs introduced
- Proper error handling implemented
- Edge cases addressed

### Quality
- Code follows specified patterns and guidelines
- Tests provide adequate coverage
- Documentation is complete and accurate
- Performance meets specified constraints

### Compliance
- Security requirements are met
- Backward compatibility maintained (if required)
- Platform compatibility verified
- Deployment strategy followed

## Review Best Practices

- Be **precise and specific** — reference exact file names, line numbers, and
  code elements
- Provide **actionable feedback** — don't just identify problems, suggest
  solutions
- Use **objective metrics** — quantify completeness, coverage, and compliance
- Include **positive findings** — acknowledge what was done well
- Maintain **traceability** — link every finding back to specific PRD
  requirements
- Be **exhaustive** — review EVERY requirement, don't skip any

## File Naming Convention

- Save the review report in the same directory as the PRD.
- Use the naming pattern: `[prd-name].review.md`.
- Example: If the PRD is `embedded-artifacts.prd.md`, save as
  `embedded-artifacts.review.md`.

## Mandatory Template

```markdown
---
prd: [Path to PRD document being validated]
scope: [Description of changes reviewed]
date_reviewed: [YYYY-MM-DD]
reviewer: GitHub Copilot
compliance_status: [COMPLIANT | PARTIALLY_COMPLIANT | NON_COMPLIANT]
completion_percentage: [0-100%]
---

# PRD Implementation Review Report

## Executive Summary

[High-level summary of review findings, overall compliance status, and critical issues]

## Scope of Review

**PRD Document**: `${input:PRD}`
**Changes Reviewed**: `${input:Scope}`
**Total Files Modified**: [count]
**Review Date**: [date]

## Requirements Compliance

### Functional Requirements

| Requirement | Status | Implementation | Notes |
|------------|--------|---------------|-------|
| REQ-001 | ✅ PASS / ❌ FAIL / ⚠️ PARTIAL | [File:line where implemented] | [Any deviations or issues] |

### Security Requirements

[Similar table for SEC- items]

### Constraints & Guidelines

[Similar table for CON-, GUD-, PAT- items]

## EPIC Implementation Status

### EPIC-001: [Name]

| Task | Status | Completion | Findings |
|------|--------|------------|----------|
| ITEM-001 | ✅ COMPLETE / ❌ MISSING / ⚠️ PARTIAL | [Details] | [Issues found] |

**EPIC Completion**: [X/Y tasks complete - Z%]

[Repeat for all EPICs]

## Scope Compliance

[Verify that the implementation contains ONLY changes specified in the PRD. This is the complement of Requirements Compliance — it checks for containment, not completeness.]

### Untraced Changes
[List any code changes that do not map to a specific requirement, EPIC, or ITEM in the PRD.]

| File | Change Description | Mapped To | Verdict |
|------|-------------------|-----------|---------|
| [file:line] | [What was changed] | [EPIC/ITEM/REQ or NONE] | ✅ TRACED / ⚠️ UNTRACED |

### Files Outside PRD Scope
[List any modified files NOT listed in the PRD's "Files" section (Section 12)]

### Drive-By Changes
[Flag any formatting changes, style adjustments, comment rewrites, refactoring, or "improvements" to code outside the stated scope. These indicate scope creep.]

## Gap Analysis

### Critical Gaps
1. **[Gap Title]**: [Description of missing implementation]
   - PRD Reference: [EPIC/ITEM/REQ number]
   - Impact: [HIGH/MEDIUM/LOW]
   - Recommendation: [Specific action to address]

### Minor Deviations
1. **[Deviation Title]**: [Description of deviation from PRD]
   - Expected: [What PRD specified]
   - Actual: [What was implemented]
   - Recommendation: [How to align]

## Quality Assessment

### Test Coverage
- **Required Tests**: [count from PRD]
- **Implemented Tests**: [count found]
- **Coverage Gap**: [missing test descriptions]

### Documentation
- **Required Updates**: [list from PRD]
- **Completed Updates**: [list of actual updates]
- **Missing Documentation**: [list gaps]

### Performance & Constraints
[Actual vs Required for each constraint]

## Risk Assessment

| Risk | Status | Mitigation | Notes |
|------|--------|------------|-------|
| RISK-001 | ✅ MITIGATED / ⚠️ PARTIAL / ❌ UNADDRESSED | [Implementation details] | [Observations] |

## Recommendations

### Priority 1 - Critical (Must Fix)
1. [Specific action with file/line reference]

### Priority 2 - Important (Should Fix)
1. [Specific action with file/line reference]

### Priority 3 - Minor (Nice to Have)
1. [Specific action with file/line reference]

## Metrics Summary

- **Total Requirements**: [count]
- **Requirements Met**: [count] ([percentage]%)
- **Total Tasks**: [count]
- **Tasks Completed**: [count] ([percentage]%)
- **Files Expected to Modify**: [count]
- **Files Actually Modified**: [count]
- **Test Coverage**: [percentage]%
- **Documentation Completeness**: [percentage]%

## Conclusion

[Summary statement on whether the implementation meets PRD requirements and is ready for deployment, or what must be addressed before approval]

## Appendix

### Files Reviewed
[List all files examined during review]

### Tools Used
- Code search patterns: [list key searches performed]
- Validation methods: [describe verification approaches]
```

## Example

```text
/octane-coder-review redis-migration/redis-migration.prd.md 9faf8ab..289682e
```

Produces a `redis-migration.review.md` report with a requirement
traceability matrix, EPIC completion status, scope-compliance tracking, gap
analysis, and an overall compliance verdict.

## Output

A `.review.md` report validating the implementation against the PRD, with
requirement traceability and scope-compliance tracking.

## Next Steps

After completing the review, present the following next steps to the user
based on the review findings:

**Review complete. Here are your next steps:**

**If gaps or issues were identified:**

1. **Address the gaps** — Implement missing requirements:
   ```text
   /octane-coder-implement <path-to-your-prd.md> <EPIC-with-gaps>
   ```
2. **Re-run the review** after fixes are applied:
   ```text
   /octane-coder-review <path-to-your-prd.md> <new-commit-range-stagedOrUnstagedFiles>
   ```

**If all requirements are met:**

1. **Merge your changes** — The implementation is complete and validated.
2. **Start the next feature** — Begin a new requirements document:
   ```text
   /octane-planner-requirements <new-feature-description>
   ```
   …or begin a new PRD directly:
   ```text
   /octane-planner-plan <new-feature-description>
   ```
