$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot
Write-Host "[AniFlow] Directory: $RepoRoot"

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[AniFlow] Creating local Python environment..."
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    }
    else {
        throw "Install Python 3.11 or later and retry."
    }
}
if (-not (Test-Path $Python)) { throw "Python virtual environment creation failed." }
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw "AniFlow requires Python 3.11 or later." }

Write-Host "[AniFlow] Installing local Python components..."
& $Python -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

$FrontendDir = Join-Path $RepoRoot "apps\grok-frontend"
$FrontendIndex = Join-Path $FrontendDir "dist\index.html"
$PrebuiltManifest = Join-Path $RepoRoot "prebuilt_frontend.json"
if (Test-Path $PrebuiltManifest) {
    if (-not (Test-Path $FrontendIndex)) { throw "Prebuilt frontend is missing; re-download the complete bundle." }
    $Manifest = Get-Content -LiteralPath $PrebuiltManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $Expected = [string]($Manifest.frontend_sha256)
    if ($Expected -notmatch '^[a-fA-F0-9]{64}$') { throw "Invalid prebuilt manifest SHA-256." }
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $HashBytes = $Hasher.ComputeHash([System.IO.File]::ReadAllBytes($FrontendIndex))
    $Actual = [System.BitConverter]::ToString($HashBytes).Replace("-", "")
}
finally {
    $Hasher.Dispose()
}
    if ($Actual -ine $Expected) { throw "Prebuilt frontend checksum mismatch. Do not launch." }
    Write-Host "[AniFlow] CI prebuilt frontend validated; Node/npm is NOT required."
}
else {
    Push-Location $FrontendDir
    try {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "npm was not found. Install Node.js/npm, or use the verified CI Windows bundle."
        }
        if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
            Write-Host "[AniFlow] Installing frontend dependencies..."
            & npm ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
        }
        Write-Host "[AniFlow] Type-checking and building frontend..."
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally {
        Pop-Location
    }
}

Write-Host "[AniFlow] Local setup complete."
Write-Host "[AniFlow] Text-to-video does NOT require S3/R2. For image uploads, configure public media separately."
Write-Host "[AniFlow] Start by double-clicking 启动AniFlow.cmd."
