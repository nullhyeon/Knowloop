param(
    [int]$MaxAttempts = 1,
    [int]$TimeoutSeconds = 240,
    [int]$RetryDelaySeconds = 15
)

$ErrorActionPreference = "Stop"
$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"
$repoRoot = Split-Path -Parent $PSScriptRoot
$promptFile = Join-Path $repoRoot ".agents\prompts\gemini-critic.md"
$criticPrompt = (Get-Content -LiteralPath $promptFile -Raw).Trim() + "`n`nReview the current planned slice or uncommitted worktree as the critic pass. Focus on the active slice only. Return findings first. If there are no material findings, say so explicitly."

function Invoke-GeminiCriticAttempt {
    param(
        [string]$RepoRoot,
        [string]$Prompt,
        [int]$TimeoutSeconds
    )

    $job = Start-Job -ScriptBlock {
        param($RepoRoot, $Prompt)
        $ErrorActionPreference = "Stop"
        $env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"
        Set-Location $RepoRoot
        gemini -m pro -p $Prompt
        if ($LASTEXITCODE -ne 0) {
            throw "gemini exited with code $LASTEXITCODE"
        }
    } -ArgumentList $RepoRoot, $Prompt

    try {
        if (-not (Wait-Job $job -Timeout $TimeoutSeconds)) {
            throw "timeout"
        }
        Receive-Job $job -Wait -AutoRemoveJob
        return $true
    }
    catch {
        if ($job.State -eq "Running") {
            Stop-Job $job | Out-Null
        }
        Receive-Job $job -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $job -Force -ErrorAction SilentlyContinue | Out-Null
        return $false
    }
}

Push-Location $repoRoot
try {
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Write-Host "Running Gemini Pro Critic attempt $attempt/$MaxAttempts"
        Write-Host "Reference prompt: .agents\\prompts\\gemini-critic.md"
        if (Invoke-GeminiCriticAttempt -RepoRoot $repoRoot -Prompt $criticPrompt -TimeoutSeconds $TimeoutSeconds) {
            return
        }
        if ($attempt -lt $MaxAttempts) {
            Write-Host "Gemini Pro Critic did not complete. Retrying in $RetryDelaySeconds seconds..."
            Start-Sleep -Seconds $RetryDelaySeconds
        }
    }
    throw "Gemini Pro Critic did not complete after $MaxAttempts attempt(s)."
}
finally {
    Pop-Location
}
