$ErrorActionPreference = "Stop"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"

$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    Write-Host "Starting Gemini Pro Critic in $repoRoot"
    Write-Host "Before reviewing, run: /memory reload"
    Write-Host "Then run: /skills list"
    Write-Host "Prompt starter: .agents\\prompts\\gemini-critic.md"
    Write-Host "Planning index: docs\\README.md"
    gemini -m pro
}
finally {
    Pop-Location
}
