param(
    [ValidateSet('critic', 'reviewer')]
    [string]$Role = 'critic',
    [string]$ScopeName = 'current-slice',
    [string]$Focus = '',
    [string[]]$Files = @(),
    [string[]]$ContractDocs = @(),
    [int]$MaxFilesPerPackage = 3,
    [int]$MaxDiffLines = 300
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

. (Join-Path $PSScriptRoot "lib\review-package.ps1")

$packages = New-ReviewPackages `
    -RepoRoot $repoRoot `
    -Role $Role `
    -ScopeName $ScopeName `
    -Focus $Focus `
    -Files $Files `
    -ContractDocs $ContractDocs `
    -MaxFilesPerPackage $MaxFilesPerPackage `
    -MaxDiffLines $MaxDiffLines

foreach ($package in $packages) {
    Write-Output $package.Path
}
