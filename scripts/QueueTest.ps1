<#
  AniFlow 队列测试（独立版）

  这个文件不依赖项目、不依赖 Python、不依赖 .env。
  下载下来放桌面双击就能跑。

  它回答一个问题：
    Agnes 免费视频的排队，是【按账户】算，还是【全平台共用一个队】？

  按账户   -> 你的多个账号 = 成倍视频产能，多 Key 抽卡策略成立
  全平台共用 -> 多账号对视频无效，产能模型要重做
#>

param(
    [switch]$Watch,           # 持续挂机，直到测出结论
    [int]$Rounds   = 3,       # 发射轮数
    [int]$Interval = 20,      # 每轮间隔秒
    [int]$Seconds  = 8,       # 测试视频时长
    [string]$ApiBase = "https://apihub.agnes-ai.com/v1",   # 仅测试用
    [string]$ApiRoot = "https://apihub.agnes-ai.com"       # 仅测试用
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { $OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}

$Model     = "agnes-video-2.5-flash"
$Prompt    = "Stop-motion needle-felt animation test. A small felted cat figure on a kitchen counter blinks once and tilts its head. Slow camera push-in."
$Line      = "=" * 60

function Write-Head($t) { Write-Host $t -ForegroundColor Cyan }
function Write-Ok  ($t) { Write-Host $t -ForegroundColor Green }
function Write-Bad ($t) { Write-Host $t -ForegroundColor DarkGray }
function Write-Warn($t) { Write-Host $t -ForegroundColor Yellow }
function Wait-Key {
    # 非交互环境（比如被重定向）下不要崩
    try {
        Write-Host "按任意键关闭..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } catch { Start-Sleep -Seconds 1 }
}

Write-Host ""
Write-Head $Line
Write-Head "  AniFlow 视频队列测试"
Write-Head $Line
Write-Host ""

# ---------------------------------------------------------------- 收集 Key
Write-Host "请粘贴你的 Agnes API Key。" -ForegroundColor White
Write-Host "  - 一行一条，粘完按两次回车" -ForegroundColor DarkGray
Write-Host "  - 也可以一行里用逗号隔开，全部粘进来" -ForegroundColor DarkGray
Write-Host "  - 至少要 2 条才测得出结论，越多越准" -ForegroundColor DarkGray
Write-Host ""

$raw = New-Object System.Collections.Generic.List[string]
while ($true) {
    $l = Read-Host "Key"
    if ([string]::IsNullOrWhiteSpace($l)) { break }
    $raw.Add($l)
}

$keys = @()
foreach ($l in $raw) {
    foreach ($p in ($l -split '[,;\s]+')) {
        $p = $p.Trim()
        if ($p.Length -gt 10) { $keys += $p }
    }
}
$keys = @($keys | Select-Object -Unique)   # @() 必须加：单元素会被拆成字符串

if ($keys.Count -eq 0) {
    Write-Host ""
    Write-Warn "一条 Key 都没收到，没法测。"
    Wait-Key; exit 1
}

Write-Host ""
Write-Host "收到 $($keys.Count) 条 Key：" -ForegroundColor White
for ($i = 0; $i -lt $keys.Count; $i++) {
    $k = $keys[$i]
    Write-Host ("  账户 {0,-2}  ...{1}" -f ($i + 1), $k.Substring([Math]::Max(0, $k.Length - 6)))
}
if ($keys.Count -lt 2) {
    Write-Host ""
    Write-Warn "只有 1 条 Key。可以跑，但测不出结论 —— 单账户下"
    Write-Warn "「按账户限流」和「全平台共用」长得完全一样。"
}
Write-Host ""
Write-Host "模式：$(if($Watch){'持续挂机'}else{"$Rounds 轮"})   间隔 $Interval 秒   时长 $Seconds 秒"
Write-Head $Line

# ---------------------------------------------------------------- 并发发射
Add-Type -AssemblyName System.Net.Http | Out-Null
$http = New-Object System.Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromSeconds(120)

$body = @{
    model        = $Model
    prompt       = $Prompt
    seconds      = "$Seconds"
    mode         = "text"
    size         = "720P"
    aspect_ratio = "9:16"
    n            = 1
} | ConvertTo-Json -Compress

function Invoke-Round {
    param([string[]]$Keys, [int]$Index)

    $tasks = [System.Collections.ArrayList]@()
    foreach ($k in $Keys) {
        $req = New-Object System.Net.Http.HttpRequestMessage(
            [System.Net.Http.HttpMethod]::Post, "$ApiBase/videos")
        $req.Headers.Authorization =
            New-Object System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", $k)
        $req.Content = New-Object System.Net.Http.StringContent(
            $body, [Text.Encoding]::UTF8, "application/json")
        [void]$tasks.Add($http.SendAsync($req))   # 全部同一瞬间发出，这是关键
    }

    $out = [System.Collections.ArrayList]@()
    for ($i = 0; $i -lt $tasks.Count; $i++) {
        $label = "账户 " + ($i + 1)
        try {
            $resp   = $tasks[$i].GetAwaiter().GetResult()
            $status = [int]$resp.StatusCode
            $text   = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $json   = $null
            try { $json = $text | ConvertFrom-Json } catch {}

            $vid = $null
            if ($json) {
                if ($json.video_id)                 { $vid = $json.video_id }
                elseif ($json.data -and $json.data.video_id) { $vid = $json.data.video_id }
            }
            $code = if ($json -and $json.code) { "$($json.code)" } else { "" }

            if ($status -ge 200 -and $status -lt 300 -and $vid) {
                [void]$out.Add([pscustomobject]@{ Label=$label; Key=$Keys[$i]; Ok=$true;
                                           VideoId=$vid; Code=""; QueueFull=$false })
            } else {
                $qf = ($code -eq "video_queue_full") -or ($text -match "video_queue_full")
                $why = if ($code) { $code } else { "HTTP $status" }
                [void]$out.Add([pscustomobject]@{ Label=$label; Key=$Keys[$i]; Ok=$false;
                                           VideoId=$null; Code=$why; QueueFull=$qf })
            }
        } catch {
            [void]$out.Add([pscustomobject]@{ Label=$label; Key=$Keys[$i]; Ok=$false;
                                       VideoId=$null; Code="网络错误"; QueueFull=$false })
        }
    }
    return $out.ToArray()   # 配合调用端的 @()，单条和多条 Key 都能正确展开
}

# ---------------------------------------------------------------- 主循环
$verdict = "inconclusive"
$won     = $null
$idx     = 0

while ($true) {
    $idx++
    $r = @(Invoke-Round -Keys $keys -Index $idx)

    Write-Host ""
    Write-Host "第 $idx 轮   $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor White
    foreach ($a in $r) {
        if ($a.Ok) {
            Write-Ok  ("   {0,-8} 已入队   {1}" -f $a.Label, $a.VideoId)
            if (-not $won) { $won = $a }
        } else {
            Write-Bad ("   {0,-8} 被拒     {1}" -f $a.Label, $a.Code)
        }
    }

    $okN = @($r | Where-Object { $_.Ok -eq $true }).Count
    $qfN = @($r | Where-Object { $_.QueueFull -eq $true }).Count
    $mixed = ($okN -gt 0 -and $qfN -gt 0)

    if ($mixed) {
        Write-Host ("   小结: {0} 成功 / {1} 被拒" -f $okN, ($r.Count - $okN)) -NoNewline
        Write-Host "   <<< 混合结果，已可定论" -ForegroundColor Magenta
        $verdict = "per_account"
        break
    }
    Write-Host ("   小结: {0} 成功 / {1} 被拒" -f $okN, ($r.Count - $okN))

    if ($okN -eq $r.Count) { $verdict = "capacity" }

    if (-not $Watch -and $idx -ge $Rounds) { break }
    Start-Sleep -Seconds $Interval
}

# ---------------------------------------------------------------- 结论
Write-Host ""
Write-Head $Line
switch ($verdict) {
    "per_account" {
        Write-Ok "  结论：队列【按账户】隔离"
        Write-Host ""
        Write-Host "  同一瞬间，有的账户进得去、有的被拒 —— 只有按账户"
        Write-Host "  限流才可能这样。你的多个账号确实能成倍放大视频产能，"
        Write-Host "  多 Key 抽卡策略成立，生产方案不用改。"
    }
    "capacity" {
        Write-Ok "  结论：当前有空位（还不能定队列模型）"
        Write-Host ""
        Write-Host "  所有账户都进去了，说明此刻不拥挤。这不能证明是按账户"
        Write-Host "  隔离 —— 需要在拥挤时段再跑一次，看会不会出现混合结果。"
    }
    default {
        Write-Warn "  结论：全部被拒，无法区分"
        Write-Host ""
        Write-Host "  所有账户同时被拒。可能是全平台队列满了，也可能是每个"
        Write-Host "  账户各自都满了 —— 这两种情况此刻长得一模一样，"
        Write-Host "  硬下结论就是骗你。"
        Write-Host ""
        Write-Warn "  建议：重新双击运行，这次选挂机模式，它会一直蹲到出结论。"
    }
}
Write-Head $Line

# ---------------------------------------------------------------- 抢到就拿到底
if ($won) {
    Write-Host ""
    Write-Host "抢到队列位了，顺便回答第二个问题：视频自不自带声音。" -ForegroundColor White
    Write-Host "正在等出片（通常几分钟，别关窗口）..." -ForegroundColor DarkGray

    $url = $null
    $deadline = (Get-Date).AddMinutes(20)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 15
        try {
            $q = Invoke-RestMethod -Method Get `
                 -Uri "$ApiRoot/agnesapi?video_id=$($won.VideoId)&model_name=$Model" `
                 -Headers @{ Authorization = "Bearer $($won.Key)" } -TimeoutSec 60
            $st = "$($q.status)"
            Write-Host ("   {0}  状态: {1}" -f (Get-Date -Format 'HH:mm:ss'), $st) -ForegroundColor DarkGray
            if ($q.url)                        { $url = $q.url }
            elseif ($q.data -and $q.data.url)  { $url = $q.data.url }
            if ($url) { break }
            if ($st -match "fail|error") { break }
        } catch {
            Write-Host "   查询出错，继续等..." -ForegroundColor DarkGray
        }
    }

    if ($url) {
        $desk = [Environment]::GetFolderPath("Desktop")
        if ([string]::IsNullOrWhiteSpace($desk) -and $env:USERPROFILE) { $desk = Join-Path $env:USERPROFILE "Desktop" }
        if ([string]::IsNullOrWhiteSpace($desk) -or -not (Test-Path $desk)) {
            $desk = if ($ScriptDir) { $ScriptDir }
                    elseif ($PSScriptRoot) { $PSScriptRoot }
                    else { (Get-Location).Path }
        }
        $dir = Join-Path $desk "AniFlow测试视频"
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $file = Join-Path $dir ("test_{0}.mp4" -f (Get-Date -Format 'HHmmss'))
        Invoke-WebRequest -Uri $url -OutFile $file -TimeoutSec 300

        $bytes = [IO.File]::ReadAllBytes($file)
        $ascii = [Text.Encoding]::ASCII.GetString($bytes)
        $hasAudio = $ascii.Contains("soun")

        Write-Host ""
        Write-Ok "   视频已保存到桌面的「AniFlow测试视频」文件夹"
        Write-Host ("   文件大小 : {0:N0} KB" -f ($bytes.Length / 1KB))
        if ($hasAudio) { Write-Ok  "   自带音轨 : 是" }
        else           { Write-Warn "   自带音轨 : 否（配音要我们自己做）" }
        Write-Host ""
        Write-Host "   请打开看一遍，我需要知道毛毡风格动起来稳不稳。" -ForegroundColor White
    } else {
        Write-Warn "   等太久还没出片，先放着。视频 ID: $($won.VideoId)"
    }
}

Write-Host ""
Write-Host "把上面这些内容截图发我就行。" -ForegroundColor White
Wait-Key
