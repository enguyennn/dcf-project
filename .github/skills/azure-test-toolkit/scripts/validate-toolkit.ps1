<#
.SYNOPSIS
    Validates Azure Test Platform toolkit files for correctness.

.DESCRIPTION
    This script validates that provider and test type toolkit files under
    skills/azure-test-toolkit/references/ follow the Azure Test Platform
    contract defined in skills/azure-test-toolkit/SKILL.md.

.PARAMETER TemplatesPath
    Path to the references directory. Defaults to the skill's references/ folder.

.PARAMETER ProviderName
    Optional. Validate only a specific provider. If omitted, validates all providers.

.EXAMPLE
    .\validate-toolkit.ps1
    Validates all providers under references/

.EXAMPLE
    .\validate-toolkit.ps1 -ProviderName "cirrus"
    Validates only the cirrus provider
#>

param(
    [string]$TemplatesPath,
    [string]$ProviderName
)

$ErrorActionPreference = "Continue"
$script:allPassed = $true
$script:errorCount = 0
$script:warnCount = 0

# --- Read primitives from config (single source of truth) ---
function Get-PrimitivesFromConfig {
    param([string]$ReferencesPath)

    # Walk up from references/ to find config/octane.yaml
    $candidatePaths = @(
        (Join-Path $ReferencesPath ".." ".." ".." "config" "octane.yaml"),
        (Join-Path $ReferencesPath ".." ".." ".." ".." "config" "octane.yaml")
    )
    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            $configPath = (Resolve-Path $candidate).Path
            $content = Get-Content $configPath -Raw

            # Parse primitives list from YAML (lightweight — no YAML module dependency)
            $primitives = @()
            $inPrimitives = $false
            foreach ($line in ($content -split "`n")) {
                if ($line -match '^\s+primitives:\s*$') {
                    $inPrimitives = $true
                    continue
                }
                if ($inPrimitives) {
                    if ($line -match '^\s+-\s+(.+)$') {
                        $primitives += $Matches[1].Trim()
                    } else {
                        break
                    }
                }
            }
            if ($primitives.Count -gt 0) {
                Write-Host "  Primitives loaded from config: $($primitives -join ', ')" -ForegroundColor Gray
                return $primitives
            }
        }
    }

    # Fallback if config not found (should not happen in a well-formed repo)
    Write-Host "  [WARN] Could not read primitives from config/octane.yaml — using built-in defaults" -ForegroundColor Yellow
    $script:warnCount++
    return @("Observe", "Diagnose")
}

# Default path resolution
if (-not $TemplatesPath) {
    $scriptDir = $PSScriptRoot
    # Check if running from scripts/ inside the skill directory, scenario directory, or repo root
    $candidatePaths = @(
        (Join-Path $scriptDir ".." "references"),
        (Join-Path $scriptDir "skills" "azure-test-toolkit" "references"),
        (Join-Path $scriptDir ".." "artifacts" "scenarios" "azure-test-platform" "skills" "azure-test-toolkit" "references"),
        (Join-Path $scriptDir ".github" "skills" "azure-test-toolkit" "references")
    )
    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            $TemplatesPath = (Resolve-Path $candidate).Path
            break
        }
    }
    if (-not $TemplatesPath) {
        Write-Host "ERROR: Could not find references directory. Use -TemplatesPath to specify." -ForegroundColor Red
        exit 1
    }
}

# Load primitives from config (single source of truth)
$script:Primitives = Get-PrimitivesFromConfig -ReferencesPath $TemplatesPath

function Write-Result {
    param(
        [string]$Status,
        [string]$Message
    )
    switch ($Status) {
        "PASS" { Write-Host "  [OK] $Message" -ForegroundColor Green }
        "FAIL" {
            Write-Host "  [FAIL] $Message" -ForegroundColor Red
            $script:allPassed = $false
            $script:errorCount++
        }
        "WARN" {
            Write-Host "  [WARN] $Message" -ForegroundColor Yellow
            $script:warnCount++
        }
        "INFO" { Write-Host "  [INFO] $Message" -ForegroundColor Cyan }
    }
}

