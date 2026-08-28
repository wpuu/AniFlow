$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "AniFlow local environment is not prepared. Run scripts\setup_aniflow_windows.ps1 first."
}

Write-Host "[AniFlow] Running Python tests..."
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { throw "Python tests failed." }

Write-Host "[AniFlow] Running strict frontend typecheck + build..."
Push-Location (Join-Path $RepoRoot "apps\grok-frontend")
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend verification/build failed." }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "[AniFlow] Local verification passed."
