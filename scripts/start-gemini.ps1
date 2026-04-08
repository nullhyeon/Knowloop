param(
    [string]$Model = "pro"
)

$ErrorActionPreference = "Stop"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"

$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    Write-Host "Starting Gemini in $repoRoot with model '$Model'"
    Write-Host "Prompt starters live in .agents\\prompts\\"
    Write-Host "Start with docs\\README.md and AGENTS.md"
    gemini -m $Model
}
finally {
    Pop-Location
}
