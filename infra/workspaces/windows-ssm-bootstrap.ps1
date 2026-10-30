#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][guid]$ActivationId,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9+/=._-]{8,256}$')][string]$ActivationCode,
    [ValidateSet('ap-northeast-1')][string]$Region = 'ap-northeast-1',
    [string]$LogDirectory = (Join-Path $env:ProgramData 'AniFlow-H3\bootstrap')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-NewHybridNode {
    $service = Get-Service -Name AmazonSSMAgent -ErrorAction SilentlyContinue
    $registration = Join-Path $env:ProgramData 'Amazon\SSM\InstanceData\registration'
    if ($service -or (Test-Path -LiteralPath $registration)) {
        throw 'Existing SSM installation or registration; automatic overwrite is prohibited.'
    }
}

function Assert-TrustedSetup([string]$Path) {
    $signature = Get-AuthenticodeSignature -FilePath $Path
    if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)(?:CN|O)="?Amazon\.com Services LLC"?(?:,|$)') {
        throw 'Setup signature or Amazon publisher verification failed.'
    }
}

$report = [ordered]@{
    Utc = [datetime]::UtcNow.ToString('o')
    Region = $Region
    RegistrationCommandSucceeded = $false
    AgentRunning = $false
    Gpu = @()
    RealVideoGenerated = $false
    ErrorType = $null
}
$downloadDirectory = $null
$setup = $null
$exitCode = 2
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
    Assert-NewHybridNode
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    $downloadDirectory = Join-Path $LogDirectory ('setup-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $downloadDirectory | Out-Null
    $setup = Join-Path $downloadDirectory 'ssm-setup-cli.exe'
    $url = "https://amazon-ssm-$Region.s3.$Region.amazonaws.com/latest/windows_amd64/ssm-setup-cli.exe"
    Invoke-WebRequest -Uri $url -OutFile $setup -UseBasicParsing -TimeoutSec 60
    Assert-TrustedSetup $setup
    # Installer output is discarded because native diagnostics may contain activation data.
    & $setup '-register' "-activation-code=$ActivationCode" "-activation-id=$ActivationId" "-region=$Region" *> $null
    if ($LASTEXITCODE -ne 0) { throw 'SSM registration command failed; inspect cloud state before retrying.' }
    $report.RegistrationCommandSucceeded = $true
    $service = Get-Service -Name AmazonSSMAgent
    $service.WaitForStatus('Running', [timespan]::FromSeconds(30))
    $report.AgentRunning = $true
    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    $smiPath = if ($smi) { $smi.Source } else { Join-Path $env:SystemRoot 'System32\nvidia-smi.exe' }
    if (Test-Path -LiteralPath $smiPath -PathType Leaf) {
        $report.Gpu = @(& $smiPath '--query-gpu=name,driver_version,memory.total,memory.free' '--format=csv,noheader,nounits' 2>$null)
        if ($LASTEXITCODE -ne 0) { $report.Gpu = @() }
    }
    $exitCode = 0
} catch {
    # Do not persist exception messages, native output, activation values, or registration files.
    $report.ErrorType = $_.Exception.GetType().Name
} finally {
    $ActivationCode = ''
    if ($setup -and (Test-Path -LiteralPath $setup -PathType Leaf)) { Remove-Item -LiteralPath $setup -Force }
    if ($downloadDirectory -and (Test-Path -LiteralPath $downloadDirectory -PathType Container)) {
        Remove-Item -LiteralPath $downloadDirectory
    }
}
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$reportPath = Join-Path $LogDirectory ('ssm-bootstrap-' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.json')
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Host ('Bootstrap report: ' + $reportPath)
Write-Host 'Cloud Online state and private tunnel still require independent verification.'
exit $exitCode
