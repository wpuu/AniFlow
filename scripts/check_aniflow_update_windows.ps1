param(
    [ValidateSet("Check", "Install")]
    [string]$Mode = "Check",
    [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$Repo = "wpuu/AniFlow"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ManifestFile = Join-Path $Root "prebuilt_frontend.json"
$VersionFile = Join-Path $Root "version.json"
$Headers = @{
    "User-Agent" = "AniFlow-Windows-Updater"
    "Accept" = "application/vnd.github+json"
}

function Get-Json([string]$Uri) {
    Invoke-RestMethod -Uri $Uri -Headers $Headers -Method Get -TimeoutSec 8
}

function Get-SHA256([string]$FilePath) {
    $Hash = [System.Security.Cryptography.SHA256]::Create()
    try {
        $Bytes = $Hash.ComputeHash([System.IO.File]::ReadAllBytes($FilePath))
        return [System.BitConverter]::ToString($Bytes).Replace("-", "").ToLowerInvariant()
    }
    finally { $Hash.Dispose() }
}

function Check-ArtifactFiles([string]$Directory, [string]$ExpectedSha,
                              [string]$ExpectedVersion, [string]$ExpectedStage) {
    $MetaFile = Join-Path $Directory "prebuilt_frontend.json"
    $ReleaseFile = Join-Path $Directory "version.json"
    $HtmlFile = Join-Path $Directory "apps\grok-frontend\dist\index.html"
    $Launcher = Join-Path $Directory "启动AniFlow.cmd"
    $Updater = Join-Path $Directory "检查更新AniFlow.cmd"
    foreach ($Path in @($MetaFile, $ReleaseFile, $HtmlFile, $Launcher, $Updater)) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "The verified AniFlow Windows package is incomplete: $Path"
        }
    }
    $Meta = Get-Content -LiteralPath $MetaFile -Encoding UTF8 -Raw | ConvertFrom-Json
    $Release = Get-Content -LiteralPath $ReleaseFile -Encoding UTF8 -Raw | ConvertFrom-Json
    if ($Meta.source_commit -ne $ExpectedSha -or $Meta.app_version -ne $ExpectedVersion -or
        $Meta.release_stage -ne $ExpectedStage -or
        $Release.app_version -ne $ExpectedVersion -or
        $Release.release_stage -ne $ExpectedStage -or
        $Meta.frontend_sha256 -ne (Get-SHA256 $HtmlFile)) {
        throw "AniFlow update rejected: release identity or frontend hash mismatches the verified workflow."
    }
}