# --- Rule 1: All primitive sentinels present in every test type file ---
function Test-PrimitiveSentinels {
    param([string]$FilePath, [string]$FileName)

    $content = Get-Content $FilePath -Raw
    $requiredSentinels = $script:Primitives

    foreach ($sentinel in $requiredSentinels) {
        $pattern = "<!-- PRIMITIVE:$sentinel -->"
        if ($content -match [regex]::Escape($pattern)) {
            Write-Result "PASS" "$FileName — sentinel PRIMITIVE:$sentinel present"
        } else {
            Write-Result "FAIL" "$FileName — missing sentinel <!-- PRIMITIVE:$sentinel -->"
        }
    }
}

# --- Rule 2: Passthrough sections have Status + Reason, no execution fields ---
function Test-PassthroughSections {
    param([string]$FilePath, [string]$FileName)

    $content = Get-Content $FilePath -Raw
    $sentinels = $script:Primitives

    foreach ($sentinel in $sentinels) {
        $pattern = "<!-- PRIMITIVE:$sentinel -->"
        if ($content -notmatch [regex]::Escape($pattern)) {
            continue
        }

        # Extract section content between this sentinel and the next one (or EOF)
        $escapedPattern = [regex]::Escape($pattern)
        $nextSentinels = $sentinels | Where-Object { $_ -ne $sentinel } | ForEach-Object { [regex]::Escape("<!-- PRIMITIVE:$_ -->") }
        $nextPattern = ($nextSentinels -join "|") + "|$"
        
        if ($content -match "(?s)$escapedPattern(.*?)(?=$nextPattern)") {
            $section = $Matches[1]
        } else {
            continue
        }

        $isPassthrough = $section -match '\*\*Status:\*\*\s*passthrough'

        if ($isPassthrough) {
            # Must have Reason
            if ($section -match '\*\*Reason:\*\*') {
                Write-Result "PASS" "$FileName — $sentinel passthrough has Reason"
            } else {
                Write-Result "FAIL" "$FileName — $sentinel is passthrough but missing **Reason:**"
            }

            # Must NOT have Method, Auth, or other execution fields
            if ($section -match '\*\*(Method|Auth|MCP Server|Tool):\*\*') {
                $field = $Matches[1]
                Write-Result "FAIL" "$FileName — $sentinel is passthrough but has **${field}:** (not allowed)"
            }
        }
    }
}

# --- Rule 3: Non-passthrough sections have Method ---
function Test-ActiveSections {
    param([string]$FilePath, [string]$FileName)

    $content = Get-Content $FilePath -Raw
    $sentinels = $script:Primitives

    foreach ($sentinel in $sentinels) {
        $pattern = "<!-- PRIMITIVE:$sentinel -->"
        if ($content -notmatch [regex]::Escape($pattern)) {
            continue
        }

        $escapedPattern = [regex]::Escape($pattern)
        $nextSentinels = $sentinels | Where-Object { $_ -ne $sentinel } | ForEach-Object { [regex]::Escape("<!-- PRIMITIVE:$_ -->") }
        $nextPattern = ($nextSentinels -join "|") + "|$"

        if ($content -match "(?s)$escapedPattern(.*?)(?=$nextPattern)") {
            $section = $Matches[1]
        } else {
            continue
        }

        $isPassthrough = $section -match '\*\*Status:\*\*\s*passthrough'
        $isInherited = $section -match '\*\*Inherits:\*\*' -or $section -match '\*\*Extends:\*\*'

        if (-not $isPassthrough) {
            if ($isInherited -and $section -match '\*\*Method:\*\*') {
                Write-Result "FAIL" "$FileName — $sentinel has both Inherits/Extends and **Method:** (not allowed per SKILL.md)"
            } elseif ($section -match '\*\*Method:\*\*') {
                Write-Result "PASS" "$FileName — $sentinel has Method"
            } elseif ($isInherited) {
                Write-Result "PASS" "$FileName — $sentinel inherits/extends provider (Method inherited)"
            } else {
                Write-Result "FAIL" "$FileName — $sentinel is active but missing **Method:**"
            }
        }
    }
}

