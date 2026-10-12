@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AniFlow - Start or Restart Current Build
echo [AniFlow] Starting the current verified build...
echo [AniFlow] This will stop only a verified old AniFlow service on port 8765.
echo [AniFlow] Browser keys, history, and files will be preserved.
echo.
if not exist "scripts\restart_aniflow_windows.ps1" goto :old_package
if not exist "prebuilt_frontend.json" goto :old_package
if /I "%ANIFLOW_NO_BROWSER%"=="1" goto :no_browser
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\restart_aniflow_windows.ps1"
goto :result
:no_browser
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\restart_aniflow_windows.ps1" -NoBrowser
:result
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :failed
echo [AniFlow] Started. Check the ACTIVE build SHA above.
exit /b 0
:old_package
echo [AniFlow] This folder contains an older or incomplete build.
echo [AniFlow] Download AniFlow-9Key-Windows from the latest successful PR 2 CI.
echo https://github.com/wpuu/AniFlow/pull/2
pause
exit /b 2
:failed
echo [AniFlow] Safe startup failed; code %RC%.
echo [AniFlow] An unknown process on port 8765 will not be killed.
pause
exit /b %RC%
