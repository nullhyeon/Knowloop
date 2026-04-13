function ConvertTo-ReviewRelativePath {
    param(
        [string]$RepoRoot,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Review path must not be blank."
    }

    $repoFullPath = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
    $resolvedFullPath = if ([System.IO.Path]::IsPathRooted($Path)) {
        [System.IO.Path]::GetFullPath($Path)
    }
    else {
        [System.IO.Path]::GetFullPath((Join-Path $repoFullPath $Path))
    }

    if (
        $resolvedFullPath -ne $repoFullPath -and
        -not $resolvedFullPath.StartsWith($repoFullPath + '\', [System.StringComparison]::OrdinalIgnoreCase)
    ) {
        throw "Review path '$Path' resolves outside the repository root."
    }

    if ($resolvedFullPath -eq $repoFullPath) {
        throw "Review path '$Path' resolves to the repository root, not a file."
    }

    $relative = $resolvedFullPath.Substring($repoFullPath.Length + 1)
    return $relative.Replace("\", "/")
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
                $_ -notmatch '^\.tmp-review-packages[\\/]' -and
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
            $_ -notmatch '^\.tmp-review-packages[\\/]' -and
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
        $tracked = @(& git ls-files -- $RelativePath 2>$null)
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        return ($tracked | Where-Object { $_ -eq $RelativePath }).Count -gt 0
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
            $patch = @(& git -c core.safecrlf=false diff --unified=3 --no-ext-diff HEAD -- $RelativePath 2>$null)
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

function Get-ReviewPatchUnits {
    param(
        [string]$RepoRoot,
        [string]$RelativePath,
        [int]$MaxPatchLines = 300
    )

    $patch = Get-ReviewPatch -RepoRoot $RepoRoot -RelativePath $RelativePath
    if ([string]::IsNullOrWhiteSpace($patch)) {
        return @()
    }

    $lines = $patch -split "`r?`n"
    if ($lines.Count -le $MaxPatchLines) {
        return @(
            [PSCustomObject]@{
                File       = $RelativePath
                Display    = $RelativePath
                Patch      = $patch
                LineCount  = $lines.Count
                SplitCount = 1
            }
        )
    }

    $firstHunkIndex = -1
    for ($lineIndex = 0; $lineIndex -lt $lines.Count; $lineIndex++) {
        if ($lines[$lineIndex] -like '@@*') {
            $firstHunkIndex = $lineIndex
            break
        }
    }

    $headerLines = if ($firstHunkIndex -gt 0) {
        @($lines[0..($firstHunkIndex - 1)])
    }
    else {
        @()
    }

    if ($firstHunkIndex -lt 0) {
        return @(
            [PSCustomObject]@{
                File       = $RelativePath
                Display    = $RelativePath
                Patch      = $patch
                LineCount  = $lines.Count
                SplitCount = 1
            }
        )
    }

    $hunks = [System.Collections.Generic.List[object]]::new()
    $currentHunk = [System.Collections.Generic.List[string]]::new()
    for ($lineIndex = $firstHunkIndex; $lineIndex -lt $lines.Count; $lineIndex++) {
        $line = $lines[$lineIndex]
        if ($line -like '@@*' -and $currentHunk.Count -gt 0) {
            $hunks.Add(@($currentHunk.ToArray()))
            $currentHunk.Clear()
        }
        $currentHunk.Add($line)
    }
    if ($currentHunk.Count -gt 0) {
        $hunks.Add(@($currentHunk.ToArray()))
    }

    $chunks = [System.Collections.Generic.List[object]]::new()
    $currentChunk = [System.Collections.Generic.List[string]]::new()
    $currentLineCount = $headerLines.Count
    $maxChunkBodyLines = [Math]::Max(1, $MaxPatchLines - $headerLines.Count)

    foreach ($hunk in $hunks) {
        $hunkLines = @($hunk)
        $wouldOverflow = $currentChunk.Count -gt 0 -and (($currentLineCount + $hunkLines.Count) -gt $MaxPatchLines)

        if ($wouldOverflow) {
            $chunks.Add(@($currentChunk.ToArray()))
            $currentChunk.Clear()
            $currentLineCount = $headerLines.Count
        }

        if (($headerLines.Count + $hunkLines.Count) -gt $MaxPatchLines -and $currentChunk.Count -eq 0) {
            $hunkHeader = $hunkLines[0]
            $hunkBody = if ($hunkLines.Count -gt 1) { @($hunkLines[1..($hunkLines.Count - 1)]) } else { @() }
            if ($hunkBody.Count -eq 0) {
                $chunks.Add(@($hunkHeader))
                $currentLineCount = $headerLines.Count
                continue
            }

            $maxBodyLinesPerSplit = [Math]::Max(1, $maxChunkBodyLines - 1)
            for ($bodyIndex = 0; $bodyIndex -lt $hunkBody.Count; $bodyIndex += $maxBodyLinesPerSplit) {
                $endIndex = [Math]::Min($bodyIndex + $maxBodyLinesPerSplit - 1, $hunkBody.Count - 1)
                $bodySlice = @($hunkBody[$bodyIndex..$endIndex])
                $chunks.Add(@($hunkHeader) + $bodySlice)
            }
            $currentLineCount = $headerLines.Count
            continue
        }

        foreach ($line in $hunkLines) {
            $currentChunk.Add($line)
        }
        $currentLineCount = $headerLines.Count + $currentChunk.Count
    }

    if ($currentChunk.Count -gt 0) {
        $chunks.Add(@($currentChunk.ToArray()))
    }

    $splitCount = $chunks.Count
    $units = [System.Collections.Generic.List[object]]::new()
    for ($chunkIndex = 0; $chunkIndex -lt $chunks.Count; $chunkIndex++) {
        $chunkLines = @($chunks[$chunkIndex])
        $display = if ($splitCount -gt 1) {
            "{0} (chunk {1}/{2})" -f $RelativePath, ($chunkIndex + 1), $splitCount
        }
        else {
            $RelativePath
        }
        $unitPatch = @($headerLines + $chunkLines) -join "`n"
        $units.Add([PSCustomObject]@{
                File       = $RelativePath
                Display    = $display
                Patch      = $unitPatch
                LineCount  = ($headerLines.Count + $chunkLines.Count)
                SplitCount = $splitCount
            })
    }

    return @($units)
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
    foreach ($candidate in $docCandidates | Select-Object -Unique) {
        if (-not $docs.Contains($candidate)) {
            $docs.Add($candidate)
        }
    }

    return @($docs)
}

function Get-ReviewPatchUnitsForFiles {
    param(
        [string]$RepoRoot,
        [string[]]$Files,
        [int]$MaxDiffLines = 300
    )

    $units = [System.Collections.Generic.List[object]]::new()
    foreach ($file in $Files) {
        foreach ($unit in (Get-ReviewPatchUnits -RepoRoot $RepoRoot -RelativePath $file -MaxPatchLines $MaxDiffLines)) {
            $units.Add($unit)
        }
    }

    return @($units)
}

function Split-ReviewUnitGroups {
    param(
        [object[]]$Units,
        [int]$MaxFilesPerPackage = 3,
        [int]$MaxDiffLines = 300
    )

    $groups = [System.Collections.Generic.List[object]]::new()
    $currentGroup = [System.Collections.Generic.List[object]]::new()
    $currentDiffLines = 0

    foreach ($unit in $Units) {
        if ($unit.SplitCount -gt 1) {
            if ($currentGroup.Count -gt 0) {
                $groups.Add(@($currentGroup.ToArray()))
                $currentGroup.Clear()
                $currentDiffLines = 0
            }
            $groups.Add(@($unit))
            continue
        }

        $wouldOverflowFiles = $currentGroup.Count -ge $MaxFilesPerPackage
        $wouldOverflowLines = $currentGroup.Count -gt 0 -and (($currentDiffLines + $unit.LineCount) -gt $MaxDiffLines)

        if ($currentGroup.Count -gt 0 -and ($wouldOverflowFiles -or $wouldOverflowLines)) {
            $groups.Add(@($currentGroup.ToArray()))
            $currentGroup.Clear()
            $currentDiffLines = 0
        }

        $currentGroup.Add($unit)
        $currentDiffLines += $unit.LineCount
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
    $units = Get-ReviewPatchUnitsForFiles `
        -RepoRoot $RepoRoot `
        -Files $scopedFiles `
        -MaxDiffLines $MaxDiffLines
    if ($units.Count -eq 0) {
        throw "No changed diff units found for the requested review scope."
    }
    $groups = Split-ReviewUnitGroups `
        -Units $units `
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
        $groupFiles = @($group | ForEach-Object { $_.File } | Select-Object -Unique)
        $hasSplitUnits = ($group | Where-Object { $_.Display -match '\(chunk \d+/\d+\)$' }).Count -gt 0
        $contracts = Resolve-ReviewContractDocs -Files $groupFiles -ExplicitContractDocs $ContractDocs
        $diffStats = if ($groupFiles.Count -gt 0) {
            Push-Location $RepoRoot
            try {
                @(& git -c core.safecrlf=false diff --stat HEAD -- @($groupFiles) 2>$null) -join "`n"
            }
            finally {
                Pop-Location
            }
        }
        else {
            ""
        }

        $patches = foreach ($unit in $group) {
            $unit.Patch
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

        foreach ($unit in $group) {
            $packageBody += "- $($unit.Display)"
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
                Files        = $groupFiles
                Displays     = @($group | ForEach-Object { $_.Display })
                ContractDocs = $contracts
                HasSplitUnits = $hasSplitUnits
                Narrowable   = ($groupFiles.Count -gt 1 -or $hasSplitUnits)
                Index        = $index + 1
                Total        = $packageCount
            })
    }

    return @($packages)
}
