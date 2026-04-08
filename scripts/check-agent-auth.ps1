$ErrorActionPreference = "Continue"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\Python\Python312\Scripts"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Local\Programs\Python\Python312\Scripts"

Write-Host "[Codex]"
codex login status

Write-Host "`n[Gemini]"
$userGemini = 'C:\Users\wowjd\.gemini\settings.json'
if (Test-Path $userGemini) {
    $settings = Get-Content -LiteralPath $userGemini -Raw | ConvertFrom-Json
    $selectedType = $settings.security.auth.selectedType
    Write-Host "Configured auth type: $selectedType"
    Write-Host "To verify end-to-end at runtime, launch .\\scripts\\start-gemini-critic.ps1"
}
else {
    Write-Host "Gemini settings not found. Run .\\scripts\\connect-gemini.ps1"
}

Write-Host "`n[Codex Critic Fallback]"
Write-Host "Fallback critic command: .\\scripts\\run-codex-critic.ps1"
