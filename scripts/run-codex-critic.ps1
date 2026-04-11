param(
    [int]$MaxAttempts = 1,
    [int]$TimeoutSeconds = 180,
    [int]$RetryDelaySeconds = 15,
    [string]$ScopeName = "current-slice",
    [string]$Focus = "",
    [string[]]$Files = @(),
    [string[]]$ContractDocs = @(),
    [int]$MaxFilesPerPackage = 3,
    [int]$MaxDiffLines = 300
)

$ErrorActionPreference = "Stop"

$env:Path += ";" + [Environment]::GetFolderPath('UserProfile') + "\AppData\Roaming\npm"
$repoRoot = Split-Path -Parent $PSScriptRoot
$promptFile = Join-Path $repoRoot ".agents\prompts\codex-critic.md"
$basePrompt = (Get-Content -LiteralPath $promptFile -Raw).Trim()

. (Join-Path $PSScriptRoot "lib\review-package.ps1")

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

function Invoke-CodexCriticPackages {
    param(
        [string[]]$ScopedFiles,
        [int]$CurrentMaxFilesPerPackage,
        [int]$CurrentMaxDiffLines
    )

    $packages = New-ReviewPackages `
        -RepoRoot $repoRoot `
        -Role critic `
        -ScopeName $ScopeName `
        -Focus $Focus `
        -Files $ScopedFiles `
        -ContractDocs $ContractDocs `
        -MaxFilesPerPackage $CurrentMaxFilesPerPackage `
        -MaxDiffLines $CurrentMaxDiffLines

    foreach ($package in $packages) {
        $packagePrompt = @(
            $basePrompt
            ""
            "Use the review package below as the authoritative scope."
            "Do not scan unrelated files or rediscover the whole repository."
            ""
            (Get-Content -LiteralPath $package.Path -Raw).Trim()
            ""
            "Return findings first. If there are no material findings, say so explicitly."
        ) -join "`n"

        $attemptBudget = if ($package.Files.Count -gt 1) { 1 } else { $MaxAttempts }
        $completed = $false

        for ($attempt = 1; $attempt -le $attemptBudget; $attempt++) {
            Write-Host "Running Codex Critic package $($package.Index)/$($package.Total) attempt $attempt/$attemptBudget"
            Write-Host "Review package: $($package.Path)"
            if (Invoke-CodexCriticAttempt -RepoRoot $repoRoot -Prompt $packagePrompt -TimeoutSeconds $TimeoutSeconds) {
                $completed = $true
                break
            }
            if ($attempt -lt $attemptBudget) {
                Write-Host "Codex Critic did not complete. Retrying in $RetryDelaySeconds seconds..."
                Start-Sleep -Seconds $RetryDelaySeconds
            }
        }

        if ($completed) {
            continue
        }

        if ($package.Files.Count -gt 1) {
            Write-Host "Codex Critic timed out on a multi-file package. Narrowing scope and retrying..."
            Invoke-CodexCriticPackages `
                -ScopedFiles $package.Files `
                -CurrentMaxFilesPerPackage 1 `
                -CurrentMaxDiffLines ([Math]::Max(120, [int][Math]::Floor($CurrentMaxDiffLines / 2)))
            continue
        }

        throw "Codex Critic did not complete for package '$($package.Path)' after $attemptBudget attempt(s)."
    }
}

Push-Location $repoRoot
try {
    $scopedFiles = Get-ReviewScopedFiles -RepoRoot $repoRoot -Files $Files
    Invoke-CodexCriticPackages `
        -ScopedFiles $scopedFiles `
        -CurrentMaxFilesPerPackage $MaxFilesPerPackage `
        -CurrentMaxDiffLines $MaxDiffLines
}
finally {
    Pop-Location
}
