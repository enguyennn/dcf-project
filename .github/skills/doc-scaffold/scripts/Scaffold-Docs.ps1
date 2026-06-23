<#
.SYNOPSIS
    Scaffolds a documentation directory structure.
.DESCRIPTION
    Creates the standard documentation directory layout with
    categories, starter toc.yml files, index.md, and .gitignore.
    Idempotent — skips existing files.
.PARAMETER TargetRepo
    Root of the target repository.
.PARAMETER OutputPath
    Documentation directory name relative to TargetRepo (default: "docs").
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRepo,

    [Parameter(Mandatory = $false)]
    [string]$OutputPath = "docs"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $TargetRepo)) {
    throw "Target repository not found: $TargetRepo"
}

$TargetRepo = (Resolve-Path $TargetRepo).Path
$DocsRoot = Join-Path $TargetRepo $OutputPath

function New-FileIfMissing {
    param(
        [string]$Path,
        [string]$Content
    )
    if (Test-Path $Path) {
        Write-Host "  Skipped (exists): $(Split-Path $Path -Leaf)" -ForegroundColor DarkGray
        return
    }
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Set-Content -Path $Path -Value $Content -Encoding UTF8
    Write-Host "  Created: $(Split-Path $Path -Leaf)" -ForegroundColor Green
}

Write-Host "Scaffolding documentation at: $DocsRoot" -ForegroundColor Cyan

# Create directories
$dirs = @(
    $DocsRoot,
    (Join-Path $DocsRoot "tutorials"),
    (Join-Path $DocsRoot "how-to-guides"),
    (Join-Path $DocsRoot "reference"),
    (Join-Path $DocsRoot "explanation"),
    (Join-Path $DocsRoot "assets/images")
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created dir: $($dir.Substring($TargetRepo.Length + 1))" -ForegroundColor Green
    }
}

# Root index.md
New-FileIfMissing -Path (Join-Path $DocsRoot "index.md") -Content @"
---
title: "Documentation"
---

# Documentation

Welcome to the documentation site. Use the navigation to explore.
"@

# Root toc.yml
New-FileIfMissing -Path (Join-Path $DocsRoot "toc.yml") -Content @"
- name: Overview
  href: index.md
- name: Tutorials
  href: tutorials/
- name: How-to Guides
  href: how-to-guides/
- name: Reference
  href: reference/
- name: Explanation
  href: explanation/
"@

# Sub-directory toc.yml files
$subDirs = @("tutorials", "how-to-guides", "reference", "explanation")
foreach ($sub in $subDirs) {
    $displayName = (Get-Culture).TextInfo.ToTitleCase(($sub -replace "-", " "))
    New-FileIfMissing -Path (Join-Path $DocsRoot "$sub/toc.yml") -Content @"
# $displayName
# Add entries as documents are created:
# - name: Document Title
#   href: document-name.md
"@
}

# .gitignore
New-FileIfMissing -Path (Join-Path $DocsRoot ".gitignore") -Content @"
_site/
obj/
"@

Write-Host ""
Write-Host "Scaffold complete at $OutputPath/" -ForegroundColor Green
Write-Host "Next: run docfx-config and build-pipeline skills, or /Octane.EngDocs.Setup for full setup." -ForegroundColor Yellow
