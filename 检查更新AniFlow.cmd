@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AniFlow - Check and Install New Version
echo [AniFlow] Checking for the latest verified Windows version...
echo [AniFlow] New versions are installed into a separate folder.
echo [AniFlow] Your existing keys, history, and videos will not be deleted.
echo.
if not exist "scripts\check_aniflow_update_windows.ps1" goto :missing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\check_aniflow_update_windows.ps1" -Mode Install
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :failed
echo.
echo [AniFlow] Update workflow finished. Use the NEW folder to start the new version.
pause
exit /b 0
:missing
echo [AniFlow] Update helper is absent. Re-download the complete Windows package.
pause
exit /b 2
:failed
echo [AniFlow] Update did not complete. Existing installation remains unchanged.
pause
exit /b %RC%