try {
    $Pr = Get-Json "https://api.github.com/repos/$Repo/pulls/2"
    if ($Pr.head.repo.full_name -ne $Repo -or
        $Pr.head.ref -ne "audit/2026-10-11-v710-revalidation" -or
        $Pr.state -ne "open") {
        throw "The AniFlow trusted update branch has changed. Update check is not safe."
    }
    $TargetSha = [string]$Pr.head.sha
    if ($TargetSha -notmatch '^[0-9a-f]{40}$') { throw "Invalid latest AniFlow Git SHA." }

    $RunList = Get-Json "https://api.github.com/repos/$Repo/actions/runs?head_sha=$TargetSha&per_page=20"
    $Run = @($RunList.workflow_runs | Where-Object {
        $_.head_sha -eq $TargetSha -and $_.conclusion -eq "success" -and
        $_.status -eq "completed" -and $_.name -eq "CI"
    } | Sort-Object created_at -Descending | Select-Object -First 1)
    if ($Run.Count -eq 0) {
        Write-Host "[AniFlow] Latest source is awaiting a successful Windows build; existing install unchanged."
        exit 0
    }
    $Run = $Run[0]
    $ArtifactList = Get-Json "https://api.github.com/repos/$Repo/actions/runs/$($Run.id)/artifacts?per_page=100"
    $Artifact = $null
    $NewVersion = $null
    $NewStage = $null
    foreach ($Item in @($ArtifactList.artifacts)) {
        if ($Item.expired -or $Item.name -notmatch '^AniFlow-v([0-9]+\.[0-9]+\.[0-9]+)-(P0-[0-9]{3})-Windows-([a-f0-9]{40})$') {
            continue
        }
        if ($Matches[3] -ne $TargetSha) { continue }
        $Artifact = $Item
        $NewVersion = $Matches[1]
        $NewStage = $Matches[2]
        break
    }
    if ($null -eq $Artifact) {
        Write-Host "[AniFlow] No verified Windows update artifact for the current PR head."
        exit 0
    }

    $CurrentSha = ""
    $CurrentVersion = "0.0.0"
    if (Test-Path -LiteralPath $ManifestFile -PathType Leaf) {
        $Current = Get-Content -LiteralPath $ManifestFile -Encoding UTF8 -Raw | ConvertFrom-Json
        $CurrentSha = [string]$Current.source_commit
        if ([string]$Current.app_version -match '^[0-9]+\.[0-9]+\.[0-9]+$') {
            $CurrentVersion = [string]$Current.app_version
        }
    }
    if ([version]$NewVersion -lt [version]$CurrentVersion) {
        throw "Remote version is older than the installed build. Downgrade refused."
    }
    if ($CurrentSha -eq $TargetSha) {
        Write-Host "[AniFlow] Already current: v$NewVersion / build $($TargetSha.Substring(0,12))."
        exit 0
    }
    Write-Host "[AniFlow] Available: v$NewVersion ($NewStage), build $($TargetSha.Substring(0,12))."
    Write-Host "[AniFlow] Verified workflow: $($Run.html_url)"
    if ($Mode -eq "Check") {
        Write-Host "[AniFlow] To update: double-click '检查更新AniFlow.cmd' from THIS folder."
        exit 0
    }

    # Downloading GitHub Actions artifacts anonymously is not guaranteed.
    # Prefer an already-downloaded ZIP, or gh CLI's existing authenticated session.
    $Downloads = Join-Path $env:USERPROFILE "Downloads"
    $Zip = Join-Path $Downloads ($Artifact.name + ".zip")
    $Parent = Split-Path -Parent $Root
    $Stage = Join-Path $Parent ("AniFlow-stage-" + [guid]::NewGuid().ToString("N"))
    $Destination = Join-Path $Parent ("AniFlow-v" + $NewVersion + "-" + $NewStage + "-" + $TargetSha.Substring(0, 12))

    if (Test-Path -LiteralPath $Destination) {
        Check-ArtifactFiles $Destination $TargetSha $NewVersion $NewStage
        Write-Host "[AniFlow] Target version is already installed in $Destination"
    }
    else {
        New-Item -ItemType Directory -Path $Stage -ErrorAction Stop | Out-Null
        try {
            if (Test-Path -LiteralPath $Zip -PathType Leaf) {
                if ([string]$Artifact.digest -notmatch '^sha256:([a-f0-9]{64})$') {
                    throw "Cannot verify downloaded ZIP because GitHub did not report a SHA-256 digest."
                }
                $TrustedDigest = $Matches[1]
                if ((Get-SHA256 $Zip) -ne $TrustedDigest) {
                    throw "Downloaded ZIP differs from the GitHub Actions artifact digest."
                }
                Expand-Archive -LiteralPath $Zip -DestinationPath $Stage
            }
            elseif (Get-Command gh -ErrorAction SilentlyContinue) {
                & gh run download ([string]$Run.id) -R $Repo -n ([string]$Artifact.name) -D $Stage
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "[AniFlow] Authenticated GitHub CLI download unavailable."
                    throw "Open the workflow page and download the Windows ZIP first."
                }
            }
            else {
                Write-Host "[AniFlow] Download required. Use GitHub while signed in:"
                Write-Host "[AniFlow] $($Run.html_url)"
                Write-Host "[AniFlow] Select Artifact: $($Artifact.name)"
                Write-Host "[AniFlow] Save ZIP into: $Zip"
                if (-not $NoBrowser) { Start-Process ([string]$Run.html_url) }
                exit 0
            }

            Check-ArtifactFiles $Stage $TargetSha $NewVersion $NewStage
            Move-Item -LiteralPath $Stage -Destination $Destination -ErrorAction Stop
            Write-Host "[AniFlow] Verified update installed into: $Destination"
        }
        finally {
            if (Test-Path -LiteralPath $Stage) {
                Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    # Never restart the old server automatically: active Agnes submissions
    # only live in the browser and cannot be safely inspected by this updater.
    Write-Host "[AniFlow] Do not restart while a video is submitting."
    Write-Host "[AniFlow] From the NEW folder, first run '首次安装AniFlow.cmd',"
    Write-Host "[AniFlow] then double-click '启动AniFlow.cmd' to switch versions."
    Write-Host "[AniFlow] Browser keys/history stay at http://127.0.0.1:8765."
    if (-not $NoBrowser) { Start-Process explorer.exe -ArgumentList @($Destination) }
}
catch {
    Write-Warning ("AniFlow update check/install did not complete: " + $_.Exception.Message)
    Write-Host "[AniFlow] Current installed files have NOT been overwritten."
    if ($Mode -eq "Install") {
        Write-Host "[AniFlow] Open https://github.com/wpuu/AniFlow/pull/2 to get the latest successful Windows Artifact."
    }
    exit 1
}
