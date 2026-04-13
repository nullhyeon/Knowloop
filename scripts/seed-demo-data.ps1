$ErrorActionPreference = "Stop"

param(
    [string]$DataRoot,
    [string]$FixtureRoot,
    [switch]$AllowReset
)

. (Join-Path $PSScriptRoot "lib\resolve-uv.ps1")

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps\api"
$uv = Get-UvCommand

$command = @("run", "python", "-m", "knowloop_api.demo_seed")
if ($AllowReset) {
    $command += "--allow-destructive-reset"
}
if ($DataRoot) {
    $command += @("--data-root", $DataRoot)
}
if ($FixtureRoot) {
    $command += @("--fixture-root", $FixtureRoot)
}

Push-Location $apiRoot
try {
    & $uv @command
}
finally {
    Pop-Location
}
