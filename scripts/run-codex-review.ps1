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
$promptFile = Join-Path $repoRoot ".agents\prompts\codex-reviewer.md"
$basePrompt = (Get-Content -LiteralPath $promptFile -Raw).Trim()

. (Join-Path $PSScriptRoot "lib\review-package.ps1")

function Invoke-CodexReviewerAttempt {
    param(
        [string]$RepoRoot,
        [string]$Prompt,
        [int]$TimeoutSeconds
    )

    $promptPath = [System.IO.Path]::GetTempFileName()
    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    $resultPath = [System.IO.Path]::GetTempFileName()

    try {
        Set-Content -LiteralPath $promptPath -Value $Prompt -Encoding utf8
        $escapedRepoRoot = $RepoRoot.Replace("'", "''")
        $escapedPromptPath = $promptPath.Replace("'", "''")
        $escapedResultPath = $resultPath.Replace("'", "''")
        $command = @"
`$ErrorActionPreference = 'Stop'
`$env:Path += ';' + [Environment]::GetFolderPath('UserProfile') + '\AppData\Roaming\npm'
Set-Location '$escapedRepoRoot'
`$prompt = Get-Content -LiteralPath '$escapedPromptPath' -Raw
`$prompt | codex exec -m gpt-5.4 -c 'model_reasoning_effort="low"' -s read-only -o '$escapedResultPath' -
exit `$LASTEXITCODE
"@
        $encodedCommand = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($command))
        $process = Start-Process `
            -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile", "-EncodedCommand", $encodedCommand) `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath `
            -PassThru `
            -WindowStyle Hidden

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
            }
            catch {
                try {
                    $process.Kill()
                    $process.WaitForExit()
                }
                catch {
                }
            }
            return $false
        }

        $stdout = Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
        if (-not [string]::IsNullOrWhiteSpace($stdout)) {
            Write-Output $stdout.TrimEnd()
        }
        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            Write-Output $stderr.TrimEnd()
        }
        $result = Get-Content -LiteralPath $resultPath -Raw -ErrorAction SilentlyContinue
        if (-not [string]::IsNullOrWhiteSpace($result)) {
            Write-Output $result.TrimEnd()
        }

        return $process.ExitCode -eq 0
    }
    finally {
        Remove-Item -LiteralPath $promptPath, $stdoutPath, $stderrPath, $resultPath -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-CodexReviewerPackages {
    param(
        [string[]]$ScopedFiles,
        [int]$CurrentMaxFilesPerPackage,
        [int]$CurrentMaxDiffLines,
        [string]$CurrentScopeName
    )

    $packages = New-ReviewPackages `
        -RepoRoot $repoRoot `
        -Role reviewer `
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
            Write-Host "Running Codex Reviewer package $($package.Index)/$($package.Total) attempt $attempt/$attemptBudget"
            Write-Host "Review package: $($package.Path)"
            if (Invoke-CodexReviewerAttempt -RepoRoot $repoRoot -Prompt $packagePrompt -TimeoutSeconds $TimeoutSeconds) {
                $completed = $true
                break
            }
            if ($attempt -lt $attemptBudget) {
                Write-Host "Codex Reviewer did not complete. Retrying in $RetryDelaySeconds seconds..."
                Start-Sleep -Seconds $RetryDelaySeconds
            }
        }

        if ($completed) {
            continue
        }

        if ($packageCanNarrow) {
            Write-Host "Codex Reviewer timed out on a wide package. Narrowing scope and retrying..."
            $nextMaxDiffLines = [Math]::Max(120, [int][Math]::Floor($CurrentMaxDiffLines / 2))
            if ($nextMaxDiffLines -ge $CurrentMaxDiffLines) {
                throw "Codex Reviewer cannot narrow package '$($package.Path)' any further after timing out."
            }
            Invoke-CodexReviewerPackages `
                -ScopedFiles $package.Files `
                -CurrentMaxFilesPerPackage 1 `
                -CurrentMaxDiffLines $nextMaxDiffLines `
                -CurrentScopeName ("{0}-narrow-{1}" -f $CurrentScopeName, $package.Index)
            continue
        }

        throw "Codex Reviewer did not complete for package '$($package.Path)' after $attemptBudget attempt(s)."
    }
}

Push-Location $repoRoot
try {
    $scopedFiles = Get-ReviewScopedFiles -RepoRoot $repoRoot -Files $Files
    Invoke-CodexReviewerPackages `
        -ScopedFiles $scopedFiles `
        -CurrentMaxFilesPerPackage $MaxFilesPerPackage `
        -CurrentMaxDiffLines $MaxDiffLines `
        -CurrentScopeName $ScopeName
}
finally {
    Pop-Location
}
