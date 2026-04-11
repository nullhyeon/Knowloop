param(
    [int]$GeminiAttempts = 1,
    [int]$GeminiTimeoutSeconds = 180,
    [int]$CodexTimeoutSeconds = 180,
    [int]$CodexAttemptsPerRound = 1,
    [int]$RetryDelaySeconds = 15,
    [string]$ScopeName = "current-slice",
    [string]$Focus = "",
    [string[]]$Files = @(),
    [string[]]$ContractDocs = @(),
    [int]$MaxFilesPerPackage = 3,
    [int]$MaxDiffLines = 300
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
            -RetryDelaySeconds $RetryDelaySeconds `
            -ScopeName $ScopeName `
            -Focus $Focus `
            -Files $Files `
            -ContractDocs $ContractDocs `
            -MaxFilesPerPackage $MaxFilesPerPackage `
            -MaxDiffLines $MaxDiffLines
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
                -RetryDelaySeconds $RetryDelaySeconds `
                -ScopeName $ScopeName `
                -Focus $Focus `
                -Files $Files `
                -ContractDocs $ContractDocs `
                -MaxFilesPerPackage $MaxFilesPerPackage `
                -MaxDiffLines $MaxDiffLines
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
