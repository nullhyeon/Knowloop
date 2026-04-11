function ConvertTo-ReviewRelativePath {
    param(
        [string]$RepoRoot,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Review path must not be blank."
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        $resolved = (Resolve-Path -LiteralPath $Path).Path
        $relative = [System.IO.Path]::GetRelativePath($RepoRoot, $resolved)
        return $relative.Replace("/", "\")
    }

    return $Path.Replace("/", "\")
}

function Get-ReviewScopedFiles {
    param(
        [string]$RepoRoot,
        [string[]]$Files = @()
    )

    if ($Files.Count -gt 0) {
        $normalized = $Files |
            ForEach-Object { ConvertTo-ReviewRelativePath -RepoRoot $RepoRoot -Path $_ } |
            Where-Object {
                $_ -and
                $_ -notmatch '^\.tmp-' -and
                $_ -notmatch '^\.tmp-review-packages\\' -and
                $_ -ne 'diff.txt'
            } |
            Select-Object -Unique
        if (-not $normalized) {
            throw "No review files remain after applying the explicit scope."
        }
        return $normalized
    }

    Push-Location $RepoRoot
    try {
        $tracked = @(& git diff --name-only --relative HEAD --)
        if ($LASTEXITCODE -ne 0) {
            throw "git diff --name-only failed while building the review scope."
        }
        $untracked = @(& git ls-files --others --exclude-standard)
        if ($LASTEXITCODE -ne 0) {
            throw "git ls-files --others failed while building the review scope."
        }
    }
    finally {
        Pop-Location
    }

    $files = @($tracked + $untracked) |
        Where-Object {
            $_ -and
            $_ -notmatch '^\.tmp-' -and
            $_ -notmatch '^\.tmp-review-packages\\' -and
            $_ -ne 'diff.txt'
        } |
        Select-Object -Unique

    if (-not $files) {
        throw "No changed files found. Pass -Files to define a focused review scope."
    }

    return $files
}

function Test-ReviewTrackedFile {
    param(
        [string]$RepoRoot,
        [string]$RelativePath
    )

    Push-Location $RepoRoot
    try {
        & git ls-files --error-unmatch -- $RelativePath 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    }
    finally {
        Pop-Location
    }
}

function Get-ReviewPatch {
    param(
        [string]$RepoRoot,
        [string]$RelativePath
    )

    if (Test-ReviewTrackedFile -RepoRoot $RepoRoot -RelativePath $RelativePath) {
        Push-Location $RepoRoot
        try {
            $patch = @(& git diff --unified=3 --no-ext-diff -- $RelativePath)
            if ($LASTEXITCODE -ne 0) {
                throw "git diff failed for review file '$RelativePath'."
            }
            return ($patch -join "`n")
        }
        finally {
            Pop-Location
        }
    }

    $absolutePath = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $absolutePath)) {
        throw "Review file '$RelativePath' does not exist."
    }

    $content = Get-Content -LiteralPath $absolutePath -Encoding utf8
    $body = if ($content.Count -eq 0) { "@@" } else { "@@`n+" + ($content -join "`n+") }
    return @(
        "diff --git a/$RelativePath b/$RelativePath"
        "new file mode 100644"
        "--- /dev/null"
        "+++ b/$RelativePath"
        $body
    ) -join "`n"
}

function Get-ReviewPatchLineCount {
    param(
        [string]$RepoRoot,
        [string]$RelativePath
    )

    $patch = Get-ReviewPatch -RepoRoot $RepoRoot -RelativePath $RelativePath
    if ([string]::IsNullOrWhiteSpace($patch)) {
        return 1
    }
    return ($patch -split "`r?`n").Count
}

