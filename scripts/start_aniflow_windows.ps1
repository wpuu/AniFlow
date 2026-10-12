$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "AniFlow is not installed. First run 首次安装AniFlow.cmd."
}

$FrontendIndex = Join-Path $RepoRoot "apps\grok-frontend\dist\index.html"
$PrebuiltManifest = Join-Path $RepoRoot "prebuilt_frontend.json"
if (-not (Test-Path $FrontendIndex)) {
    if (Test-Path $PrebuiltManifest) {
        throw "Prebuilt frontend missing. Re-download the complete bundle."
    }
    Write-Host "[AniFlow] Frontend missing: building from source..."
    Push-Location (Join-Path $RepoRoot "apps\grok-frontend")
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally {
        Pop-Location
    }
}
if (Test-Path $PrebuiltManifest) {
    $Manifest = Get-Content -LiteralPath $PrebuiltManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $Expected = [string]($Manifest.frontend_sha256)
    if ($Expected -notmatch '^[a-fA-F0-9]{64}$') { throw "Invalid prebuilt checksum metadata." }
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $HashBytes = $Hasher.ComputeHash([System.IO.File]::ReadAllBytes($FrontendIndex))
    $Actual = [System.BitConverter]::ToString($HashBytes).Replace("-", "")
}
finally {
    $Hasher.Dispose()
}
    if ($Actual -ine $Expected) {
        throw "Prebuilt frontend checksum mismatch. Re-download the complete bundle."
    }
}

# Avoid accidentally showing a stale AniFlow service from a previous checkout.
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($listeners) { throw "Port 8765 already occupied; close the previous AniFlow window first." }
}

$Url = "http://127.0.0.1:8765/"
Write-Host "[AniFlow] Starting local Bridge: $Url"
Write-Host "[AniFlow] Keep this window open. Press Ctrl+C to stop."
Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile",
    "-Command",
    "Start-Sleep -Seconds 2; Start-Process '$Url'"
) | Out-Null
& $Python -m aniflow.cli bridge
