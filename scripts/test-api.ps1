$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib\resolve-uv.ps1")

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps\api"
$uv = Get-UvCommand

Push-Location $apiRoot
try {
    & $uv run pytest
}
finally {
    Pop-Location
}
