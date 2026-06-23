# Local Build and Test for CloudTest in Powerbi Repository

This guide describes how to build and execute CloudTest tests locally in the PowerBI repository.

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
Microsoft.PowerBI.MetadataService.CT -> Q:\Repos\Shared.obj.x64Debug\sql\cloudbi\as\test\componenttests\powerbimetadataservice\microsoft.powerbi.metadataservice.ct.csproj\Microsoft.PowerBI.MetadataService.CT.dll
```

### 3. Run the Tests

Follow the steps below strictly in order to execute tests.

- Use commands exactly as specified
- Do NOT add, remove, or modify arguments
- If execution fails, refer to **Failure Analysis**

#### 3.1 Locate TestJob from XML

1. From the bug report URL, extract **Module Id** in Repro Steps.

   Example:

   ```
   <path>\testgroup.<...>.xml_<TestJob Name>
   ```

2. Identify:

   * XML file → `<testgroup...>.xml`
   * TestJob Name → the portion after `_`

3. Search repo for the XML file

   * If duplicates exist → select the one containing the correct TestJob

#### 3.2 Validate Execution Type

Check `<Execution Type="...">`:

* If `MsTest` → continue
* Otherwise → **Stop here and report not supported**, do not continue the following steps.

#### 3.3 Execute Tests

1. From the `<Execution>` element in TestJob:
   * Extract the value of `Args`
   * Construct `<Arguments>` strictly using:
  👉 **Argument Resolution Rules (see section below)**

**Argument Integrity (Critical)**
- `<Arguments>` must be derived **only** from `Args`
- **Do NOT add, infer, or inject any additional arguments**

Specifically:

- ❌ Do NOT add additional `/Tests:<...>` or `--filter <testName>` (even if a specific test was fixed)
- ❌ Do NOT add filters, traits, or any new parameters
- ❌ Do NOT modify existing argument values

✅ The final command must reflect **exactly and only** what is defined in `Args` after applying the Argument Resolution Rules.

2. After the build succeeds, search the build log to find the line "ProjectName -> <path-to-test-project-dll>". Run the compiled test project assembly using `vstest.console.exe <path-to-test-project-dll> <Arguments> /Logger:trx`.

**Command:**
```powershell
vstest.console.exe <path-to-test-project-dll> <Arguments> /Logger:trx
```

Example command:
```powershell
vstest.console.exe Q:\Repos\Shared.obj.x64Debug\sql\cloudbi\as\test\componenttests\powerbimetadataservice\microsoft.powerbi.metadataservice.ct.csproj\Microsoft.PowerBI.MetadataService.CT.dll /platform:x64 /InIsolation /TestCaseFilter:"TestCategory=CmkTenantKeysControllerTests" /settings:Q:\Repos\Shared\testsrc\BI\CloudTest\setup\coverage.runsettings /Logger:trx
```

**Expected Result**

All tests run successfully without failures.

## Argument Resolution Rules

Use this section when constructing `<Arguments>`.

### RunSettings File

If Args contains:

```
/settings:<file>
```

- Locate the corresponding `.runsettings` file within the current repository
- Replace `<file>` with its **absolute path**

### Other Arguments

- Use all other arguments exactly as provided
- Do **not** modify, reorder, or add any additional arguments

**Important: PowerShell Quoting**

When using `/TestCaseFilter`, parentheses and encoded quotes (`&quot;`) are not supported in PowerShell argument parsing and must be replaced with quotes.

❌

```
/TestCaseFilter:(TestCategory=CloudTest)
```

```
/TestCaseFilter:&quot;TestCategory=CloudTest&quot;
```

✅

```
/TestCaseFilter:"TestCategory=CloudTest"
```

## Execution Rules

- Build and test must run in the same terminal session. Do not open background terminals.
- Always run `msbuild` before `vstest.console.exe`.
- Use the **exact** `msbuild` command as provided; do **not** add extra output processing (for example, `Select-Object`)
- Do not run tests against stale binaries.
- Do **not** review logs until the build or test execution has fully completed. Wait for the command to finish before analyzing logs.
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

When the build or test execution fails, analyze:
- Build logs in the terminal
- Test execution logs in `TestResults/*.trx`
Then classify the failure based on the root cause.

**Failure Classification:**

| Failure Type | Characteristics | Action |
|--------------|-----------------|--------|
| **Caused by your changes** | Syntax errors, missing dependencies, incorrect logic introduced in the fix | Proceed to the "Iterative Fix Workflow"  |
| **Unrelated to your changes** | Errors in unrelated parts of the project, pre-existing issues | Report the error and stop; Provide analysis and suggestions (see **Infrastructure Issue Suggestions**). Do NOT modify unrelated code |

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
1. Review failure logs (terminal or TestResults\*.trx)
        ↓
2. Identify root cause
        ↓
3. Apply targeted code fix
        ↓
4. Re-run the workflow:
   - Rebuild the test project
   - Re-run the tests
        ↓
5. If still failing → Return to step 1
   If successful → report success
```

## Infrastructure Issue Suggestions

Apply this section only when the failure is NOT caused by your changes.

### Required Output

Provide all of the following:

1. **Failure Summary** — concise description of what failed
2. **Likely Root Cause** — why it happened
3. **Concrete Remediation Steps** — actionable next steps

### Common Scenarios and Guidance

#### 1. Environment / Setup Issues (Missing Local Dependencies)

Examples:
 - Storage emulator (e.g., Azurite)
 - Object store or other local services
 - Required background processes

Action:
- Identify the missing dependency
- Instruct the user to install (if needed) and start the required services
- Include any necessary configuration details (if applicable)
- Advise re-running the workflow after setup is complete

If local reproduction is unreliable:
  - Recommend validating the fix via PR build pipeline
  - Or suggest using the user’s standard local validation workflow (e.g., running tests in other tools or platforms, ensuring dependent services are running before execution)

#### 2. External or Pipeline-Dependent Components

Examples:
- Services only available in CI/CD
- Cloud resources not accessible locally
- Integration dependencies

Action:
- Clearly explain why the issue cannot be reproduced locally
- Recommend validation through:
  - PR build pipeline
  - Integration or staging environments

### Important Rules

- Do NOT modify code for infrastructure-related failures
- Do NOT attempt speculative fixes
- Focus on diagnosis and clear guidance only

## Success Criteria

The execution is successful when:

- `msbuild` completes without errors
- `vstest.console.exe` runs successfully
- All relevant tests pass
