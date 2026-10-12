$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot
Write-Host "[AniFlow] Directory: $RepoRoot"

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

$RuntimeLoader = Join-Path $PSScriptRoot "aniflow_shared_runtime.ps1"
if (-not (Test-Path -LiteralPath $RuntimeLoader -PathType Leaf)) {
    throw "AniFlow shared runtime helper is missing. Download the complete release."
}
. $RuntimeLoader
$Python = Get-AniFlowRuntimePython -RepoRoot $RepoRoot -AllowInstall
$env:PYTHONPATH = Join-Path $RepoRoot "src"
& $Python -c "import aniflow,pathlib,sys;sys.exit(0 if pathlib.Path(aniflow.__file__).resolve()==(pathlib.Path.cwd()/'src/aniflow/__init__.py').resolve() else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "AniFlow Python import is not bound to the current release source."
}
Write-Host "PASS_ANIFLOW_CURRENT_SOURCE_BOUND_SHARED_RUNTIME"
Write-Host "[AniFlow] Local setup complete."
Write-Host "[AniFlow] Update checker: double-click the new package's update launcher."
if ($env:ANIFLOW_SKIP_UPDATE_CHECK -ne "1") {
    $UpdateCheck = Join-Path $PSScriptRoot "check_aniflow_update_windows.ps1"
    if (Test-Path -LiteralPath $UpdateCheck -PathType Leaf) {
        Write-Host "[AniFlow] Checking whether a newer verified build exists (non-blocking)..."
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UpdateCheck -Mode Check -NoBrowser
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[AniFlow] Update check unavailable; this does not affect installation."
        }
    }
}
Write-Host "[AniFlow] Text-to-video does NOT require S3/R2. For image uploads, configure public media separately."
Write-Host "[AniFlow] Start by double-clicking 启动AniFlow.cmd."
