#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PortableRoot = '',
    [string]$AssetDirectory = '',
    [string]$LogDirectory = (Join-Path $PSScriptRoot 'preflight-logs'),
    [switch]$VerifyLargeFileHashes,
    [switch]$LicenseJapanAndMainlandUseConfirmed,
    [switch]$IndependentStopGuardsConfirmed,
    [switch]$PrivateConnectionConfirmed,
    [switch]$HybridUsageCostsConfirmed,
    [string]$HardStopUtc = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$checks = New-Object 'System.Collections.Generic.List[object]'
$artifacts = @(
    [pscustomobject]@{ RelativePath = 'diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors'; Bytes = 20970379616L; Sha256 = 'e889202c41dafb67b10d67b97f0d8541508036a6090af23425a5c2615d03c47a' },
    [pscustomobject]@{ RelativePath = 'text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'; Bytes = 15687142551L; Sha256 = '35a88d51044231fe332301d7a62aa81e3f2cba62febeb446e2c1e3e0ef76f2c6' },
    [pscustomobject]@{ RelativePath = 'vae\minimax_h3_video_vae_int8_convrot.safetensors'; Bytes = 2811065184L; Sha256 = '52a2c8c73583c86e4f41cdcce3a6ad0ea562987bc0bf3d60a0cef5f5c8e60c0e' },
    [pscustomobject]@{ RelativePath = 'vae\minimax_h3_audio_vae_fp32.safetensors'; Bytes = 605254808L; Sha256 = '8e505d95dd1561d47abd43d4238fd40d9bb1ae9e147ed0a4cba778d76ae4db48' }
)
$portable = [pscustomobject]@{
    FileName = 'ComfyUI_windows_portable_nvidia.7z'
    Bytes = 2018444114L
    Sha256 = '496afd18790ec685d99ebba2edf200d7371a29fbdd3a992bb0f4f52f244a6874'
    Url = 'https://github.com/Comfy-Org/ComfyUI/releases/download/v0.42.1/ComfyUI_windows_portable_nvidia.7z'
}

function Add-Check([string]$Name, [string]$Status, $Detail) {
    $checks.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
    Write-Host ('[{0}] {1}' -f $Status, $Name)
}

function Check-PinnedFile([string]$Path, [long]$Bytes, [string]$Sha256, [bool]$HashNow) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Add-Check $Path 'Blocked' 'Pinned file is absent; nothing was downloaded.'
        return
    }
    $file = Get-Item -LiteralPath $Path
    if ($file.Length -ne $Bytes) {
        Add-Check $Path 'Blocked' @{ ExpectedBytes = $Bytes; ActualBytes = $file.Length }
        return
    }
    if (-not $HashNow) {
        Add-Check $Path 'NotChecked' 'Size matches; SHA256 requires VerifyLargeFileHashes.'
        return
    }
    $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -eq $Sha256) {
        Add-Check $Path 'Pass' @{ Bytes = $file.Length; Sha256 = $actualHash }
    } else {
        Add-Check $Path 'Blocked' @{ ExpectedSha256 = $Sha256; ActualSha256 = $actualHash }
    }
}

