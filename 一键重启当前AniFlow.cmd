@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title AniFlow - Restart verified current build
echo [AniFlow] 正在核实当前文件夹并切换至此版本...
echo [AniFlow] 本操作只关闭旧 AniFlow 本机服务，不删除浏览器 Key 或历史。
echo.
if not exist "scripts\restart_aniflow_windows.ps1" (
  echo [AniFlow] 此文件夹属于旧测试包：缺少新版安全重启组件。
  echo 请从 AniFlow PR #2 最新成功 CI 的 Artifacts 下载完整 Windows 测试包。
  echo 不要从 main 页面直接 Download ZIP，那个仍是旧代码。
  echo.
  pause
  exit /b 2
)
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\restart_aniflow_windows.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" (
  echo [AniFlow] 未启动新版，避免误打开旧版本。错误码 %EXITCODE%。
  echo 请查看以上错误信息；不要删除 localStorage 或强制结束未知端口程序。
  pause
  exit /b %EXITCODE%
)
echo [AniFlow] 已打开浏览器。如果页面没变，请确认网页底部的“正在运行版本”。
timeout /t 5 /nobreak >nul
exit /b 0
