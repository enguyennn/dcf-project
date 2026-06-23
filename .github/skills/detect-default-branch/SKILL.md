---
name: detect-default-branch
description: |
  Git utility skill for detecting the default branch of a repository. Automatically activated when users request any of these tasks:
  - Determine the default branch ("what is the default branch", "find default branch", "detect main branch")
  - Check if the default branch is main or master ("is it main or master", "which branch is default")
  - Get the primary branch name before performing branch operations
---

# Detect Default Branch Name

This skill determines the default branch of the current repository. Common values are `main` or `master`.

## Steps

### 1. Query the Remote for the Default Branch

Ask the remote which branch HEAD points to.

**Command:**
```powershell
git remote show origin | Select-String "HEAD branch"
```

**Execution Context:**
- Navigate to the root directory of the repository
- Execute in a `pwsh` (PowerShell Core) terminal

**Expected Output:**
```
  HEAD branch: master
```

**Parsing:**
- Extract the branch name from the output (the value after `HEAD branch:`).
- Common values: `main`, `master`.

**Troubleshooting:**

| Error | Solution |
|-------|----------|
| "fatal: 'origin' does not appear to be a git repository" | No remote named `origin` is configured; check remotes with `git remote -v` |
| Network timeout or authentication failure | The command requires network access to the remote; fall through to Step 2 for an offline alternative |
| "not a git repository" | Verify you are inside the repository root directory |

### 2. Offline Fallback via Symbolic Ref

If Step 1 fails (e.g., no network access), use the locally cached default branch reference.

**Command:**
```powershell
git symbolic-ref refs/remotes/origin/HEAD
```

**Expected Output:**
```
refs/remotes/origin/master
```

**Parsing:**
- Extract the branch name from the last path segment (e.g., `master` from `refs/remotes/origin/master`).

**Troubleshooting:**

| Error | Solution |
|-------|----------|
| "fatal: ref refs/remotes/origin/HEAD is not a symbolic ref" | The symbolic ref has not been set locally; run `git remote set-head origin --auto` first (requires network), then retry |
| "fatal: No such ref" | Run `git fetch origin` followed by `git remote set-head origin --auto`, then retry |

### 3. Last-Resort Fallback via Local Branch Heuristic

If both Step 1 and Step 2 fail, check for the existence of common default branch names locally.

**Command:**
```powershell
$candidates = @("main", "master")
foreach ($branch in $candidates) {
    $exists = git rev-parse --verify "refs/heads/$branch" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Output "Default branch (heuristic): $branch"
        break
    }
}
```

**Expected Output:**
```
Default branch (heuristic): master
```
