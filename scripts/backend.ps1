$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & .\.venv\Scripts\nfl.exe serve
    if ($LASTEXITCODE -ne 0) { throw 'Backend exited with an error.' }
} finally { Pop-Location }
