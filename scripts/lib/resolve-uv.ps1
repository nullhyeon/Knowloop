function Get-UvCommand {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\AppData\Roaming\Python\Python312\Scripts\uv.exe",
        "$env:USERPROFILE\AppData\Local\Programs\Python\Python312\Scripts\uv.exe",
        "$env:USERPROFILE\AppData\Roaming\uv\bin\uv.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "uv.exe was not found. Install uv or add it to PATH before running this script."
}