# --- Rule 4: Diagnose has Diagnostic Knowledge with Failure Patterns table ---
function Test-DiagnosticKnowledge {
    param([string]$FilePath, [string]$FileName)

    $content = Get-Content $FilePath -Raw

    if ($content -notmatch '<!-- PRIMITIVE:Diagnose -->') {
        return
    }

    # Extract Diagnose section
    if ($content -match '(?s)<!-- PRIMITIVE:Diagnose -->(.*?)(?=<!-- PRIMITIVE:|$)') {
        $diagnoseSection = $Matches[1]
    } else {
        Write-Result "FAIL" "$FileName — could not extract Diagnose section"
        return
    }

    $isPassthrough = $diagnoseSection -match '\*\*Status:\*\*\s*passthrough'
    if ($isPassthrough) {
        Write-Result "INFO" "$FileName — Diagnose is passthrough, skipping knowledge check"
        return
    }

    if ($diagnoseSection -match 'Diagnostic Knowledge') {
        Write-Result "PASS" "$FileName — Diagnose has Diagnostic Knowledge section"
    } else {
        Write-Result "FAIL" "$FileName — Diagnose missing ##### Diagnostic Knowledge"
    }

    if ($diagnoseSection -match 'Failure Patterns') {
        Write-Result "PASS" "$FileName — Diagnose has Failure Patterns"
    } else {
        Write-Result "FAIL" "$FileName — Diagnose missing Failure Patterns table"
    }
}

