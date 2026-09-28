@echo off
chcp 65001 >nul
title AniFlow Video Studio Installer
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ScriptDir='%~dp0';$t=[IO.File]::ReadAllText('%~f0',[Text.Encoding]::UTF8);$m='#PSBEGIN'+'#';iex $t.Substring($t.LastIndexOf($m)+$m.Length)"
echo.
pause
exit /b
#PSBEGIN#
<#
  AniFlow - 视频工作台一键安装（v2）

  v1 的教训：
    - 没有日志，出错就什么都看不到
    - 在同一个窗口里调 start.bat，它一失败就退回来，
      而用户多按的那次回车会被结尾的 pause 吃掉，窗口瞬间关闭
    - 没告诉用户地址是 http://localhost:8765

  v2 全部修掉：全程写日志、start.bat 开在自己的窗口里（/k 不会消失）、
  装完主动探测端口并把地址打出来、结束前清空键盘缓冲。
#>

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { $OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Version = "v7.0.4"
$Zip     = "https://github.com/lcy362/agnes-video-generator/archive/refs/tags/$Version.zip"
$Url     = "http://localhost:8765"
$Line    = "=" * 62

$root = if ($ScriptDir) { $ScriptDir } elseif ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Log  = Join-Path $root "安装日志.txt"

function Say  ($t) { Write-Host $t;                        Add-Content -Path $Log -Value $t -Encoding UTF8 }
function Ok   ($t) { Write-Host $t -ForegroundColor Green; Add-Content -Path $Log -Value $t -Encoding UTF8 }
function Warn ($t) { Write-Host $t -ForegroundColor Yellow;Add-Content -Path $Log -Value $t -Encoding UTF8 }
function Bad  ($t) { Write-Host $t -ForegroundColor Red;   Add-Content -Path $Log -Value $t -Encoding UTF8 }

# 结束前清空键盘缓冲：否则用户多敲的回车会被外层 pause 吃掉，窗口秒关
function Finish {
    Say ""
    Say "（完整日志：$Log）"
    try { $Host.UI.RawUI.FlushInputBuffer() } catch {}
}

"" | Set-Content -Path $Log -Encoding UTF8
Say "AniFlow 视频工作台安装 —— $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

Write-Host ""
Write-Host $Line -ForegroundColor Cyan
Write-Host "  AniFlow 视频工作台 - 一键安装" -ForegroundColor Cyan
Write-Host $Line -ForegroundColor Cyan
Write-Host ""

try {

# ---------------------------------------------------------------- Python
Say "[1/5] 检查 Python ..."
$py = $null
foreach ($c in @("python", "py")) {
    try {
        $v = (& $c --version 2>&1 | Out-String).Trim()
        Add-Content -Path $Log -Value "      探测 $c -> $v" -Encoding UTF8
        if ($v -match "Python 3\.(\d+)") {
            if ([int]$Matches[1] -ge 10) { $py = $c; Ok "      $v"; break }
            else { Warn "      找到 $v，但需要 3.10 以上" }
        }
    } catch {
        Add-Content -Path $Log -Value "      探测 $c 失败: $($_.Exception.Message)" -Encoding UTF8
    }
}
if (-not $py) {
    Bad "      没找到 Python 3.10 以上。"
    Say ""
    Say "      请先装一次 Python：https://www.python.org/downloads/"
    Warn "      安装时务必勾选最下面的 'Add python.exe to PATH'，否则装完还是找不到。"
    Say "      装完重新双击本文件即可。"
    Finish; return
}

# ---------------------------------------------------------------- 下载
$dest = Join-Path $root "video-studio"
$app  = Join-Path $dest "agnes-video-generator-$($Version.TrimStart('v'))"

Say ""
Say "[2/5] 下载视频工作台 $Version ..."
if (Test-Path (Join-Path $app "start.bat")) {
    Ok "      已存在，跳过下载"
} else {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    $tmp = Join-Path $env:TEMP "avg-$Version.zip"
    Say "      从 GitHub 拉取（约 20 MB）..."
    try {
        Invoke-WebRequest -Uri $Zip -OutFile $tmp -UseBasicParsing -TimeoutSec 600
        Expand-Archive -Path $tmp -DestinationPath $dest -Force
        Remove-Item $tmp -ErrorAction SilentlyContinue
        Ok "      已解压"
    } catch {
        Bad "      下载失败：$($_.Exception.Message)"
        Say "      可手动下载后解压到 $dest，再重新双击本文件："
        Say "        $Zip"
        Finish; return
    }
}
if (-not (Test-Path (Join-Path $app "start.bat"))) {
    Bad "      解压后找不到 start.bat。实际解压出来的是："
    Get-ChildItem $dest -ErrorAction SilentlyContinue | ForEach-Object { Say "        $($_.Name)" }
    Finish; return
}

# ---------------------------------------------------------------- 打补丁
Say ""
Say "[3/5] 打上队列优化补丁 ..."
$target = Join-Path $app "core\api\agnes_video.py"
if (-not (Test-Path $target)) {
    Bad "      找不到 $target，上游结构可能变了。跳过补丁，不影响使用。"
} else {
    $src = [IO.File]::ReadAllText($target, [Text.Encoding]::UTF8)
    $initAnchor  = "        queue_retries = 0"
    $delayAnchor = "                        delay = _QUEUE_RETRY_BASE_DELAY + random.uniform(0, _QUEUE_RETRY_JITTER)"
    if ($src.Contains("queue_rotations")) {
        Ok "      已经打过，跳过"
    } elseif (-not $src.Contains($initAnchor) -or -not $src.Contains($delayAnchor)) {
        Bad "      补丁锚点对不上，上游代码已改。跳过补丁，不影响使用。"
    } else {
        $initAdd = "        queue_retries = 0`n        # 本轮退避前已换过几个 Key（每次 sleep 后归零）`n        queue_rotations = 0"
        $rotateAdd = @"
                        # 队列满先把其余账号试一遍，再退避。
                        # 429 早就是这么做的，队列满却漏了：原来命中 503 直接
                        # sleep 30~60s，9 个账号轮完一圈要 4.5~9 分钟。
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
        $src = $src.Replace($initAnchor, $initAdd).Replace($delayAnchor, $rotateAdd.Replace("`r`n", "`n"))
        [IO.File]::WriteAllText($target, $src, (New-Object Text.UTF8Encoding $false))
        Ok "      已打上：队列满时先换账号，全被拒才退避"
    }
}

# ---------------------------------------------------------------- 写 Key
Say ""
Say "[4/5] 配置 Agnes 账号 ..."
$envFile = Join-Path $app ".env"
if (Test-Path $envFile) {
    $n = (Select-String -Path $envFile -Pattern "^AGNES_API_KEY" -ErrorAction SilentlyContinue).Count
    Ok "      .env 已存在（$n 个账号），不覆盖。要重填就先删掉它。"
} else {
    Say ""
    Say "      粘贴 Agnes API Key —— 一行一条，或一行里用逗号隔开。"
    Say "      粘完按一次回车留空行结束。"
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
        Warn "      一条都没收到。可稍后手动编辑 $envFile"
    } else {
        $lines = @("# 由 AniFlow 安装器生成", "AGNES_API_KEY=$($keys[0])")
        for ($i = 1; $i -lt $keys.Count; $i++) { $lines += "AGNES_API_KEY_$($i + 1)=$($keys[$i])" }
        [IO.File]::WriteAllLines($envFile, $lines, (New-Object Text.UTF8Encoding $false))
        Ok "      已写入 $($keys.Count) 个账号（只存本机，不上传）"
    }
}

# ---------------------------------------------------------------- 启动
Say ""
Say "[5/5] 启动服务 ..."
Say ""
Warn "      会另外弹出一个黑窗口，那个才是服务本体。"
Warn "      第一次要装依赖，大概 3~10 分钟，中间看起来没反应是正常的。"
Warn "      那个窗口不要关，关了服务就停了。"
Say ""

# 关键：开在自己的窗口里，用 /k 让它失败也不会消失
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "start.bat" -WorkingDirectory $app | Out-Null
Ok "      已拉起服务窗口"

Say ""
Say "      正在等服务就绪（最多等 10 分钟）..."
$ready = $false
for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { $ready = $true; break }
    } catch {}
    if ($i % 12 -eq 11) { Say "      还在装依赖...（已等 $([int](($i+1)*5/60)) 分钟）" }
}

Say ""
Write-Host $Line -ForegroundColor Cyan
if ($ready) {
    Ok "  服务已就绪"
    Say ""
    Say "  在浏览器里打开： $Url"
    try { Start-Process $Url } catch {}
} else {
    Warn "  等了 10 分钟还没起来。"
    Say ""
    Say "  去看那个黑窗口里最后几行写了什么，截图发我。"
    Say "  也可以先自己试试打开： $Url"
}
Write-Host $Line -ForegroundColor Cyan

} catch {
    Bad ""
    Bad "出错了：$($_.Exception.Message)"
    Add-Content -Path $Log -Value ($_ | Out-String) -Encoding UTF8
    Say ""
    Say "把 安装日志.txt 发我就行。"
}

Finish
