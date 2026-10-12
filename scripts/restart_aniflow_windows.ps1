param(
    [switch]$NoBrowser,
    [switch]$ValidateOnly
)
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root
$Port = 8765
$Base = "http://127.0.0.1:$Port"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$ManifestFile = Join-Path $Root "prebuilt_frontend.json"
$IndexFile = Join-Path $Root "apps\grok-frontend\dist\index.html"

Write-Host "AniFlow | Current folder: $Root"
if (-not (Test-Path -LiteralPath $ManifestFile -PathType Leaf)) {
    throw "Missing prebuilt_frontend.json. Download the successful PR #2 Windows Artifact ZIP, NOT the repository main ZIP."
}
if (-not (Test-Path -LiteralPath $IndexFile -PathType Leaf)) {
    throw "Frontend HTML missing. Re-extract the complete Windows Artifact ZIP."
}
$Manifest = Get-Content -LiteralPath $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$Commit = [string]$Manifest.source_commit
$Expected = [string]$Manifest.frontend_sha256
if ($Commit -notmatch '^[0-9a-fA-F]{40}$' -or $Expected -notmatch '^[0-9a-fA-F]{64}$') {
    throw "Invalid AniFlow build manifest. Do not start an unknown version."
}
$Hasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $HashBytes = $Hasher.ComputeHash([System.IO.File]::ReadAllBytes($IndexFile))
    $Actual = [System.BitConverter]::ToString($HashBytes).Replace("-", "")
}
finally {
    $Hasher.Dispose()
}
    if ($Actual -ine $Expected) {
if ($Actual -ine $Expected) {
    throw "Frontend SHA256 mismatch. Do not launch a mixed old/new app. Re-extract a complete ZIP."
}
Write-Host ("AniFlow | Package version: " + $Commit.Substring(0, 12))
Write-Host "AniFlow | Compiled frontend checksum: OK"
if ($ValidateOnly) {
    Write-Host "PASS_ANIFLOW_RESTART_VERSION_VALIDATION_ONLY"
    exit 0
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Write-Host "AniFlow | Python not installed; setting up the current folder."
    & (Join-Path $PSScriptRoot "setup_aniflow_windows.ps1")
    if ($LASTEXITCODE -ne 0) { throw "AniFlow installation failed" }
}
# An existing editable Python install may still point at a different extracted ZIP.
& $Python -c "import aniflow,pathlib,sys;sys.exit(0 if pathlib.Path(aniflow.__file__).resolve()==(pathlib.Path.cwd()/'src/aniflow/__init__.py').resolve() else 7)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "AniFlow | Python still points to a previous extraction; rebinding."
    & $Python -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw "Could not bind Python environment to this AniFlow folder" }
}
if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
    throw "Cannot safely identify port owner: Windows Get-NetTCPConnection is unavailable."
}

# Only kill a positively identified AniFlow bridge, never a foreign service on the same port.
$Owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($ProcessId in $Owners) {
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
    $CommandLine = [string]$ProcessInfo.CommandLine
    $KnownBridge = (
        $CommandLine -match '(?i)(?:-m\s+)?aniflow\.cli\s+bridge(?:\s|$)' -or
        $CommandLine -match '(?i)uvicorn\s+aniflow\.bridge\.app:app(?:\s|$)' -or
        $CommandLine -match '(?i)aniflow\.exe"?\s+bridge(?:\s|$)'
    )
    if (-not $KnownBridge) {
        throw "Port $Port belongs to a process not proven to be AniFlow (PID $ProcessId). No process was killed. Close that program manually."
    }
    Write-Host "AniFlow | Stopping old AniFlow Bridge PID=$ProcessId (no files or browser data deleted)"
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
}
for ($i = 0; $i -lt 30; $i++) {
    $Bound = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $Bound) { break }
    Start-Sleep -Milliseconds 300
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 8765 remains occupied. No unrelated process was stopped."
}

$LogRoot = Join-Path $Root "data\runtime\bridge-restarts"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
$Stdout = Join-Path $LogRoot "stdout-$Stamp.txt"
$Stderr = Join-Path $LogRoot "stderr-$Stamp.txt"
Write-Host "AniFlow | Starting the current folder's loopback Bridge"
$Process = Start-Process -FilePath $Python -ArgumentList @("-m", "aniflow.cli", "bridge") -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr

try {
    $Ready = $false
    for ($i = 0; $i -lt 50; $i++) {
        if ($Process.HasExited) { throw "New AniFlow service exited before readiness. See: $Stderr" }
        try {
            $Version = Invoke-RestMethod -Uri "$Base/api/version?check=$Stamp" -TimeoutSec 2 -Headers @{"Cache-Control"="no-cache"}
            if ($Version.build_type -eq "prebuilt" -and $Version.source_commit -eq $Commit -and $Version.frontend_verified -eq $true) {
                $Ready = $true
                break
            }
            throw "Wrong active AniFlow version on port 8765; refused to open a stale page."
        } catch [System.Net.WebException] {
            Start-Sleep -Milliseconds 350
        }
    }
    if (-not $Ready) { throw "Current AniFlow server did not become ready on port 8765." }
    Write-Host ("AniFlow | ACTIVE build: " + $Commit.Substring(0, 12))
    Write-Host ("AniFlow | URL: " + $Base + "/")
    Write-Host "AniFlow | Browser API Keys, tasks and history were NOT cleared."
    if (-not $NoBrowser) {
        Start-Process "$Base/?v=$($Commit.Substring(0,12))"
    }
    Write-Host "PASS_ANIFLOW_VERIFIED_RESTART_ACTIVE_BUILD"
} catch {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    throw
}
