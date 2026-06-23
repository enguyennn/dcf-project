---
name: build-and-test
description: |
  Build and test execution skill for validating test-hardening edits in local repository environments. Automatically activated when users request any of these tasks:
  - Build and run tests ("build the project", "run the tests", "run quickbuild")
  - Validate code changes ("check if my changes work", "verify the hardening edit")
---

# Build and Test Skill

This skill provides guidance for building test projects, and executing test suites in local development environments using PowerShell. Follow the steps below to determine the correct workflow based on the current repository.

## Steps

### 1. Identify the Current Repository

Determine the name of the repository where the user is currently working.

### 2. Determine the Test Type (QTest vs CloudTest)

Identify the test type based on signals in the bug report (e.g., Details, Repro Steps, Tags):

**QTest Indicators**:

- CloudBuild.FlakyTests.json
- References to QTest
- https://cloudbuild.microsoft.com

**CloudTest Indicators**:

- CloudTest.FlakyTests.json
- References to CloudTest

**Decision Rules**:

- If only QTest indicators → TestType = QTest
- If only CloudTest indicators → TestType = CloudTest
- If both or neither → **Stop the process and report ambiguity**

### 3. Select Workflow Using the Routing Table

Use **both the repository name and test type** to select the correct workflow from the routing table below.

| Repository | QTest Workflow Reference | CloudTest Workflow Reference |
|------------|-------------------|--------------------|
| Azure-Compute | [QTest ACM and AC](references/qtest-acm-and-ac.md) | [CloudTest ACM and AC](references/cloudtest-acm-and-ac.md) |
| Azure-Compute-Move | [QTest ACM and AC](references/qtest-acm-and-ac.md) | [CloudTest ACM and AC](references/cloudtest-acm-and-ac.md) |
| powerbi | [QTest Powerbi](references/qtest-powerbi.md) | ❌ Not Supported |
| Shared | [QTest Powerbi](references/qtest-powerbi.md) | ❌ Not Supported |

**Decision Rule:**

- If the repository name **matches an entry in the table**:
  - If the **selected test type has a valid workflow reference**:
    → Use the corresponding `.md` file from the table
  - If the **selected test type is NOT supported** (empty or ❌):
    → **Skip the Build and Test Skill entirely**

- If the repository name **does NOT match any entry in the table**:
  → Use the **Generic .NET Workflow** below

### 4. Execute the Workflow

If a valid workflow reference is selected:
- Open the referenced `.md` workflow file from the table
- Follow the instructions step by step

### 5. Generic .NET Workflow (Fallback)

Use this workflow when the repository does not match any entry in the routing table. This covers standard .NET projects using `dotnet` CLI.

#### 5.1. Locate the Test Project

Find the test project (`.csproj`) that contains the target test. Use workspace search to locate it by searching for the test class name or the project file.

#### 5.2. Build the Test Project

```powershell
dotnet build <path-to-test-project.csproj>
```

- Replace `<path-to-test-project.csproj>` with the actual path to the test project.
- If the build fails, report the errors and stop. Do not proceed to test execution.

#### 5.3. Run the Specific Test

```powershell
dotnet test <path-to-test-project.csproj> --filter "<TestMethodName>" --no-build
```

- Replace `<TestMethodName>` with the fully qualified or simple name of the test method.
- `--no-build` skips rebuilding since we already built in step 5.2.
- If the test fails, report the failure details (assertion messages, stack trace).

#### 5.4. Interpret Results

| Outcome | Action |
|---------|--------|
| Build succeeds, test passes | Proceed to the next workflow step |
| Build fails | Report build errors; fix before retrying |
| Test fails | Report test failure details; investigate and fix |

#### 5.5. Native Test Parallelism (Folder Mode Only)

Folder-mode improve runs **all** the test methods in a project once at the end of the per-project sub-agent. When that suite contains many tests, enable framework-native parallelism to cut wall-clock time. Flags by framework:

| Framework | Flag | Notes |
|-----------|------|-------|
| .NET (xUnit) | `dotnet test --parallel` | Honors `xunit.runner.json#maxParallelThreads`. Class-level parallelism is the safe default. |
| .NET (MSTest) | `dotnet test --parallel` | Respects `[assembly: Parallelize(Workers = 0, Scope = ExecutionScope.ClassLevel)]`. Method-level requires explicit thread-safety verification. |
| .NET (NUnit) | `dotnet test -- NUnit.NumberOfTestWorkers=N` | Run-settings file equivalent: `<NumberOfTestWorkers>` in `.runsettings`. |
| Python (pytest) | `pytest -n auto` | Requires `pytest-xdist`. Each worker is a separate process → module fixtures are per-worker. |
| TypeScript (Vitest) | `vitest run --threads` (default in v0.30+) | Tune with `--maxConcurrency=N`. |
| TypeScript (Jest) | `jest --maxWorkers=auto` | Default behavior on most modern CI. |
| Go | `go test -p N ./...` | Parallel across packages by default; `t.Parallel()` opts each test in. |

**Single-file flow note.** Single-file `End2End` runs only one test method (`--filter`), so this section does not apply. Folder mode is the only consumer.

**Safety rule.** Do NOT introduce `[Parallelize(Scope = MethodLevel)]` or remove `[DoNotParallelize]` annotations as part of a hardening edit unless the audit explicitly flagged a class as thread-safe — see the stability-by-design recipe in [`hardening-recipes`](../hardening-recipes/SKILL.md). This section is about **exploiting parallelism that's already safe**, not adding new parallel annotations.

**Where to add the flag.** Inside the per-project sub-agent's build/test invocation in folder mode (the one build per project, run target tests once step). Do NOT add it to the single-test post-edit verification — a single `--filter` run does not benefit and the extra flag adds noise to error reporting.
