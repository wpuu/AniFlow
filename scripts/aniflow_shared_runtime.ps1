# Shared, non-secret Python dependencies for all AniFlow Windows releases.
# Source code is ALWAYS imported from the running release's own src directory.
$ErrorActionPreference = "Stop"

function Get-AniFlowRuntimePython {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [switch]$AllowInstall
    )
    $LocalData = [Environment]::GetFolderPath("LocalApplicationData")
    if ([string]::IsNullOrWhiteSpace($LocalData)) {
        throw "Windows local application data folder is unavailable."
    }
    $RuntimeDir = Join-Path $LocalData "AniFlow\python-env"
    $Python = Join-Path $RuntimeDir "Scripts\python.exe"
    $Stamp = Join-Path $RuntimeDir "dependencies-sha256.txt"

    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        if (-not $AllowInstall) {
            throw "AniFlow shared Python runtime is not initialized. Run the installer once."
        }
        Write-Host "[AniFlow] First-time shared dependency setup (one environment for all versions)."
        New-Item -ItemType Directory -Path (Split-Path -Parent $RuntimeDir) -Force | Out-Null
        if (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv $RuntimeDir
        }
        elseif (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv $RuntimeDir
        }
        else {
            throw "Python 3.11+ is required for initial AniFlow setup."
        }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
            throw "AniFlow shared Python virtual environment creation failed."
        }
    }

    & $Python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "AniFlow runtime requires Python 3.11 or later." }

    $ReadRequirements = @'
import json, pathlib, sys, tomllib
spec = tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
requirements = sorted(spec["project"]["dependencies"])
print(json.dumps({"requirements": requirements, "python": list(sys.version_info[:2])}, separators=(",", ":")))
'@
    $SpecFile = Join-Path $RepoRoot "pyproject.toml"
    $RequirementsJson = & $Python -c $ReadRequirements $SpecFile
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($RequirementsJson)) {
        throw "Cannot inspect dependency list in current AniFlow source."
    }
    $RequirementData = $RequirementsJson | ConvertFrom-Json
    $Requirements = @($RequirementData.requirements)
    if ($Requirements.Count -lt 1) { throw "AniFlow dependency list is empty." }
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $HashBytes = $Hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes([string]$RequirementsJson))
        $Fingerprint = [System.BitConverter]::ToString($HashBytes).Replace("-", "").ToLowerInvariant()
    }
    finally { $Hasher.Dispose() }

    $CurrentFingerprint = ""
    if (Test-Path -LiteralPath $Stamp -PathType Leaf) {
        $CurrentFingerprint = ([System.IO.File]::ReadAllText($Stamp)).Trim()
    }
    $CheckModules = @'
import importlib.metadata as m
required = ["boto3", "fastapi", "httpx", "pydantic", "pydantic-settings",
            "python-dotenv", "python-multipart", "typer", "uvicorn"]
missing = []
for name in required:
    try:
        m.version(name)
    except m.PackageNotFoundError:
        missing.append(name)
if missing:
    print("ANIFLOW_SHARED_RUNTIME_MISSING")
else:
    print("ANIFLOW_SHARED_RUNTIME_HEALTH_OK")
'@
    $Health = & $Python -c $CheckModules
    $Healthy = $LASTEXITCODE -eq 0 -and @($Health) -contains "ANIFLOW_SHARED_RUNTIME_HEALTH_OK"
    if ($CurrentFingerprint -eq $Fingerprint -and $Healthy) {
        Write-Host "[AniFlow] Reusing existing shared Python dependencies (NO pip)."
        Write-Host "PASS_ANIFLOW_SHARED_RUNTIME_REUSED_NO_PIP"
        return $Python
    }

    if (-not $AllowInstall) {
        throw "AniFlow third-party dependencies changed or were damaged. Run first installation to update them."
    }
    Write-Host "[AniFlow] Installing dependencies once for this requirements set..."
    & $Python -m pip install --disable-pip-version-check @Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Third-party dependency installation failed; existing releases were not modified."
    }
    $Health = & $Python -c $CheckModules
    if ($LASTEXITCODE -ne 0 -or @($Health) -notcontains "ANIFLOW_SHARED_RUNTIME_HEALTH_OK") {
        throw "AniFlow dependency health check failed. No successful install stamp was written."
    }
    [System.IO.File]::WriteAllText($Stamp, $Fingerprint + [Environment]::NewLine)
    Write-Host "PASS_ANIFLOW_SHARED_RUNTIME_INITIALIZED"
    return $Python
}
