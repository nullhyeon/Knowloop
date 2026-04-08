$ErrorActionPreference = "Stop"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Gemini CLI will now start."
Write-Host "Choose 'Sign in with Google' and use the Google account that owns your Google AI Pro subscription."
Write-Host "After login completes, Gemini will cache credentials locally for future sessions."

Push-Location $repoRoot
try {
    gemini
}
finally {
    Pop-Location
}