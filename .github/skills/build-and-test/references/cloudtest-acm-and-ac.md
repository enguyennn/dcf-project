# Local Build and Test for CloudTest in ACM and AC Repositories

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

### 2. Build the test project

Build the project using quickbuild. If successful, report success and stop (do not check logs).

**Command:**
```powershell
quickbuild -retail -amd64 -notest
```

**Execution Context:**
- Navigate to the test project directory containing the test you are working on
- Execute after successful repository initialization
- Must run in the same terminal session as initialization

**Troubleshooting:**
- If you see:
  ```
  Could not find MSBuild.exe on the PATH
  ```

  This usually means initialization and build were run in **different terminal sessions**

  **Fix: run both commands in the same session**, for example:

  ```powershell
  cd <repo-root-directory>; .\init.ps1; cd <test-project-directory>; quickbuild -retail -amd64 -notest
  ```

**Success Criteria:**
- Build completes without errors

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

#### 3.3 Determine Project Type

Determine whether the test project is **SDK-style** or **CoreXT-style** by inspecting the `.csproj` file in the test project directory.

* **SDK-style** Project

Classify as **SDK-style** if the `<Project>` element contains an `Sdk` attribute:

```xml
<Project Sdk="...">
```

**Common examples:**

```xml
<Project Sdk="Microsoft.NET.Sdk">
<Project Sdk="Microsoft.NET.Sdk.Web">
<Project Sdk="MSTest.Sdk">
```

* **CoreXT-style** Project

Classify as **CoreXT-style** if the `<Project>` element does NOT contain `Sdk`, and instead looks like:

```xml
<Project DefaultTargets="Build" ToolsVersion="Current" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
```

* Validation / Edge Cases
  * If `<Project Sdk="...">` exists → **Always treat as SDK-style**
  * If `Sdk` attribute is missing → **Treat as CoreXT-style**

If the project structure is unclear or does not match either pattern:
→ **Stop and report unsupported project type**

#### 3.4 Execute Tests (Choose ONE path)

⚠️ These are **mutually exclusive paths** — execute only one based on project type.

Before executing:

* Extract from `<Execution>` in TestJob:
  * `Path` → full relative path to test DLL
  * `Args` → execution arguments
* Extract **DLL file name** from `Path`
* Construct `<Arguments>` strictly using:
  👉 **Argument Resolution Rules (see section below)**

**Argument Integrity (Critical)**
- `<Arguments>` must be derived **only** from `Args`
- **Do NOT add, infer, or inject any additional arguments**

Specifically:

- ❌ Do NOT add additional `/Tests:<...>` (even if a specific test was fixed)
- ❌ Do NOT add filters, traits, or any new parameters
- ❌ Do NOT modify existing argument values

✅ The final command must reflect **exactly and only** what is defined in `Args` after applying the Argument Resolution Rules.

#### Option A — CoreXT-style Project

1. Navigate to `<test-project-directory>\obj\amd64`:

```powershell
cd <test-project-directory>\obj\amd64
```

2. Run using extracted DLL name:

```powershell
vstest.console.exe <test-dll-name> <Arguments> /Logger:trx
```

#### Option B — SDK-style Project

##### Step B1 — Resolve Absolute DLL Path

1. Read `Path` from `<Execution>`:

Example:

```
Path="[WorkingDirectory]\<relative-path>\<test-dll-name>.dll"
```

This indicates:

* DLL exists under `[WorkingDirectory]\<relative-path>`

2. Locate corresponding `<BuildFiles><Copy>` section:

Example:

```xml
<Copy Src="[BuildRoot]\[BuildType]-[BuildArch]-unittest\<source-path>\*" 
      Dest="[WorkingDirectory]\<relative-path>" />
```

This means:

* Files in `[WorkingDirectory]\<relative-path>` are copied from:

  ```
  [BuildRoot]\[BuildType]-[BuildArch]-unittest\<source-path>\
  ```

3. Replace placeholders:

* `[BuildRoot]` → `<repo-root>\out`
* `[BuildType]` → `retail`
* `[BuildArch]` → `amd64`

4. Final absolute path of the directory containing dll:

For example:
```powershell
<repo-root>\out\retail-amd64-unittest\<source-path>
```

##### Step B2 — Navigate to DLL Directory

Navigate to the directory containing dll.

```powershell
cd <directory-containing-dll>
```

##### Step B3 — Execute Tests

```powershell
dotnet test <test-dll-name> <Arguments> --logger "trx"
```

**Note:**

If error occurs:

```
Specifying dlls or executables for 'dotnet test' should be via '--test-modules'
```

Then:

1. Open `global.json` at repo root
2. Temporarily comment out:
```
"runner": "Microsoft.Testing.Platform"
```
3. Re-run the test command
4. Restore `global.json` after execution

## Argument Resolution Rules

Use this section when constructing `<Arguments>`.

### TaefAdapter Path

If Args contains:

```
/TestAdapterPath:<path>
```

Find using:

```powershell
where.exe /R <drive-root> TE.TestAdapter.dll
```

Select the path that meets **all** of the following criteria:

- Includes `Taef.TestAdapter.<version>` in the directory path
- Does **not** include `.pkgref`
- Points to a valid `TE.TestAdapter.dll` file

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

When using `/TestCaseFilter`, parentheses are not supported in PowerShell argument parsing and must be replaced with quotes.

❌

```
/TestCaseFilter:(TestCategory=CloudTest)
```

✅

```
/TestCaseFilter:"TestCategory=CloudTest"
```

## Troubleshooting

| Error                                                                | Solution |
|----------------------------------------------------------------------|----------|
| `The term 'vstest.console.exe' is not recognized` | Ask the user to open a Visual Studio Developer Command Prompt and run `where vstest.console.exe` to locate the executable. Then instruct the user to add the returned directory path to the System `Path` environment variable and restart VS Code. |
| Tests fail to start                                                  | Verify the test DLL path is correct and ensure the DLL exists in the build output directory. |

Example vstest.console.exe path:
```powershell
C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\TestWindow\vstest.console.exe
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
- **Use Correct Flags**: Always use `-retail -amd64 -notest` flags for consistent builds

## Failure Analysis

When the build or test execution fails, analyze the build or test log files and classify the failure.

**Log Files to Review:**

| Log File | Purpose |
|----------|---------|
| `QuickBuild.log` | Build output and errors |
| `QLogs/` | Additional diagnostic logs |
| `<current-dll-directory>/TestResults/*.trx` | Test execution logs |

**Failure Classification:**

| Failure Type | Characteristics | Action |
|--------------|-----------------|--------|
| **Caused by your changes** | Syntax errors, missing dependencies, incorrect logic introduced in the fix | Go to the next step: "Iterative Fix Workflow"  |
| **Unrelated to your changes** | Errors in unrelated parts of the project, pre-existing issues | Report the error and stop; Provide analysis and suggestions (see **Infrastructure Issue Suggestions**). Do NOT modify unrelated code |

**Examples of Change-Related Failures:**
- Compilation errors in files you modified
- Test failures directly caused by your code changes
- Missing using statements or imports you should have added
- Type mismatches from your modifications

**Examples of Unrelated Failures:**
- Build errors in modules you didn't touch
- Test failures in tests you didn't modify
- Infrastructure or environment issues (e.g., missing dependencies)
- Pre-existing flaky tests

**Iterative Fix Workflow**

When failures are caused by your changes, follow this iterative process:

```
1. Review failure logs (QuickBuild.log, TestResults\*.trx)
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

1. Clear summary of the failure
2. Likely root cause
3. Concrete remediation steps

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

- Initialization succeeds
- Build completes without errors
- All relevant tests pass