# --- Rule 5: Provider has NAVIGATION sentinel and required fields ---
function Test-ProviderFile {
    param([string]$FilePath, [string]$ProviderDir)

    $providerName = Split-Path $ProviderDir -Leaf
    $content = Get-Content $FilePath -Raw

    Write-Host "`n  [provider.md]" -ForegroundColor Cyan

    if ($content -match '<!-- NAVIGATION -->') {
        Write-Result "PASS" "provider.md — NAVIGATION sentinel present"
    } else {
        Write-Result "FAIL" "provider.md — missing <!-- NAVIGATION --> sentinel"
    }

    # Schema header (required for all toolkit files)
    Test-SchemaHeader -FilePath $FilePath -FileName "provider.md"

    # Available Test Types check (Default Test Type no longer required)
    if ($content -match '\*\*Available Test Types:\*\*\s*(.+)') {
        $available = $Matches[1].Trim()
        $isFlat = ($available -eq 'none')
        if ($isFlat) {
            Write-Result "PASS" "provider.md — Available Test Types: none (flat provider)"
        } else {
            Write-Result "PASS" "provider.md — Available Test Types: $available"
        }
    } else {
        Write-Result "FAIL" "provider.md — missing **Available Test Types:**"
        $available = $null
        $isFlat = $false
    }

    # Required Settings table
    if ($content -match 'Required Settings') {
        Write-Result "PASS" "provider.md — has Required Settings section"
    } else {
        Write-Result "FAIL" "provider.md — no Required Settings section (required by SKILL.md)"
    }

    # Common Metadata
    if ($content -match '\*\*Cluster:\*\*' -or $content -match '\*\*Auth:\*\*') {
        Write-Result "PASS" "provider.md — has Common Metadata"
    } else {
        Write-Result "WARN" "provider.md — no Common Metadata (Cluster/Auth)"
    }

    # MCP Data Source
    if ($content -match 'MCP Data Source') {
        Write-Result "PASS" "provider.md — has MCP Data Source section"
    } else {
        Write-Result "WARN" "provider.md — no MCP Data Source section"
    }

    # Common Tables
    if ($content -match 'Common Tables') {
        Write-Result "PASS" "provider.md — has Common Tables section"
    } else {
        Write-Result "WARN" "provider.md — no Common Tables section"
    }

    # Key Functions
    if ($content -match 'Key Functions') {
        Write-Result "PASS" "provider.md — has Key Functions section"
    } else {
        Write-Result "WARN" "provider.md — no Key Functions section"
    }

    # Terminology with Execution Hierarchy
    if ($content -match 'Terminology') {
        Write-Result "PASS" "provider.md — has Terminology section"
        if ($content -match 'Execution Hierarchy') {
            Write-Result "PASS" "provider.md — Terminology has Execution Hierarchy"
        } else {
            Write-Result "WARN" "provider.md — Terminology missing Execution Hierarchy"
        }
        if ($content -match 'FailureHandling Modes') {
            Write-Result "PASS" "provider.md — Terminology has FailureHandling Modes"
        } else {
            Write-Result "WARN" "provider.md — Terminology missing FailureHandling Modes"
        }
    } else {
        Write-Result "WARN" "provider.md — no Terminology section"
    }

    # Error Records (CER)
    if ($content -match 'Error Records.*CER') {
        Write-Result "PASS" "provider.md — has Error Records (CER) section"
    } else {
        Write-Result "WARN" "provider.md — no Error Records (CER) section"
    }

    # Provider Notes subsections
    if ($content -match 'Provider Notes') {
        Write-Result "PASS" "provider.md — has Provider Notes section"
        $notesSubsections = @(
            @{ Name = "Permissions & Access"; Pattern = 'Permissions.*Access' },
            @{ Name = "CER Data Model"; Pattern = 'CER Data Model' },
            @{ Name = "Garbage Collection"; Pattern = 'Garbage Collection' },
            @{ Name = "Schedules"; Pattern = '### Schedules' },
            @{ Name = "Test Cancellation"; Pattern = 'Test Cancellation' },
            @{ Name = "Support Channels"; Pattern = 'Support Channels' }
        )
        foreach ($sub in $notesSubsections) {
            if ($content -match $sub.Pattern) {
                Write-Result "PASS" "provider.md — Provider Notes has $($sub.Name)"
            } else {
                Write-Result "WARN" "provider.md — Provider Notes missing $($sub.Name)"
            }
        }
    } else {
        Write-Result "WARN" "provider.md — no Provider Notes section"
    }

    # Platform Primitives sentinels — read from NAVIGATION instead of hardcoding
    $platformPrimitives = @()
    if ($content -match '\*\*Platform Primitives:\*\*\s*(.+)') {
        $platformPrimitives = $Matches[1].Trim() -split ',' | ForEach-Object { $_.Trim() }
        Write-Result "PASS" "provider.md — Platform Primitives declared: $($platformPrimitives -join ', ')"
    } else {
        if (-not $isFlat) {
            Write-Result "WARN" "provider.md — no **Platform Primitives:** in NAVIGATION (typed providers should declare these)"
        }
    }
    foreach ($prim in $platformPrimitives) {
        $primPattern = "<!-- PRIMITIVE:$prim -->"
        if ($content -match [regex]::Escape($primPattern)) {
            Write-Result "PASS" "provider.md — platform primitive PRIMITIVE:$prim present"
        } else {
            Write-Result "WARN" "provider.md — missing platform primitive <!-- PRIMITIVE:$prim -->"
        }
    }

    # Diagnose section: Diagnostic Knowledge
    # Bound extraction to next PRIMITIVE sentinel (or EOF) to avoid including Report section
    if ($content -match '<!-- PRIMITIVE:Diagnose -->') {
        if ($content -match '(?s)<!-- PRIMITIVE:Diagnose -->(.*?)(?=<!-- PRIMITIVE:|$)') {
            $diagnoseSection = $Matches[1]
            $diagChecks = @(
                @{ Name = "Platform Failure Patterns"; Pattern = 'Platform Failure Patterns' },
                @{ Name = "Platform Cascade Rules"; Pattern = 'Platform Cascade Rules' },
                @{ Name = "Platform Environment Checks"; Pattern = 'Platform Environment Checks' }
            )
            foreach ($check in $diagChecks) {
                if ($diagnoseSection -match $check.Pattern) {
                    Write-Result "PASS" "provider.md — Diagnose has $($check.Name)"
                } else {
                    Write-Result "WARN" "provider.md — Diagnose missing $($check.Name)"
                }
            }
        }
    }

    return @{
        Available = $available
        IsFlat = $isFlat
    }
}

