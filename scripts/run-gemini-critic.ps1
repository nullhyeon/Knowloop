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
$promptFile = Join-Path $repoRoot ".agents\prompts\gemini-critic.md"
$basePrompt = (Get-Content -LiteralPath $promptFile -Raw).Trim()

. (Join-Path $PSScriptRoot "lib\review-package.ps1")

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

function Invoke-GeminiCriticPackages {
    param(
        [string[]]$ScopedFiles,
        [int]$CurrentMaxFilesPerPackage,
        [int]$CurrentMaxDiffLines,
        [string]$CurrentScopeName
    )

    $packages = New-ReviewPackages `
        -RepoRoot $repoRoot `
        -Role critic `
        -ScopeName $CurrentScopeName `
        -Focus $Focus `
        -Files $ScopedFiles `
        -ContractDocs $ContractDocs `
        -MaxFilesPerPackage $CurrentMaxFilesPerPackage `
        -MaxDiffLines $CurrentMaxDiffLines

    foreach ($package in $packages) {
        $packageCanNarrow = ($package.Files.Count -gt 1) -or (
            ($package.Displays | Where-Object { $_ -match '\(chunk \d+/\d+\)$' }).Count -gt 0
        )
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

        $attemptBudget = if ($packageCanNarrow) {
            1
        }
        else {
            $MaxAttempts
        }
        $completed = $false

        for ($attempt = 1; $attempt -le $attemptBudget; $attempt++) {
            Write-Host "Running Gemini Pro Critic package $($package.Index)/$($package.Total) attempt $attempt/$attemptBudget"
            Write-Host "Review package: $($package.Path)"
            if (Invoke-GeminiCriticAttempt -RepoRoot $repoRoot -Prompt $packagePrompt -TimeoutSeconds $TimeoutSeconds) {
                $completed = $true
                break
            }
            if ($attempt -lt $attemptBudget) {
                Write-Host "Gemini Pro Critic did not complete. Retrying in $RetryDelaySeconds seconds..."
                Start-Sleep -Seconds $RetryDelaySeconds
            }
        }

        if ($completed) {
            continue
        }

        if ($packageCanNarrow) {
            Write-Host "Gemini Pro Critic timed out on a wide package. Narrowing scope and retrying..."
            $nextMaxDiffLines = [Math]::Max(120, [int][Math]::Floor($CurrentMaxDiffLines / 2))
            if ($nextMaxDiffLines -ge $CurrentMaxDiffLines) {
                throw "Gemini Pro Critic cannot narrow package '$($package.Path)' any further after timing out."
            }
            Invoke-GeminiCriticPackages `
                -ScopedFiles $package.Files `
                -CurrentMaxFilesPerPackage 1 `
                -CurrentMaxDiffLines $nextMaxDiffLines `
                -CurrentScopeName ("{0}-narrow-{1}" -f $CurrentScopeName, $package.Index)
            continue
        }

        throw "Gemini Pro Critic did not complete for package '$($package.Path)' after $attemptBudget attempt(s)."
    }
}

Push-Location $repoRoot
try {
    $scopedFiles = Get-ReviewScopedFiles -RepoRoot $repoRoot -Files $Files
    Invoke-GeminiCriticPackages `
        -ScopedFiles $scopedFiles `
        -CurrentMaxFilesPerPackage $MaxFilesPerPackage `
        -CurrentMaxDiffLines $MaxDiffLines `
        -CurrentScopeName $ScopeName
}
finally {
    Pop-Location
}
