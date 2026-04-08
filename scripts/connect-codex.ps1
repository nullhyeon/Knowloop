$ErrorActionPreference = "Stop"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Codex CLI login will start if needed."
Write-Host "If a browser opens, complete the OpenAI or ChatGPT sign-in flow there."

Push-Location $repoRoot
try {
    codex login
}
finally {
    Pop-Location
}