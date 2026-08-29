@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AniFlow] 首次安装/更新本机运行环境...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup_aniflow_windows.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo [AniFlow] 安装失败，错误码 %EXITCODE%。
) else (
  echo [AniFlow] 安装完成。以后双击“启动AniFlow.cmd”即可。
)
echo.
pause
exit /b %EXITCODE%
