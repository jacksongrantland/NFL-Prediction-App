$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & .\.venv\Scripts\ruff.exe check .
    if ($LASTEXITCODE -ne 0) { throw 'Python lint failed.' }
    & .\.venv\Scripts\ruff.exe format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Python formatting failed.' }
    & .\.venv\Scripts\python.exe -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    Push-Location frontend
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend checks/build failed.' }
    } finally { Pop-Location }
} finally { Pop-Location }
