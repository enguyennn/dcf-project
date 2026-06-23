# Local Build and Test for QTest in ACM and AC Repositories

This guide describes how to initialize the repository environment and run the build and test workflow locally in Azure-Compute and Azure-Compute-Move repositories.

## Steps

### 1. Repository Initialization

Initialize the repository environment before building or running tests.

**Command:**
```powershell
.\init.ps1
```

**Execution Context:**
- Navigate to the root directory of the repository
- Execute in a `pwsh` (PowerShell Core) terminal
- Must complete successfully before proceeding to build

**Troubleshooting:**

| Error | Solution |
|-------|----------|
| "File init.ps1 cannot be loaded because running scripts is disabled on this system" | Run: `powershell -ExecutionPolicy Bypass -File .\init.ps1` |
| Script not found | Verify you are in the repository root directory |
| Permission denied | Run PowerShell as Administrator |

**Failure Behavior:**
- If initialization fails, report the failure and stop the process
- Do not proceed to build without successful initialization

### 2. Build and Test Execution

Build the project and run the full test suite using QuickBuild. If successful, report success and stop (do not check test logs).

**Command:**
```powershell
quickbuild -retail -amd64
```

**Execution Context:**
- Navigate to the test project directory containing the test you are working on
- Execute after successful repository initialization
- Must run in the same terminal session as initialization

**Success Criteria:**
- Build completes without errors

### 3. Failure Analysis

When build or tests fail, analyze logs to determine the cause.

**Log Files to Review:**

| Log File | Purpose |
|----------|---------|
| `QuickBuild.log` | Build output and errors |
| `QTestLogs/` | Test execution logs |
| `QLogs/` | Additional diagnostic logs |

**Failure Classification:**

| Failure Type | Characteristics | Action |
|--------------|-----------------|--------|
| **Caused by your changes** | Syntax errors, missing dependencies, incorrect logic introduced in the fix | Go to the next step: "Iterative Fix Workflow"  |
| **Unrelated to your changes** | Errors in unrelated parts of the project, pre-existing issues | Report the error and stop; do not modify unrelated code |

**Examples of Change-Related Failures:**
- Compilation errors in files you modified
- Test failures directly caused by your code changes
- Missing using statements or imports you should have added
- Type mismatches from your modifications

**Examples of Unrelated Failures:**
- Build errors in modules you didn't touch
- Test failures in tests you didn't modify
- Infrastructure or environment issues
- Pre-existing flaky tests

### 4. Iterative Fix Workflow

When failures are caused by your changes, follow this iterative process:

```
┌─────────────────────────────────────────────────────────┐
│  1. Review failure logs (QuickBuild.log, QTestLogs)     │
│                          ↓                              |
│  2. Identify root cause of failure                      │
│                          ↓                              │
│  3. Make targeted code adjustments                      │
│                          ↓                              │
│  4. Re-run: quickbuild -retail -amd64                   │
│                          ↓                              │
│  5. If still failing → Return to step 1                 │
│     If passing → Report success                         │
└─────────────────────────────────────────────────────────┘
```

## Rules

### Session Management
- **Single Terminal Session**: All steps (init, build, test) must execute in the same terminal session
- **No Background Sessions**: Do not open additional terminals or background sessions
- **Sequential Execution**: Complete each step before proceeding to the next

### Failure Handling
- **Report and Stop on Unrelated Failures**: Do not attempt to fix unrelated code
- **Iterate on Related Failures**: Continue adjusting until your changes work
- **Preserve Existing Functionality**: Your changes should not break unrelated tests

### Build Verification
- **Always Initialize First**: Never skip the `Repository Initialization` step
- **Use Correct Directory**: Run QuickBuild from the test project directory
- **Use Correct Flags**: Always use `-retail -amd64` flags for consistent builds

## Common Scenarios

### Scenario 1: First-Time Build

```powershell
# 1. Navigate to repository root
cd $env:REPOROOT

# 2. Initialize repository
.\init.ps1

# 3. Navigate to test project
cd src\Services\MyService\Tests

# 4. Build and run tests
quickbuild -retail -amd64
```

### Scenario 2: Script Execution Policy Error

```powershell
# If init.ps1 fails due to execution policy
powershell -ExecutionPolicy Bypass -File .\init.ps1

# Then continue with build
cd src\Services\MyService\Tests
quickbuild -retail -amd64
```

### Scenario 3: Iterating on Failures

```powershell
# After fixing code based on failure analysis
# Re-run from test project directory
quickbuild -retail -amd64

# If still failing, review logs again
Get-Content QuickBuild.log | Select-String "error"
```

## Output Expectations

### Success Output
```
Build succeeded.
All tests passed.

✅ Build and test execution completed successfully.
```

### Failure Output
```
Build failed. See QuickBuild.log for details.

Analysis:
- Failure Type: [Caused by changes | Unrelated]
- Root Cause: [Description of the issue]
- Recommended Action: [Next steps]
```
