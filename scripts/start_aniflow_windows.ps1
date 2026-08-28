$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "AniFlow local environment is not prepared. Run scripts\setup_aniflow_windows.ps1 first."
}

$FrontendIndex = Join-Path $RepoRoot "apps\grok-frontend\dist\index.html"
if (-not (Test-Path $FrontendIndex)) {
    Write-Host "[AniFlow] Frontend build not found; building now..."
    Push-Location (Join-Path $RepoRoot "apps\grok-frontend")
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally {
        Pop-Location
    }
}

$Url = "http://127.0.0.1:8765/"
Write-Host "[AniFlow] Starting local Bridge at $Url"
Write-Host "[AniFlow] Keep this window open. Press Ctrl+C to stop AniFlow."

# Open the browser shortly after the foreground bridge starts. The helper
# PowerShell process exits immediately after opening the URL.
Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile",
    "-Command",
    "Start-Sleep -Seconds 2; Start-Process '$Url'"
) | Out-Null

& $Python -m aniflow.cli bridge
