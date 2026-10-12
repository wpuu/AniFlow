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

    $ProbeFile = Join-Path $PSScriptRoot "aniflow_runtime_probe.py"
    if (-not (Test-Path -LiteralPath $ProbeFile -PathType Leaf)) {
        throw "AniFlow runtime inspection script missing from the Windows package."
    }
    $RequirementsJson = & $Python $ProbeFile requirements $RepoRoot
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
    $Health = & $Python $ProbeFile health
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
    $Health = & $Python $ProbeFile health
    if ($LASTEXITCODE -ne 0 -or @($Health) -notcontains "ANIFLOW_SHARED_RUNTIME_HEALTH_OK") {
        throw "AniFlow dependency health check failed. No successful install stamp was written."
    }
    [System.IO.File]::WriteAllText($Stamp, $Fingerprint + [Environment]::NewLine)
    Write-Host "PASS_ANIFLOW_SHARED_RUNTIME_INITIALIZED"
    return $Python
}
