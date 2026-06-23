---
name: test-file-discovery
description: |
  Test-file discovery and input classification skill. Use when the Folder prompt receives a `test path` input and must decide whether it is a single test file, a folder of test files, a production file, an empty/no-tests folder, or a non-existent path. Returns a classification verdict plus (for the folder case) the enumerated test-file list.
---

# Test File Discovery and Input Classification

This skill turns a free-form `test path` input into one of five classifications and, when the input is a usable folder, the list of test files to fan out across. Classification is performed BEFORE any audit, improve, or submit work runs so the orchestrator can short-circuit on ambiguous or off-scope input.

## Inputs

- `test path` (string, required) -- absolute path, repo-relative path, or workspace-relative path. May be a file or a directory.
- `max files` (integer, optional, default 30, hard ceiling 100) -- fan-out cap. Above the ceiling the skill returns `too-large` and refuses to enumerate.

## Output

Always emit a single classification block. The orchestrator dispatches on the `Classification:` line; everything below is human-readable detail for the chat surface.

```
Classification: <single-test-file | folder-of-tests | folder-empty | folder-no-test-files | non-existent-path | production-file | ambiguous-too-large>
Resolved path: <absolute path>
Test framework: <MSTest | xUnit | NUnit | pytest | jest | vitest | mocha | go-test | mixed | unknown | n/a>
File count: <N | n/a>
Files (when folder-of-tests, capped at max files):
  - <relative path 1>
  - <relative path 2>
  ...
Reason: <short human-readable explanation>
Next action: <route-to-single-file | fan-out | ask-clarification | abort>
```

## Classification Decision Table

Run the checks **in order**; the first match wins.

| Check (in order) | Verdict | Next action |
|------------------|---------|-------------|
| Path does not exist on disk | `non-existent-path` | `ask-clarification` |
| Path is a file AND matches a test glob (see below) | `single-test-file` | `route-to-single-file` |
| Path is a file AND does NOT match a test glob | `production-file` | `ask-clarification` |
| Path is a directory AND has zero files under it (recursively) | `folder-empty` | `ask-clarification` |
| Path is a directory AND has files but zero match any test glob | `folder-no-test-files` | `ask-clarification` |
| Path is a directory AND matching files exceed `max files` hard ceiling (100) | `ambiguous-too-large` | `ask-clarification` |
| Path is a directory AND has at least one test glob match (and total ≤ ceiling) | `folder-of-tests` | `fan-out` |

When `folder-of-tests` is returned but the count exceeds `max files` (default 30) yet is still under the ceiling (100), include the count and ask the user to either confirm or set `max files` to the actual count. Do **not** silently truncate.

## Test-File Globs (by framework)

Use the table below to determine whether a single file is a test file and to enumerate test files inside a folder. A directory is a "test folder" if at least one file under it matches any row.

| Framework | File globs |
|-----------|------------|
| .NET (MSTest / xUnit / NUnit) | `**/*Tests.cs`, `**/*Test.cs`, `**/Tests/**/*.cs`, `**/test/**/*.cs` |
| pytest | `**/test_*.py`, `**/*_test.py`, `**/tests/**/*.py` |
| Jest / Vitest / Mocha (TS/JS) | `**/*.test.{ts,tsx,js,jsx,mjs,cjs}`, `**/*.spec.{ts,tsx,js,jsx,mjs,cjs}`, `**/__tests__/**/*.{ts,tsx,js,jsx}` |
| Go | `**/*_test.go` |

If a folder contains test files from multiple frameworks, emit `Test framework: mixed` and include the per-framework counts in `Reason:`.

## Framework Detection (single file)

When `single-test-file` is matched, set `Test framework:` from the file extension and content:

| Extension | Content signal | Framework |
|-----------|----------------|-----------|
| `.cs` | `[TestClass]` / `using Microsoft.VisualStudio.TestTools.UnitTesting` | MSTest |
| `.cs` | `[Fact]` / `using Xunit` | xUnit |
| `.cs` | `[Test]` / `using NUnit.Framework` | NUnit |
| `.py` | `import pytest` / `def test_` | pytest |
| `.ts` / `.tsx` / `.js` / `.jsx` | `from "vitest"` or `import { test } from "vitest"` | vitest |
| `.ts` / `.tsx` / `.js` / `.jsx` | `from "@jest/globals"` or `describe(` + jest config in repo | jest |
| `.ts` / `.tsx` / `.js` / `.jsx` | `from "mocha"` / `import { describe } from "mocha"` | mocha |
| `.go` | `func Test` and `import "testing"` | go-test |

If the file matches a test glob but no content signal, emit `Test framework: unknown` and continue (it is still a test file).