# --- Rule 6: Test type files match Available Test Types ---
function Test-TestTypeFiles {
    param([string]$ProviderDir, [string]$Available)

    if (-not $Available -or $Available -eq 'none') {
        Write-Result "INFO" "Flat provider — no test type files expected"
        return
    }

    # Check all available test types
    $types = $Available -split ',' | ForEach-Object { $_.Trim() }
    foreach ($testType in $types) {
        # Validate test type name to prevent path traversal
        if ($testType -notmatch '^[a-zA-Z0-9_-]+$') {
            Write-Result "FAIL" "Test type name contains invalid characters: $testType (must be alphanumeric, hyphens, underscores only)"
            continue
        }
        $typeFile = Join-Path $ProviderDir "$testType.md"
        if (Test-Path $typeFile) {
            Write-Result "PASS" "Test type file exists: $testType.md"
        } else {
            Write-Result "FAIL" "Test type file missing: $testType.md (listed in Available Test Types)"
        }
    }
}

# --- Rule 7: KQL queries reference only known columns for key tables/functions ---
function Test-KqlColumnReferences {
    param([string]$FilePath, [string]$FileName)

    $content = Get-Content $FilePath -Raw

    # Known column schemas — columns that do NOT exist on these tables/functions
    # Used to catch hallucinated column references
    $forbiddenColumns = @{
        'GetActionCompletion' = @('ExceptionType', 'Category', 'SubCategory', 'ErrorMessage', 'StackTrace')
        'EnvironmentEvent'    = @('TipNodeId')
    }

    # Extract all KQL code blocks
    $kqlBlocks = [regex]::Matches($content, '(?s)```kql\s*\n(.*?)```')

    if ($kqlBlocks.Count -eq 0) {
        Write-Result "INFO" "$FileName — no KQL code blocks found"
        return
    }

    Write-Result "INFO" "$FileName — found $($kqlBlocks.Count) KQL code block(s), checking column references"

    foreach ($entry in $forbiddenColumns.GetEnumerator()) {
        $tableName = $entry.Key
        $badColumns = $entry.Value

        foreach ($block in $kqlBlocks) {
            $kql = $block.Groups[1].Value

            # Only check blocks that reference this table/function
            if ($kql -notmatch [regex]::Escape($tableName)) {
                continue
            }

            foreach ($col in $badColumns) {
                # Check for column name used as a projected/referenced field (not in comments)
                $lines = $kql -split "`n" | Where-Object { $_ -notmatch '^\s*//' }
                $nonCommentKql = $lines -join "`n"
                if ($nonCommentKql -match "\b$col\b") {
                    Write-Result "FAIL" "$FileName — KQL references '$col' on $tableName (column does not exist on this table)"
                }
            }
        }
    }

    Write-Result "PASS" "$FileName — KQL column reference check complete"
}

# --- Schema header check ---
function Test-SchemaHeader {
    param([string]$FilePath, [string]$FileName)

    $content = Get-Content $FilePath -Raw
    if ($content -match '\*\*Schema:\*\*\s*\d+') {
        Write-Result "PASS" "$FileName — has Schema header"
    } else {
        Write-Result "FAIL" "$FileName — missing **Schema:** header (required by SKILL.md)"
    }
}

