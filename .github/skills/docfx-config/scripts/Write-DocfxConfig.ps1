<#
.SYNOPSIS
    Generates DocFX configuration files for a documentation site.
.PARAMETER DocsRoot
    Path to the documentation directory.
.PARAMETER SiteTitle
    Title for the site. If not provided, inferred from directory or README.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$DocsRoot,

    [Parameter(Mandatory = $false)]
    [string]$SiteTitle = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DocsRoot)) {
    throw "Docs directory not found: $DocsRoot"
}

$DocsRoot = (Resolve-Path $DocsRoot).Path

# Infer title
if ([string]::IsNullOrWhiteSpace($SiteTitle)) {
    $readme = Join-Path $DocsRoot "README.md"
    if (Test-Path $readme) {
        $firstLine = Get-Content $readme -TotalCount 5 | Where-Object { $_ -match "^#\s+" } | Select-Object -First 1
        if ($firstLine) {
            $SiteTitle = ($firstLine -replace "^#\s+", "").Trim()
        }
    }
    if ([string]::IsNullOrWhiteSpace($SiteTitle)) {
        $SiteTitle = Split-Path $DocsRoot -Leaf
        $SiteTitle = (Get-Culture).TextInfo.ToTitleCase(($SiteTitle -replace "[-_]", " "))
    }
}

# docfx.json
$docfxPath = Join-Path $DocsRoot "docfx.json"
if (-not (Test-Path $docfxPath)) {
    $docfxContent = @"
{
  "build": {
    "content": [
      {
        "files": ["**/*.yml", "**/*.md"],
        "exclude": ["_site/**", ".meta/**", "obj/**"]
      }
    ],
    "resource": [
      {
        "files": ["**/*.png", "**/*.jpg", "**/*.gif", "**/*.svg"],
        "exclude": ["_site/**", ".meta/**", "obj/**"]
      }
    ],
    "dest": "_site",
    "globalMetadata": {
      "_appTitle": "$SiteTitle",
      "_enableSearch": true,
      "_enableNewTab": true
    },
    "template": ["default"]
  }
}
"@
    Set-Content -Path $docfxPath -Value $docfxContent -Encoding UTF8
    Write-Host "  Created: docfx.json (title: $SiteTitle)" -ForegroundColor Green
} else {
    Write-Host "  Skipped (exists): docfx.json" -ForegroundColor DarkGray
}

# build.cmd
$buildCmdPath = Join-Path $DocsRoot "build.cmd"
if (-not (Test-Path $buildCmdPath)) {
    Set-Content -Path $buildCmdPath -Value @"
@echo off
echo Building documentation...
docfx docfx.json
if %ERRORLEVEL% NEQ 0 (
    echo Build failed with errors.
    exit /b %ERRORLEVEL%
)
echo Build succeeded.
"@ -Encoding UTF8
    Write-Host "  Created: build.cmd" -ForegroundColor Green
}

# build_docs.sh
$buildShPath = Join-Path $DocsRoot "build_docs.sh"
if (-not (Test-Path $buildShPath)) {
    Set-Content -Path $buildShPath -Value @"
#!/bin/bash
set -e
echo "Building documentation..."
docfx docfx.json
echo "Build succeeded."
"@ -Encoding UTF8
    Write-Host "  Created: build_docs.sh" -ForegroundColor Green
}

# web.config
$webConfigPath = Join-Path $DocsRoot "web.config"
if (-not (Test-Path $webConfigPath)) {
    Set-Content -Path $webConfigPath -Value @"
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <staticContent>
      <mimeMap fileExtension=".json" mimeType="application/json" />
      <mimeMap fileExtension=".yml" mimeType="text/yaml" />
    </staticContent>
  </system.webServer>
</configuration>
"@ -Encoding UTF8
    Write-Host "  Created: web.config" -ForegroundColor Green
}

Write-Host ""
Write-Host "DocFX config complete. Build with: cd $DocsRoot && build.cmd" -ForegroundColor Green
