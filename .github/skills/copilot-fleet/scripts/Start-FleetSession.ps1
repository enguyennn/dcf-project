<#
.SYNOPSIS
    Launches a Copilot CLI fleet session in a new console window.
.DESCRIPTION
    Spawns copilot in interactive mode with a /fleet prompt in a new window.
    The /fleet command requires a real console — subprocess pipes and
    CREATE_NO_WINDOW cause it to be treated as literal text.
    Cross-platform: pwsh runs on Windows, macOS, Linux.
.PARAMETER WorkingDirectory
    The repository root where the session runs.
.PARAMETER Prompt
    The prompt to send. Must start with "/fleet".
.EXAMPLE
    pwsh Start-FleetSession.ps1 -WorkingDirectory "/repos/my-service" `
      -Prompt "/fleet Generate docs for this repo. Output to docs/."
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$WorkingDirectory,

    [Parameter(Mandatory = $true)]
    [string]$Prompt
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $WorkingDirectory)) {
    throw "Working directory not found: $WorkingDirectory"
}

if (-not $Prompt.StartsWith("/fleet")) {
    throw "Prompt must start with '/fleet'. Got: $Prompt"
}

$resolvedDir = (Resolve-Path $WorkingDirectory).Path

function Convert-ToExplicitArtifactPromptPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $normalizedValue = $Value
    $artifactRoots = @("agents", "instructions", "prompts", "skills", "templates")

    foreach ($artifactRoot in $artifactRoots) {
        $normalizedValue = $normalizedValue -replace "@$artifactRoot/", "@.github/$artifactRoot/"
    }

    return $normalizedValue
}

$normalizedPrompt = Convert-ToExplicitArtifactPromptPaths -Value $Prompt

# Verify copilot CLI is available and resolve full path
$copilotCmd = Get-Command "copilot" -ErrorAction SilentlyContinue
if (-not $copilotCmd) {
    throw "Copilot CLI not found on PATH. Install from https://aka.ms/copilot-cli"
}
$copilotPath = $copilotCmd.Source

# Guard: check if a copilot session is already running to prevent duplicate launches.
# Start-Process is async — if the caller retries, it will spawn extra windows.
$existing = Get-Process -Name "copilot" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "WARNING: Copilot is already running (PID: $($existing[0].Id))." -ForegroundColor Yellow
    Write-Host "A fleet session may already be active. Do NOT call this script again." -ForegroundColor Yellow
    Write-Host "If you need to restart, kill the existing process first:" -ForegroundColor Yellow
    Write-Host "  Stop-Process -Id $($existing[0].Id) -Force" -ForegroundColor Yellow
    throw "Copilot process already running. Kill it before launching a new session."
}

Write-Host "Starting fleet session in: $resolvedDir" -ForegroundColor Cyan
Write-Host "Prompt: $normalizedPrompt" -ForegroundColor Gray

# Start-Process gives copilot a real console window, which is required
# for /fleet to be processed as a slash command (not literal text).
# Use pwsh -Command with & to invoke copilot (handles .ps1 wrappers)
# in a single new window.
$escapedPrompt = $normalizedPrompt.Replace("'", "''")
$proc = Start-Process -FilePath "pwsh" `
    -ArgumentList "-NoProfile -Command `"& '$copilotPath' --interactive --allow-all-tools '$escapedPrompt'`"" `
    -WorkingDirectory $resolvedDir `
    -PassThru

Write-Host "Fleet session launched (PID: $($proc.Id))" -ForegroundColor Green
Write-Output $proc.Id