# --- Main: Validate a single provider ---
function Test-Provider {
    param([string]$ProviderDir)

    $providerName = Split-Path $ProviderDir -Leaf
    Write-Host "`n[$providerName]" -ForegroundColor Yellow

    # Check provider.md
    $providerFile = Join-Path $ProviderDir "provider.md"
    if (-not (Test-Path $providerFile)) {
        Write-Result "FAIL" "provider.md — NOT FOUND"
        return
    }

    $providerInfo = Test-ProviderFile -FilePath $providerFile -ProviderDir $ProviderDir

    # Check test type files (skipped for flat providers)
    Test-TestTypeFiles -ProviderDir $ProviderDir -Available $providerInfo.Available

    if ($providerInfo.IsFlat) {
        # Flat provider: validate primitives directly in provider.md
        Write-Host "`n  [provider.md — flat mode primitives]" -ForegroundColor Cyan
        Test-PrimitiveSentinels -FilePath $providerFile -FileName "provider.md"
        Test-PassthroughSections -FilePath $providerFile -FileName "provider.md"
        Test-ActiveSections -FilePath $providerFile -FileName "provider.md"
        Test-DiagnosticKnowledge -FilePath $providerFile -FileName "provider.md"
    } else {
        # Typed provider: validate each test type file
        $testTypeFiles = Get-ChildItem $ProviderDir -Filter "*.md" -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne "provider.md" }

        foreach ($ttFile in $testTypeFiles) {
            Write-Host "`n  [$($ttFile.Name)]" -ForegroundColor Cyan
            Test-SchemaHeader -FilePath $ttFile.FullName -FileName $ttFile.Name
            Test-PrimitiveSentinels -FilePath $ttFile.FullName -FileName $ttFile.Name
            Test-PassthroughSections -FilePath $ttFile.FullName -FileName $ttFile.Name
            Test-ActiveSections -FilePath $ttFile.FullName -FileName $ttFile.Name
            Test-DiagnosticKnowledge -FilePath $ttFile.FullName -FileName $ttFile.Name
            Test-KqlColumnReferences -FilePath $ttFile.FullName -FileName $ttFile.Name
        }
    }

    # Also validate KQL in provider.md
    Test-KqlColumnReferences -FilePath $providerFile -FileName "provider.md"
}

# === Main Execution ===

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  AZURE TEST TOOLKIT VALIDATION" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "References: $TemplatesPath" -ForegroundColor Gray

if ($ProviderName) {
    # Validate provider name to prevent path traversal
    if ($ProviderName -notmatch '^[a-zA-Z0-9_-]+$') {
        Write-Host "Invalid provider name: $ProviderName (must be alphanumeric, hyphens, underscores only)" -ForegroundColor Red
        exit 1
    }
    $providerDir = Join-Path $TemplatesPath $ProviderName
    if (Test-Path $providerDir) {
        Test-Provider -ProviderDir $providerDir
    } else {
        Write-Host "Provider not found: $ProviderName" -ForegroundColor Red
        exit 1
    }
} else {
    # Find all provider directories (exclude template files and README)
    $providers = Get-ChildItem $TemplatesPath -Directory -ErrorAction SilentlyContinue
    if ($providers.Count -eq 0) {
        Write-Host "`n  [WARN] No provider directories found under $TemplatesPath" -ForegroundColor Yellow
    }
    foreach ($provider in $providers) {
        Test-Provider -ProviderDir $provider.FullName
    }
}

Write-Host "`n=========================================" -ForegroundColor Cyan
if ($script:allPassed) {
    Write-Host "  ALL VALIDATIONS PASSED!" -ForegroundColor Green
} else {
    Write-Host "  $($script:errorCount) FAILURE(S) FOUND" -ForegroundColor Red
}
if ($script:warnCount -gt 0) {
    Write-Host "  $($script:warnCount) warning(s)" -ForegroundColor Yellow
}
Write-Host "=========================================" -ForegroundColor Cyan

exit $(if ($script:allPassed) { 0 } else { 1 })
