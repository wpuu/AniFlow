<#
  AniFlow - 诊断

  双击它，把结果截图发我。它只读不写，不会改任何东西。
#>

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { $OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$root = if ($ScriptDir) { $ScriptDir } elseif ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Line = "=" * 62

function Ok  ($t) { Write-Host "  [OK]   $t" -ForegroundColor Green }
function No  ($t) { Write-Host "  [缺失] $t" -ForegroundColor Red }
function Inf ($t) { Write-Host "         $t" -ForegroundColor DarkGray }

Write-Host ""
Write-Host $Line -ForegroundColor Cyan
Write-Host "  AniFlow 诊断 - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host $Line -ForegroundColor Cyan

# 1. Python
Write-Host ""
Write-Host "1) Python" -ForegroundColor White
$found = $false
foreach ($c in @("python", "py")) {
    try {
        $v = (& $c --version 2>&1 | Out-String).Trim()
        if ($v -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 10) { Ok "$c -> $v"; $found = $true }
            else { No "$c -> $v（需要 3.10 以上）" }
        } else { Inf "$c -> $v" }
    } catch { Inf "$c 不存在" }
}
if (-not $found) {
    No "没有可用的 Python 3.10+"
    Inf "装一次：https://www.python.org/downloads/ （勾选 Add python.exe to PATH）"
}

# 2. 安装目录
Write-Host ""
Write-Host "2) 安装目录" -ForegroundColor White
Inf "本文件所在：$root"
$dest = Join-Path $root "video-studio"
if (Test-Path $dest) {
    Ok "video-studio 存在"
    Get-ChildItem $dest -Directory -ErrorAction SilentlyContinue | ForEach-Object { Inf "  └ $($_.Name)" }
} else {
    No "没有 video-studio 文件夹（说明下载或解压那步没成功）"
}

$app = Get-ChildItem $dest -Directory -ErrorAction SilentlyContinue |
       Where-Object { Test-Path (Join-Path $_.FullName "start.bat") } |
       Select-Object -First 1

if ($app) {
    Ok "找到 start.bat：$($app.FullName)"
} else {
    No "找不到 start.bat"
}

# 3. 配置与补丁
Write-Host ""
Write-Host "3) 配置与补丁" -ForegroundColor White
if ($app) {
    $envFile = Join-Path $app.FullName ".env"
    if (Test-Path $envFile) {
        $n = @(Select-String -Path $envFile -Pattern "^AGNES_API_KEY" -ErrorAction SilentlyContinue).Count
        Ok ".env 存在，配了 $n 个账号"
        if ($n -lt 2) { Inf "  少于 2 个账号，测不出队列是不是按账户隔离" }
    } else { No ".env 不存在（账号没写进去）" }

    $target = Join-Path $app.FullName "core\api\agnes_video.py"
    if (Test-Path $target) {
        if ((Get-Content $target -Raw) -match "queue_rotations") { Ok "队列优化补丁已生效" }
        else { No "补丁没打上（能用，但队列满时换账号会慢 30~60 秒）" }
    } else { No "找不到 agnes_video.py" }

    $venv = Join-Path $app.FullName ".venv\Scripts\python.exe"
    if (Test-Path $venv) { Ok "虚拟环境已建好" }
    else { No "虚拟环境没建（依赖还没装，或 start.bat 没跑起来）" }
}

# 4. 服务
Write-Host ""
Write-Host "4) 服务状态" -ForegroundColor White
$up = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8765" -UseBasicParsing -TimeoutSec 5
    Ok "服务在运行（HTTP $($r.StatusCode)）"
    Inf "浏览器打开：http://localhost:8765"
    $up = $true
} catch {
    No "8765 端口没响应，服务没在跑"
}
if (-not $up -and $app) {
    Inf "手动启动：进 $($app.FullName) 双击 start.bat"
}

# 5. 日志
Write-Host ""
Write-Host "5) 安装日志最后 25 行" -ForegroundColor White
$log = Join-Path $root "安装日志.txt"
if (Test-Path $log) {
    Get-Content $log -Tail 25 | ForEach-Object { Write-Host "   $_" -ForegroundColor DarkGray }
} else {
    No "没有 安装日志.txt（说明安装器是旧版，或从没跑到写日志那步）"
}

Write-Host ""
Write-Host $Line -ForegroundColor Cyan
Write-Host "  把以上内容截图发我" -ForegroundColor White
Write-Host $Line -ForegroundColor Cyan
try { $Host.UI.RawUI.FlushInputBuffer() } catch {}
