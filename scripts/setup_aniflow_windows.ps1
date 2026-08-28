$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

Write-Host "[AniFlow] Repository: $RepoRoot"

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[AniFlow] Creating local Python virtual environment..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    }
    else {
        throw "Python 3.11+ was not found."
    }
}

Write-Host "[AniFlow] Installing/updating local Python package..."
& $Python -m pip install -e .

$FrontendDir = Join-Path $RepoRoot "apps\grok-frontend"
Push-Location $FrontendDir
try {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Install Node.js/npm before building the frontend."
    }

    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "[AniFlow] Installing frontend dependencies..."
        & npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    }

    Write-Host "[AniFlow] Type-checking and building the single-file frontend..."
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "[AniFlow] Local setup complete."
Write-Host "[AniFlow] Next: copy .env.example to .env and fill R2/S3 settings as needed."
Write-Host "[AniFlow] Start with: powershell -ExecutionPolicy Bypass -File scripts\start_aniflow_windows.ps1"
