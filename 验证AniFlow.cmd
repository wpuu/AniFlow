@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AniFlow] 正在执行本机测试与前端构建验证...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\verify_aniflow_windows.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo [AniFlow] 验证失败，错误码 %EXITCODE%。
) else (
  echo [AniFlow] 验证通过。
)
echo.
pause
exit /b %EXITCODE%
