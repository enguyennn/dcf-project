# Local Build and Test for QTest in Powerbi Repository

This guide describes how to build and execute QTest tests locally in the PowerBI repository.

## Steps

### 1. Navigate to the Test Project

Open a PowerShell (`pwsh`) terminal and navigate to the directory containing the test project you want to build.

Example:
```powershell
cd <repo-root>/<test-project-directory>
```

### 2. Build the Test Project

Run `msbuild` to build the project.

**Command:**
```powershell
msbuild
```

**Expected Result**

The build completes without errors and produces a test DLL.

Example output path:
```powershell
Microsoft.ASExternalServicesWatchdog.CT -> Q:\Repos\Shared.obj.x64Debug\sql\cloudbi\as\test\componenttests\asexternalserviceswatchdog\microsoft.asexternalserviceswatchdog.ct.csproj\Microsoft.SqlServer.Cloud.Analysis.ASExternalServicesWatchdog.CT.dll
```

### 3. Run the Tests

After the build succeeds, search the build log to find the line "ProjectName -> <path-to-test-project-dll>". Run the compiled test project assembly using `vstest.console.exe <path-to-test-project-dll>`.

**Command:**
```powershell
vstest.console.exe <path-to-test-project-dll>
```

Example command:
```powershell
vstest.console.exe Q:\Repos\Shared.obj.x64Debug\sql\cloudbi\as\test\componenttests\asexternalserviceswatchdog\microsoft.asexternalserviceswatchdog.ct.csproj\Microsoft.SqlServer.Cloud.Analysis.ASExternalServicesWatchdog.CT.dll
```

**Expected Result**

All tests run successfully without failures.

## Execution Rules

- Build and test must run in the same terminal session. Do not open background terminals.
- Always run `msbuild` before `vstest.console.exe`.
- Use the **exact** `msbuild` command as provided; do **not** add extra output processing (for example, `Select-Object`)
- Run **all tests** using `vstest.console.exe` against the test project DLL. Do **not** run individual tests using the `/Tests:` filter.
- Do not run tests against stale binaries.
- Do not modify unrelated projects when fixing failures.
- Stop execution if failures are unrelated to your changes.

## Troubleshooting

| Error                                                                | Solution |
|----------------------------------------------------------------------|----------|
| `The term 'msbuild' is not recognized` **or** `The term 'vstest.console.exe' is not recognized` | Ask the user to open a Visual Studio Developer Command Prompt and run `where <tool>` (for example, `where msbuild` or `where vstest.console.exe`) to locate the executable. Then instruct the user to add the returned directory path to the System `Path` environment variable and restart VS Code. |
| Tests fail to start                                                  | Verify the test DLL path is correct and ensure the DLL exists in the build output directory. |

Example MSBuild path:
```powershell
C:\Program Files\Microsoft Visual Studio\18\Enterprise\MSBuild\Current\Bin\amd64
```

## Failure Analysis

When the build or test execution fails, analyze the terminal logs and classify the failure.

**Failure Classification:**

| Failure Type | Characteristics | Action |
|--------------|-----------------|--------|
| **Caused by your changes** | Syntax errors, missing dependencies, incorrect logic introduced in the fix | Proceed to the "Iterative Fix Workflow"  |
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

**Iterative Fix Workflow**

When failures are caused by your changes, follow this iterative process:

```
1. Review terminal logs
        ↓
2. Identify root cause
        ↓
3. Apply targeted code fix
        ↓
4. Re-run the workflow:
   - Run `msbuild`
   - Then run `vstest.console.exe <path-to-test-project-dll>`
        ↓
5. If still failing → Return to step 1
   If successful → report success
```

## Success Criteria

The execution is successful when:

- `msbuild` completes without errors
- `vstest.console.exe` runs successfully
- All relevant tests pass
