param(
    [int]$GeminiAttempts = 1,
    [int]$GeminiTimeoutSeconds = 240,
    [int]$CodexTimeoutSeconds = 240,
    [int]$CodexAttemptsPerRound = 1,
    [int]$RetryDelaySeconds = 15
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$geminiScript = Join-Path $PSScriptRoot "run-gemini-critic.ps1"
$codexScript = Join-Path $PSScriptRoot "run-codex-critic.ps1"
$codexRound = 1

Push-Location $repoRoot
try {
    Write-Host "Critic chain: Gemini Pro -> Codex Critic -> Codex Critic ..."
    $geminiCompleted = $false
    try {
        & $geminiScript `
            -MaxAttempts $GeminiAttempts `
            -TimeoutSeconds $GeminiTimeoutSeconds `
            -RetryDelaySeconds $RetryDelaySeconds
        $geminiCompleted = $true
    }
    catch {
        Write-Host "Gemini Pro Critic did not complete: $($_.Exception.Message)"
    }
    if ($geminiCompleted) {
        return
    }

    while ($true) {
        Write-Host "Starting Codex Critic round $codexRound"
        try {
            & $codexScript `
                -MaxAttempts $CodexAttemptsPerRound `
                -TimeoutSeconds $CodexTimeoutSeconds `
                -RetryDelaySeconds $RetryDelaySeconds
            return
        }
        catch {
            Write-Host "Codex Critic round $codexRound did not complete: $($_.Exception.Message)"
        }
        $codexRound += 1
        Write-Host "Codex Critic did not complete. Repeating Codex Critic after $RetryDelaySeconds seconds..."
        Start-Sleep -Seconds $RetryDelaySeconds
    }
}
finally {
    Pop-Location
}
