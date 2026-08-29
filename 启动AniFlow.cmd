@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AniFlow] 正在启动...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start_aniflow_windows.ps1"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo [AniFlow] 启动失败，错误码 %EXITCODE%。
  echo 如果是第一次使用，请先双击“首次安装AniFlow.cmd”。
  echo.
  pause
)
exit /b %EXITCODE%
