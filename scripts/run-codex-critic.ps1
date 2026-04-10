param(
    [int]$MaxAttempts = 1,
    [int]$TimeoutSeconds = 240,
    [int]$RetryDelaySeconds = 15
)

$ErrorActionPreference = "Stop"

$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"
$repoRoot = Split-Path -Parent $PSScriptRoot
$promptFile = Join-Path $repoRoot ".agents\prompts\codex-critic.md"
$criticPrompt = (Get-Content -LiteralPath $promptFile -Raw).Trim() + "`n`nReview the current planned slice or uncommitted worktree as the fallback critic pass. Return findings first. If there are no material findings, say so explicitly."

function Invoke-CodexCriticAttempt {
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
        codex exec -m gpt-5.4 -c 'model_reasoning_effort="xhigh"' -s read-only $Prompt
        if ($LASTEXITCODE -ne 0) {
            throw "codex exited with code $LASTEXITCODE"
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
        Write-Host "Running Codex Critic attempt $attempt/$MaxAttempts"
        Write-Host "Reference prompt: .agents\\prompts\\codex-critic.md"
        if (Invoke-CodexCriticAttempt -RepoRoot $repoRoot -Prompt $criticPrompt -TimeoutSeconds $TimeoutSeconds) {
            return
        }
        if ($attempt -lt $MaxAttempts) {
            Write-Host "Codex Critic did not complete. Retrying in $RetryDelaySeconds seconds..."
            Start-Sleep -Seconds $RetryDelaySeconds
        }
    }
    throw "Codex Critic did not complete after $MaxAttempts attempt(s)."
}
finally {
    Pop-Location
}
