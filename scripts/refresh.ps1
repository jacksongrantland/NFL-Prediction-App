param([switch]$CachedSources, [switch]$Scheduled)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $refreshArgs = @('refresh', '--config', 'config/refresh.local.json')
    if ($CachedSources) { $refreshArgs += '--cached-sources' }
    if ($Scheduled) { $refreshArgs += '--scheduled' }
    & .\.venv\Scripts\nfl.exe @refreshArgs
    if ($LASTEXITCODE -ne 0) { throw 'Refresh failed; inspect data/refresh/runs.' }
} finally { Pop-Location }
