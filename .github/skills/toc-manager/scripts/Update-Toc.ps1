<#
.SYNOPSIS
    Scans documentation directory and updates toc.yml files.
.DESCRIPTION
    Ensures every .md file has a toc.yml entry. Creates toc.yml
    where missing, adds entries for unregistered files.
.PARAMETER DocsRoot
    Path to the documentation root directory.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$DocsRoot
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DocsRoot)) {
    throw "Docs directory not found: $DocsRoot"
}

$DocsRoot = (Resolve-Path $DocsRoot).Path
$skipDirs = @("_site", ".meta", "obj", "node_modules", "assets")

function Get-DisplayName {
    param([string]$FilePath)

    # Try to read H1 from file
    if (Test-Path $FilePath) {
        $lines = Get-Content $FilePath -TotalCount 20 -ErrorAction SilentlyContinue
        foreach ($line in $lines) {
            if ($line -match "^#\s+(.+)$") {
                return $Matches[1].Trim()
            }
        }
    }

    # Fall back to filename
    $name = [System.IO.Path]::GetFileNameWithoutExtension($FilePath)
    $name = $name -replace "[-_]", " "
    return (Get-Culture).TextInfo.ToTitleCase($name)
}

function Get-TocEntries {
    param([string]$TocPath)

    if (-not (Test-Path $TocPath)) {
        return @()
    }

    $content = Get-Content $TocPath -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        return @()
    }

    # Simple regex to extract href values
    $hrefs = [regex]::Matches($content, "href:\s*(.+)")
    return $hrefs | ForEach-Object { $_.Groups[1].Value.Trim() }
}

function Update-DirectoryToc {
    param([string]$DirPath)

    $mdFiles = Get-ChildItem -Path $DirPath -Filter "*.md" -File | Where-Object { $_.Name -ne "toc.yml" }
    $subDirs = Get-ChildItem -Path $DirPath -Directory | Where-Object { $skipDirs -notcontains $_.Name }

    if ($mdFiles.Count -eq 0 -and $subDirs.Count -eq 0) {
        return
    }

    $tocPath = Join-Path $DirPath "toc.yml"
    $existingHrefs = Get-TocEntries -TocPath $tocPath
    $newEntries = @()

    # Sort: index.md first, then alphabetical, glossary.md last
    $sorted = $mdFiles | Sort-Object {
        switch ($_.Name) {
            "index.md" { "0_$($_.Name)" }
            "glossary.md" { "z_$($_.Name)" }
            default { "m_$($_.Name)" }
        }
    }

    foreach ($file in $sorted) {
        if ($existingHrefs -notcontains $file.Name -and $existingHrefs -notcontains "./$($file.Name)") {
            $displayName = Get-DisplayName -FilePath $file.FullName
            $newEntries += "- name: $displayName`n  href: $($file.Name)"
        }
    }

    foreach ($sub in $subDirs) {
        $subRef = "$($sub.Name)/"
        if ($existingHrefs -notcontains $subRef) {
            $displayName = (Get-Culture).TextInfo.ToTitleCase($sub.Name -replace "[-_]", " ")
            $newEntries += "- name: $displayName`n  href: $subRef"
        }
    }

    if ($newEntries.Count -gt 0) {
        if (Test-Path $tocPath) {
            $existing = Get-Content $tocPath -Raw
            $appendContent = "`n" + ($newEntries -join "`n")
            Set-Content -Path $tocPath -Value ($existing.TrimEnd() + $appendContent) -Encoding UTF8
            Write-Host "  Updated: $(Split-Path $tocPath -Leaf) (+$($newEntries.Count) entries)" -ForegroundColor Yellow
        } else {
            $content = $newEntries -join "`n"
            Set-Content -Path $tocPath -Value $content -Encoding UTF8
            Write-Host "  Created: $($DirPath.Substring($DocsRoot.Length + 1))/toc.yml ($($newEntries.Count) entries)" -ForegroundColor Green
        }
    }

    # Recurse into subdirectories
    foreach ($sub in $subDirs) {
        Update-DirectoryToc -DirPath $sub.FullName
    }
}

Write-Host "Updating toc.yml files in: $DocsRoot" -ForegroundColor Cyan
Update-DirectoryToc -DirPath $DocsRoot
Write-Host "TOC update complete." -ForegroundColor Green