function Resolve-ReviewContractDocs {
    param(
        [string[]]$Files,
        [string[]]$ExplicitContractDocs = @()
    )

    $docs = [System.Collections.Generic.List[string]]::new()
    foreach ($doc in $ExplicitContractDocs) {
        if (-not [string]::IsNullOrWhiteSpace($doc) -and -not $docs.Contains($doc)) {
            $docs.Add($doc.Replace("/", "\"))
        }
    }

    $joined = ($Files -join "`n").ToLowerInvariant()

    $docCandidates = @()
    if ($joined -match 'query|fixtures\\queries|test_query') {
        $docCandidates += @(
            'docs\architecture\query-writeback-policy.md',
            'docs\architecture\api-contracts.md',
            'docs\product\fixture-catalog.md'
        )
    }
    if ($joined -match 'candidate|review|promotion|test_candidates|test_review') {
        $docCandidates += @(
            'docs\architecture\data-contracts.md',
            'docs\architecture\promotion-policy.md',
            'docs\architecture\api-contracts.md'
        )
    }
    if ($joined -match 'session|learning|source|manifest|bootstrap|maintenance|health') {
        $docCandidates += @(
            'docs\architecture\data-contracts.md',
            'docs\architecture\api-contracts.md'
        )
    }
    if ($joined -match 'docs\\') {
        $docCandidates += ($Files | Where-Object { $_ -like 'docs\*' })
    }

    foreach ($candidate in $docCandidates | Select-Object -Unique) {
        if (-not $docs.Contains($candidate)) {
            $docs.Add($candidate)
        }
    }

    return @($docs)
}

function Split-ReviewFileGroups {
    param(
        [string]$RepoRoot,
        [string[]]$Files,
        [int]$MaxFilesPerPackage = 3,
        [int]$MaxDiffLines = 300
    )

    $groups = [System.Collections.Generic.List[object]]::new()
    $currentGroup = [System.Collections.Generic.List[string]]::new()
    $currentDiffLines = 0

    foreach ($file in $Files) {
        $lineCount = Get-ReviewPatchLineCount -RepoRoot $RepoRoot -RelativePath $file
        $wouldOverflowFiles = $currentGroup.Count -ge $MaxFilesPerPackage
        $wouldOverflowLines = $currentGroup.Count -gt 0 -and (($currentDiffLines + $lineCount) -gt $MaxDiffLines)

        if ($currentGroup.Count -gt 0 -and ($wouldOverflowFiles -or $wouldOverflowLines)) {
            $groups.Add(@($currentGroup.ToArray()))
            $currentGroup.Clear()
            $currentDiffLines = 0
        }

        $currentGroup.Add($file)
        $currentDiffLines += $lineCount
    }

    if ($currentGroup.Count -gt 0) {
        $groups.Add(@($currentGroup.ToArray()))
    }

    return @($groups)
}

function New-ReviewPackages {
    param(
        [string]$RepoRoot,
        [ValidateSet('critic', 'reviewer')]
        [string]$Role,
        [string]$ScopeName,
        [string]$Focus,
        [string[]]$Files,
        [string[]]$ContractDocs = @(),
        [int]$MaxFilesPerPackage = 3,
        [int]$MaxDiffLines = 300
    )

    $scopedFiles = Get-ReviewScopedFiles -RepoRoot $RepoRoot -Files $Files
    $groups = Split-ReviewFileGroups `
        -RepoRoot $RepoRoot `
        -Files $scopedFiles `
        -MaxFilesPerPackage $MaxFilesPerPackage `
        -MaxDiffLines $MaxDiffLines

    $scopeSlug = if ([string]::IsNullOrWhiteSpace($ScopeName)) {
        "current-slice"
    }
    else {
        ($ScopeName.ToLowerInvariant() -replace '[^a-z0-9-]+', '-').Trim('-')
    }

    $outputRoot = Join-Path $RepoRoot ".tmp-review-packages\$Role\$scopeSlug"
    if (Test-Path -LiteralPath $outputRoot) {
        Remove-Item -LiteralPath $outputRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

    $packages = [System.Collections.Generic.List[object]]::new()
    $packageCount = $groups.Count
    for ($index = 0; $index -lt $packageCount; $index++) {
        $group = @($groups[$index])
        $contracts = Resolve-ReviewContractDocs -Files $group -ExplicitContractDocs $ContractDocs
        $diffStats = if ($group.Count -gt 0) {
            Push-Location $RepoRoot
            try {
                @(& git diff --stat -- @($group)) -join "`n"
            }
            finally {
                Pop-Location
            }
        }
        else {
            ""
        }

        $patches = foreach ($file in $group) {
            Get-ReviewPatch -RepoRoot $RepoRoot -RelativePath $file
        }

        $objective = if ([string]::IsNullOrWhiteSpace($Focus)) {
            if ($Role -eq 'critic') {
                "Challenge the current slice for contract drift, hidden coupling, and replay/idempotency risk."
            }
            else {
                "Review the current slice for correctness, missing tests, and contract drift."
            }
        }
        else {
            $Focus
        }

        $packageBody = @(
            "# Review Package"
            ""
            "- role: $Role"
            "- scope: $ScopeName"
            "- package: " + ($index + 1) + " of " + $packageCount
            ""
            "## Objective"
            $objective
            ""
            "## Scope Rules"
            "- Review only the files listed below."
            "- Use only the listed contract docs as additional context."
            "- Do not rediscover the whole repository unless one of these files explicitly requires it."
            ""
            "## Files Under Review"
        )

        foreach ($file in $group) {
            $packageBody += "- $file"
        }

        $packageBody += @(
            ""
            "## Relevant Contract Docs"
        )

        if ($contracts.Count -eq 0) {
            $packageBody += "- none"
        }
        else {
            foreach ($doc in $contracts) {
                $packageBody += "- $doc"
            }
        }

        $packageBody += @(
            ""
            "## Diff Stats"
            '```text'
            ($diffStats | ForEach-Object { $_ })
            '```'
            ""
            "## Diff"
            '```diff'
            ($patches -join "`n`n")
            '```'
            ""
        )

        $packagePath = Join-Path $outputRoot ("package-{0:d2}.md" -f ($index + 1))
        $packageContent = $packageBody -join "`n"
        Set-Content -LiteralPath $packagePath -Value $packageContent -Encoding utf8

        $packages.Add([PSCustomObject]@{
                Path         = $packagePath
                Files        = $group
                ContractDocs = $contracts
                Index        = $index + 1
                Total        = $packageCount
            })
    }

    return @($packages)
}
