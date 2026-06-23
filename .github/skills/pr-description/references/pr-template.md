# Test Hardening Pull Request Title and Description Generation

## Pull Request Title Template
Use the following format for PR titles:
```
(AI Generated) Test hardening: [TestMethodName] in [TestClassName]
```

Example:
```
(AI Generated) Test hardening: TestVirtualMachineCreation in ComputeServiceTests
```

## Pull Request Description Template

When generating pull request descriptions for test hardening improvements, use the following template:

```markdown
## Test Hardening

### Test Information
**Test Method:** `[TestMethodName]`
**Test Class:** `[TestClassName]`
**Test Project:** `[TestProjectName]`
**Test File Path:** `[RelativePathToTestFile]`

### AI Tool Used Summary
**AI-Model:** [Claude/GPT-4/Other - specify the AI model used]
**AI-Agent:** [Agent name, e.g., TestHardening]
**AI-Agent-Version:** [Version if available, otherwise N/A]

### Hardening Categories Applied
<!-- List every hardening category from the audit that produced at least one edit -->
- [ ] Assertion strength
- [ ] Edge-case coverage
- [ ] Stability-by-design
- [ ] Parameterization
- [ ] Naming and intent
- [ ] Mock saturation

### Audit Findings Applied
<!-- One bullet per applied finding: [impact/confidence/failure-mode] file:line range -- category -- before/after summary -->
- [Example] [high/9/logic] `Foo.Tests.cs:42-44` -- assertion-strength -- replaced `Assert.NotNull(result)` with `Assert.AreEqual(Expected, result.Status)`

### Audit Findings Skipped
<!-- Every audit finding not applied, with reason (requires-production-change, requires-helper, etc.) -->
- [Example] `Foo.Tests.cs:88` -- stability-by-design -- skipped (`requires-helper`: no `WaitForCondition` helper found in project)

### Production Code Changed
None -- hardening scope is test code only.

### Validation Results
<!-- Build, single-test, and (when applicable) stress validation -->
**Build outcome:** [LOCAL_BUILD_OK | LOCAL_BUILD_BLOCKED]
**Tests pass/fail:** [P passed, F failed]
**Stress validation:** [pass-rate% | deferred-to-cloud | not-applicable]

### Cloud Validation Required
<!-- Include this section only when local validation was blocked, stress was deferred, or stress failed. The PR must be created as Draft in that case. -->
[List what could not run locally: compile of the edited file, pass of each method under Audit Findings Applied, stress run for any stability-by-design edits, stress-failing test method when applicable.]

### Additional Notes
[Any additional context, follow-up items, or reviewer guidance.]

---
<!-- Metadata for audit and analytics - DO NOT REMOVE -->
**Metadata:**
- Test-Framework: [MSTest/xUnit/NUnit/pytest/Other]
- Service-Area: [ServiceName if applicable]
- Avg-Confidence: [0-10 from the audit summary]
- Findings-Applied: [N]
- Findings-Skipped: [M]
- Prompt: [The prompts (or prompt files) used for this hardening run]
```
