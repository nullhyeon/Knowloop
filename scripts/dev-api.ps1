$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib\resolve-uv.ps1")

$repoRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $repoRoot "apps\api"
$uv = Get-UvCommand

Push-Location $apiRoot
try {
    & $uv run uvicorn knowloop_api.main:app --app-dir src --reload --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}
