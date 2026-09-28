<#
  AniFlow - 视频工作台一键安装

  做三件事：
    1. 下载 lcy362/agnes-video-generator（MIT，436★，持续更新）
    2. 打上我们的优化补丁：队列满时先把其余账号试一遍，再退避
    3. 写好多 Key 配置并启动

  为什么不是自己写：这个项目已经有 Web 界面、多 Key 轮换、断点续跑、
  22 语言、完整测试。我们该做的是在它上面叠 IP / 选题 / 事实核验，
  而不是重造一遍它的视频提交层。
#>

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { $OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Version = "v7.0.4"
$Zip     = "https://github.com/lcy362/agnes-video-generator/archive/refs/tags/$Version.zip"
$Line    = "=" * 60

function Say  ($t) { Write-Host $t }
function Ok   ($t) { Write-Host $t -ForegroundColor Green }
function Warn ($t) { Write-Host $t -ForegroundColor Yellow }
function Bad  ($t) { Write-Host $t -ForegroundColor Red }

Write-Host ""
Write-Host $Line -ForegroundColor Cyan
Write-Host "  AniFlow 视频工作台 - 一键安装" -ForegroundColor Cyan
Write-Host $Line -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------- Python
Say "[1/5] 检查 Python ..."
$py = $null
foreach ($c in @("python", "py")) {
    try {
        $v = & $c --version 2>&1
        if ($v -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 10) { $py = $c; break }
            else { Warn "      找到 $v，但这个项目需要 3.10 以上" }
        }
    } catch {}
}
if (-not $py) {
    Bad "      没找到 Python 3.10 以上。"
    Say ""
    Say "      请先装 Python，只用装一次："
    Say "        https://www.python.org/downloads/"
    Say ""
    Warn "      装的时候务必勾选最下面那个 'Add python.exe to PATH'，"
    Warn "      否则装完还是找不到。装完重新双击本文件即可。"
    return
}
Ok  "      $(& $py --version 2>&1)"

# ---------------------------------------------------------------- 下载
$root = if ($ScriptDir) { $ScriptDir } elseif ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$dest = Join-Path $root "video-studio"
$app  = Join-Path $dest "agnes-video-generator-$($Version.TrimStart('v'))"

Say ""
Say "[2/5] 下载视频工作台 $Version ..."
if (Test-Path $app) {
    Ok "      已存在，跳过下载"
} else {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    $tmp = Join-Path $env:TEMP "avg-$Version.zip"
    Say "      从 GitHub 拉取（约 20 MB，取决于网速）..."
    try {
        Invoke-WebRequest -Uri $Zip -OutFile $tmp -UseBasicParsing -TimeoutSec 600
    } catch {
        Bad "      下载失败：$($_.Exception.Message)"
        Say ""
        Say "      如果是网络问题，可以手动下载这个链接，"
        Say "      解压到 $dest 下面，再重新双击本文件："
        Say "        $Zip"
        return
    }
    Expand-Archive -Path $tmp -DestinationPath $dest -Force
    Remove-Item $tmp -ErrorAction SilentlyContinue
    Ok "      已解压到 video-studio\"
}

# ---------------------------------------------------------------- 打补丁
Say ""
Say "[3/5] 打上队列优化补丁 ..."

$target = Join-Path $app "core\api\agnes_video.py"
if (-not (Test-Path $target)) { Bad "      找不到 $target，安装包结构可能变了"; return }

$src = [IO.File]::ReadAllText($target, [Text.Encoding]::UTF8)

$initAnchor = "        queue_retries = 0"
$initAdd    = "        queue_retries = 0`r`n        # 本轮退避前已经换过几个 Key（每次 sleep 后归零）`r`n        queue_rotations = 0"

$delayAnchor = "                        delay = _QUEUE_RETRY_BASE_DELAY + random.uniform(0, _QUEUE_RETRY_JITTER)"
$rotateAdd = @"
                        # 队列满先把其余账号试一遍，再退避。
                        # 429 早就是这么做的，队列满却漏了：原来命中 503 直接
                        # sleep 30~60s，9 个账号轮完一圈要 4.5~9 分钟。若队列按
                        # 账户隔离，那几分钟里其余账号可能全是空的。
                        # 视频提交桶的 burst 本就是 1 x Key 数，连续换 Key 用的
                        # 正是它预留的配额。
                        if ring.has_multiple() and queue_rotations < len(ring) - 1:
                            queue_rotations += 1
                            ring.rotate()
                            logger.warning(
                                f"[KeyRotation] queue full ({code}), 换账号立即重试 "
                                f"({queue_rotations}/{len(ring) - 1})"
                            )
                            continue
                        queue_rotations = 0

$delayAnchor
"@

if ($src.Contains("queue_rotations")) {
    Ok "      补丁已经打过了，跳过"
} else {
    if (-not $src.Contains($initAnchor))  { Bad "      补丁锚点 1 对不上，上游代码可能改了。已跳过打补丁。"; }
    elseif (-not $src.Contains($delayAnchor)) { Bad "      补丁锚点 2 对不上，上游代码可能改了。已跳过打补丁。"; }
    else {
        $src = $src.Replace($initAnchor, $initAdd)
        $src = $src.Replace($delayAnchor, $rotateAdd.Replace("`r`n", "`n"))
        [IO.File]::WriteAllText($target, $src, (New-Object Text.UTF8Encoding $false))
        Ok "      已打上：队列满时先换账号，全被拒才退避"
    }
}

# ---------------------------------------------------------------- 写 Key
Say ""
Say "[4/5] 配置你的 Agnes 账号 ..."

$envFile = Join-Path $app ".env"
if (Test-Path $envFile) {
    Warn "      .env 已存在，不覆盖。要重填就先删掉它。"
} else {
    Say ""
    Say "      粘贴你的 Agnes API Key —— 一行一条，或一行里用逗号隔开。"
    Say "      粘完按两次回车。多几条就多几倍产能。"
    Say ""
    $raw = New-Object System.Collections.Generic.List[string]
    while ($true) {
        $l = Read-Host "      Key"
        if ([string]::IsNullOrWhiteSpace($l)) { break }
        $raw.Add($l)
    }
    $keys = @()
    foreach ($l in $raw) {
        foreach ($p in ($l -split '[,;\s]+')) { if ($p.Trim().Length -gt 10) { $keys += $p.Trim() } }
    }
    $keys = @($keys | Select-Object -Unique)

    if ($keys.Count -eq 0) {
        Warn "      一条都没收到。稍后可以自己编辑 $envFile"
    } else {
        $lines = @("# 由 AniFlow 安装器生成", "AGNES_API_KEY=$($keys[0])")
        for ($i = 1; $i -lt $keys.Count; $i++) { $lines += "AGNES_API_KEY_$($i + 1)=$($keys[$i])" }
        [IO.File]::WriteAllLines($envFile, $lines, (New-Object Text.UTF8Encoding $false))
        Ok "      已写入 $($keys.Count) 个账号（存在本机 .env，不会上传）"
    }
}

# ---------------------------------------------------------------- 启动
Say ""
Say "[5/5] 启动 ..."
Say ""
Warn "      第一次启动要装依赖，可能要几分钟，别关窗口。"
Warn "      启动完会自动打开浏览器；以后想再用，双击 video-studio 里的 start.bat 即可。"
Say ""

$start = Join-Path $app "start.bat"
if (Test-Path $start) {
    Push-Location $app
    & cmd /c "start.bat"
    Pop-Location
} else {
    Bad "      找不到 start.bat，请手动进 $app 运行"
}