## Ambiguity Messages (when `Next action: ask-clarification`)

Use the templates below verbatim. Replace `<…>` tokens with the resolved values. **Do not** ask the user to provide an example; just list what you saw and what you need.

### `non-existent-path`

```
Test Hardening -- input not found.

The path you provided does not exist:
  <resolved path>

Please re-run with a valid file or folder path. Examples of what works:
  - A test method, class, or file (single-file mode)
  - A folder containing test files (folder mode)
```

### `production-file`

```
Test Hardening -- this looks like a production file.

Path:           <resolved path>
Why we think so: no test-file glob matched (checked: <list of globs that ran>).

This scenario hardens existing tests; it never edits production code.

Did you mean one of these?
  - The test file that exercises <basename>? If so, re-run with the test file path or its method name.
  - Hardening the folder that contains the tests for <basename>? If so, re-run with the test folder path.
  - Generating new tests for <basename>? That belongs to `unit-test-generation`, not this scenario.
```

### `folder-empty`

```
Test Hardening -- folder is empty.

Path: <resolved path>
File count: 0

Re-run with a folder that contains test files, or a single test file.
```

### `folder-no-test-files`

```
Test Hardening -- folder has files but no recognized test files.

Path:           <resolved path>
Files scanned:  <N>
Globs checked:  <list of globs that ran>
Frameworks:     MSTest, xUnit, NUnit, pytest, jest, vitest, mocha, go-test

If your project uses a non-standard test-file naming convention, either:
  - Rename the test files to match one of the supported globs, or
  - Re-run pointing at a single test file (the file globs above are documentation for what the discovery scans).
```

### `ambiguous-too-large`

```
Test Hardening -- folder has too many test files for one run.

Path:        <resolved path>
File count:  <N> (hard ceiling: 100)

Re-run with a narrower folder (e.g., one subdirectory at a time) or split the run.
A single PR for >100 files is not reviewable.
```

### `folder-of-tests` ABOVE `max files` (soft cap)

```
Test Hardening -- folder has more test files than the default cap.

Path:               <resolved path>
File count:         <N>
Default cap:        <max files> (currently <value>)

Re-run with `max files = <N>` to process all of them, or point at a smaller folder.
```

## Steps

### 1. Resolve the Path

Convert the input to an absolute path. Pass through `git rev-parse --show-toplevel` to anchor repo-relative inputs. If resolution fails, emit `non-existent-path`.

**Command:**
```powershell
$repoRoot   = git rev-parse --show-toplevel 2>$null
$resolved   = if (Test-Path $TestPath) { (Resolve-Path $TestPath).Path } `
              elseif ($repoRoot -and (Test-Path (Join-Path $repoRoot $TestPath))) { (Resolve-Path (Join-Path $repoRoot $TestPath)).Path } `
              else { $null }
```

### 2. Classify File vs Directory

Use `Test-Path -PathType Leaf` for files and `Test-Path -PathType Container` for directories. If neither, emit `non-existent-path`.

### 3. Apply the Decision Table

Run the rows in the table above in order. Stop at the first match.

### 4. For Folders, Enumerate Test Files

```powershell
$patterns = @(
  "*Tests.cs", "*Test.cs",
  "test_*.py", "*_test.py",
  "*.test.ts", "*.test.tsx", "*.test.js", "*.test.jsx", "*.test.mjs", "*.test.cjs",
  "*.spec.ts", "*.spec.tsx", "*.spec.js", "*.spec.jsx", "*.spec.mjs", "*.spec.cjs",
  "*_test.go"
)
$files = $patterns | ForEach-Object {
  Get-ChildItem -Path $resolved -Recurse -Filter $_ -File -ErrorAction SilentlyContinue
} | Sort-Object FullName -Unique

# Also include Jest-style __tests__ and pytest-style tests/ trees
$dirHits = Get-ChildItem -Path $resolved -Recurse -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -in @("__tests__", "tests", "Tests", "test") } |
  ForEach-Object { Get-ChildItem -Path $_.FullName -Recurse -File -Include *.ts,*.tsx,*.js,*.jsx,*.py,*.cs }

$files = ($files + $dirHits) | Sort-Object FullName -Unique
```

### 5. Emit the Classification Block

Print the block defined in **Output** above. The orchestrator dispatches on the first line.

## Rules

- **Classification runs before any audit work.** Never invoke the Audit prompt against an unclassified path.
- **First-match wins** in the decision table. Do not invent additional verdicts.
- **Never silently truncate** the file list. If the count exceeds the soft cap, return the soft-cap message and stop.
- **Always include the resolved absolute path** in the output so the user can verify what was actually scanned.
- **No external network calls.** Discovery uses only the local filesystem.
