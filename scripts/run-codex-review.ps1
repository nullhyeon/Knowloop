$ErrorActionPreference = "Stop"

$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"
$repoRoot = Split-Path -Parent $PSScriptRoot
$promptFile = Join-Path $repoRoot ".agents\prompts\codex-reviewer.md"
$reviewPrompt = (Get-Content -LiteralPath $promptFile -Raw).Trim() + "`n`nReview the current uncommitted diff for this repository. Return findings first. If there are no material findings, say so explicitly."

Push-Location $repoRoot
try {
    Write-Host "Running Codex Reviewer against the current worktree"
    Write-Host "Reference prompt: .agents\\prompts\\codex-reviewer.md"
    codex exec -m gpt-5.4 -c 'model_reasoning_effort="xhigh"' -s read-only $reviewPrompt
}
finally {
    Pop-Location
}
