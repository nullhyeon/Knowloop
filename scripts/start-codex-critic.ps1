$ErrorActionPreference = "Stop"

$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"
$repoRoot = Split-Path -Parent $PSScriptRoot
$promptFile = Join-Path $repoRoot ".agents\prompts\codex-critic.md"
$initialPrompt = Get-Content -LiteralPath $promptFile -Raw

Push-Location $repoRoot
try {
    codex -m gpt-5.4 -c 'model_reasoning_effort="xhigh"' $initialPrompt
}
finally {
    Pop-Location
}
