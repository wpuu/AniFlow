# AniFlow - Agnes 视频队列探测（Windows 一键运行）
#
# 回答一个决定产能模型的问题：
#   免费视频队列是【按账户】隔离，还是【全平台共享】？
#
# 按账户  -> 你的 9 个账户让视频产能 x9，多 Key 抽卡策略成立
# 共享    -> 多账户对视频无效（对文本/图片仍有效），产能模型要重做
#
# 用法：右键「使用 PowerShell 运行」，或：
#   powershell -ExecutionPolicy Bypass -File scripts\probe_queue_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\probe_queue_windows.ps1 -Watch

param(
    [switch]$Watch,          # 持续挂机直到测出结论
    [int]$Rounds = 3,        # 发射轮数
    [double]$Interval = 20,  # 每轮间隔秒
    [int]$Seconds = 8        # 测试视频时长
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host ""
Write-Host "AniFlow 视频队列探测" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan

# --- 环境检查 ---
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "未找到虚拟环境，先跑一次安装：" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\setup_aniflow_windows.ps1"
    exit 1
}

if (-not (Test-Path (Join-Path $repo ".env"))) {
    Write-Host ".env 不存在。请先复制 .env.example 为 .env" -ForegroundColor Red
    Write-Host "并填入 AGNES_API_KEYS（你的多条 Key，用英文逗号分隔，不要有空格）" -ForegroundColor Red
    Write-Host ""
    Write-Host "例如：" -ForegroundColor DarkGray
    Write-Host "  AGNES_API_KEYS=sk-aaa,sk-bbb,sk-ccc" -ForegroundColor DarkGray
    exit 1
}

# 只检查是否配置了 Key，绝不打印 Key 本身
$envText = Get-Content (Join-Path $repo ".env") -Raw
if ($envText -notmatch "(?m)^\s*AGNES_API_KEYS\s*=\s*\S") {
    Write-Host ".env 里没有配置 AGNES_API_KEYS" -ForegroundColor Red
    Write-Host "把你的 9 条 Key 用英文逗号连起来写进去，例如：" -ForegroundColor Yellow
    Write-Host "  AGNES_API_KEYS=sk-第1条,sk-第2条,sk-第3条,..." -ForegroundColor DarkGray
    exit 1
}

# --- 运行 ---
$probeArgs = @("-m", "aniflow.cli", "queue-probe",
               "--rounds", $Rounds, "--interval", $Interval, "--seconds", $Seconds)
if ($Watch) { $probeArgs += "--watch" }

& $venvPython @probeArgs
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
    Write-Host "探测完成。" -ForegroundColor Green
} else {
    Write-Host "探测结束：队列当前拥挤，未能定论。" -ForegroundColor Yellow
    Write-Host "建议加 -Watch 持续挂机，抢到空位就会自动出结论：" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\probe_queue_windows.ps1 -Watch" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "按任意键关闭..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