try {
    Add-Check 'ExecutionMode' 'Pass' 'Diagnostics only: no downloads, installs, driver updates, registration, server start, or video submission.'
    Add-Check 'WindowsX64' $(if ([Environment]::Is64BitOperatingSystem -and [Environment]::OSVersion.Platform -eq 'Win32NT') { 'Pass' } else { 'Blocked' }) ([Environment]::OSVersion.VersionString)
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $computer = Get-CimInstance -ClassName Win32_ComputerSystem
    $ramGiB = [math]::Round([double]$computer.TotalPhysicalMemory / 1GB, 2)
    Add-Check 'RAM64GiBClass' $(if ($ramGiB -ge 63) { 'Pass' } else { 'Blocked' }) @{ TotalGiB = $ramGiB; FreeGiB = [math]::Round([double]$os.FreePhysicalMemory * 1KB / 1GB, 2); Rule = '63 GiB observed tolerance for a nominal 64 GiB bundle; not an H3 minimum specification.' }

    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    $smiPath = if ($smi) { $smi.Source } else { Join-Path $env:SystemRoot 'System32\nvidia-smi.exe' }
    if (-not (Test-Path -LiteralPath $smiPath -PathType Leaf)) {
        Add-Check 'GPUAndDriver' 'Blocked' 'nvidia-smi.exe was not found; do not auto-update the managed graphics driver.'
    } else {
        $gpuLines = @(& $smiPath '--query-gpu=name,driver_version,memory.total,memory.free' '--format=csv,noheader,nounits' 2>$null)
        if ($LASTEXITCODE -ne 0 -or $gpuLines.Count -ne 1) {
            Add-Check 'GPUAndDriver' 'Blocked' 'Expected one readable GPU; nvidia-smi failed or returned another GPU count.'
        } else {
            $gpu = $gpuLines[0] -split '\s*,\s*'
            $l4 = $gpu[0] -match '^NVIDIA L4($|[- ])'
            $memoryMiB = [double]::Parse($gpu[2], [Globalization.CultureInfo]::InvariantCulture)
            $driverMajor = [int](($gpu[1] -split '\.')[0])
            Add-Check 'L4Nominal24GiB' $(if ($l4 -and $memoryMiB -ge 22000 -and $memoryMiB -le 26000) { 'Pass' } else { 'Blocked' }) @{ Name = $gpu[0]; ReportedMiB = $memoryMiB; FreeMiB = $gpu[3]; Rule = 'Allows display/virtualization reservations; excludes 12 GiB fractional bundles.' }
            Add-Check 'NvidiaDriverR580OrNewer' $(if ($driverMajor -ge 580) { 'Pass' } else { 'Blocked' }) @{ DriverVersion = $gpu[1]; RequiredBranch = 580 }
        }
    }

    foreach ($gate in @(
        @{ Name = 'LicenseJapanAndMainlandUse'; Value = $LicenseJapanAndMainlandUseConfirmed.IsPresent },
        @{ Name = 'IndependentStopGuards'; Value = $IndependentStopGuardsConfirmed.IsPresent },
        @{ Name = 'PrivateConnection'; Value = $PrivateConnectionConfirmed.IsPresent },
        @{ Name = 'HybridUsageCosts'; Value = $HybridUsageCostsConfirmed.IsPresent }
    )) {
        Add-Check $gate.Name $(if ($gate.Value) { 'Attested' } else { 'Blocked' }) 'Operator attestation only; this script does not verify the AWS account or cloud protection.'
    }
    if ($HardStopUtc) {
        $stopTime = [datetime]::ParseExact($HardStopUtc, "yyyy-MM-dd'T'HH:mm:ss'Z'", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal)
        $minutesLeft = [math]::Round(($stopTime - [datetime]::UtcNow).TotalMinutes, 1)
        Add-Check 'FixedStopDeadline' $(if ($minutesLeft -gt 0) { 'Attested' } else { 'Blocked' }) @{ Utc = $HardStopUtc; MinutesRemaining = $minutesLeft; Rule = 'Report only; never extends or creates a stop guard.' }
    } else {
        Add-Check 'FixedStopDeadline' 'Blocked' 'Supply the already armed absolute UTC deadline; not a new relative timer.'
    }

    $service = Get-Service -Name AmazonSSMAgent -ErrorAction SilentlyContinue
    Add-Check 'SSMAgentService' $(if ($service -and $service.Status -eq 'Running') { 'Pass' } else { 'Blocked' }) $(if ($service) { [string]$service.Status } else { 'Not installed; no installation or registration attempted.' })
    Add-Check 'SSMCloudOnlineAndPrivateTunnel' 'NotChecked' 'Requires authenticated console evidence for the correct hybrid node and a real local private tunnel; never read registration keys into logs.'

    if ($AssetDirectory) {
        Check-PinnedFile (Join-Path $AssetDirectory $portable.FileName) $portable.Bytes $portable.Sha256 $VerifyLargeFileHashes.IsPresent
    } else {
        Add-Check 'PinnedPortableArchive' 'NotChecked' 'AssetDirectory not supplied; exact release metadata is recorded below.'
    }
    if ($PortableRoot) {
        $comfy = Join-Path $PortableRoot 'ComfyUI'
        $corePins = @{
            'main.py' = '226a90fdd2cb0942c587e60ae292cddcebd8f6173224e3b91a80ab0efafa93ef'
            'comfyui_version.py' = '883aa406426f07743ad7386afe871050b2a3c3f53d7442684299821bd7cc32a6'
            'comfy\cli_args.py' = '9fa1867311954525344a2d6a61c1408ac9785e5f021f88d4f726826b88ec4a0a'
            'requirements.txt' = 'be1b15fd2f8ea459609c2e62d573ab862f53443023316ba494b4190af50bc028'
        }
        foreach ($relative in $corePins.Keys) {
            $corePath = Join-Path $comfy $relative
            $match = (Test-Path -LiteralPath $corePath -PathType Leaf) -and ((Get-FileHash -LiteralPath $corePath -Algorithm SHA256).Hash.ToLowerInvariant() -eq $corePins[$relative])
            Add-Check ('PinnedCore:' + $relative) $(if ($match) { 'Pass' } else { 'Blocked' }) 'Exact raw bytes from ComfyUI v0.42.1 commit; does not attest every installed file.'
        }
        foreach ($artifact in $artifacts) {
            Check-PinnedFile (Join-Path (Join-Path $comfy 'models') $artifact.RelativePath) $artifact.Bytes $artifact.Sha256 $VerifyLargeFileHashes.IsPresent
        }
        $python = Join-Path $PortableRoot 'python_embeded\python.exe'
        if (Test-Path -LiteralPath $python -PathType Leaf) {
            $probe = 'import json,importlib.metadata as m,torch; print(json.dumps({''python'':__import__(''sys'').version.split()[0],''torch'':torch.__version__,''cuda_runtime'':torch.version.cuda,''cuda_available'':torch.cuda.is_available(),''capability'':torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None,''comfy_kitchen'':m.version(''comfy-kitchen''),''workflow_templates'':m.version(''comfyui-workflow-templates'')}))'
            $probeOutput = @(& $python '-I' '-B' '-c' $probe 2>$null)
            if ($LASTEXITCODE -eq 0) {
                $runtime = $probeOutput[-1] | ConvertFrom-Json
                $runtimeOk = $runtime.cuda_available -and $runtime.cuda_runtime -match '^13\.' -and $runtime.comfy_kitchen -eq '0.2.39' -and $runtime.workflow_templates -eq '0.11.89'
                Add-Check 'PortableCudaRuntime' $(if ($runtimeOk) { 'Pass' } else { 'Blocked' }) $runtime
            } else {
                Add-Check 'PortableCudaRuntime' 'Blocked' 'Embedded Python import probe failed; no packages were installed or upgraded.'
            }
        } else {
            Add-Check 'PortableCudaRuntime' 'Blocked' 'Embedded Python is absent; no installation attempted.'
        }
        $driveName = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($PortableRoot)).TrimEnd('\').TrimEnd(':')
        $drive = Get-PSDrive -Name $driveName -PSProvider FileSystem
        Add-Check 'WorkingDiskHeadroom' $(if ($drive.Free -ge 20GB) { 'Pass' } else { 'Blocked' }) @{ FreeGiB = [math]::Round($drive.Free / 1GB, 2); Rule = '20 GiB operational headroom after staging; model and archive storage must be added before staging. Not an official minimum.' }
    } else {
        Add-Check 'PinnedComfyAndModelFiles' 'NotChecked' 'PortableRoot not supplied; installed runtime, disk headroom and model hashes are unverified.'
    }
    $listeners = @(Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue)
    $unsafe = @($listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') })
    Add-Check 'ComfyLoopbackOnly' $(if ($unsafe.Count) { 'Blocked' } elseif ($listeners.Count) { 'Pass' } else { 'NotChecked' }) 'Inspects local port only; no server started and no HTTP/video request made.'
    Add-Check 'OfficialI2VWorkflowValidated' 'NotChecked' 'Exact official workflow export, model scan/optional LoRA, first-frame path, duration grid, resolution and API schema still require validation. Never fabricate prompt inputs.'
} catch {
    Add-Check 'DiagnosticFailure' 'Blocked' @{ ErrorType = $_.Exception.GetType().Name; Category = [string]$_.CategoryInfo.Category }
}

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$reportPath = Join-Path $LogDirectory ('h3-preflight-' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.json')
$report = [ordered]@{
    Utc = [datetime]::UtcNow.ToString('o')
    Mode = 'DiagnosticOnly'
    RealVideoGenerated = $false
    DeploymentReady = $false
    ComfyTag = 'v0.42.1'
    ComfyCommit = '63be2f9b82ad0dac88a7ceaa28a9cf3154125a18'
    Portable = $portable
    ModelRevision = 'e5eb578a89295337b8ff433a035929ce0279e0b6'
    Models = $artifacts
    SsmSetupOfficialUrl = 'https://amazon-ssm-ap-northeast-1.s3.ap-northeast-1.amazonaws.com/latest/windows_amd64/ssm-setup-cli.exe'
    Checks = @($checks.ToArray())
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Host ('Diagnostic report: ' + $reportPath)
Write-Host 'No deployment or real generation was performed. Remaining checks require explicit operator verification.'
if (@($checks | Where-Object Status -eq 'Blocked').Count) { exit 2 }
exit 0
