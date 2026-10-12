@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title AniFlow - Install Local Runtime
echo [AniFlow] Installing or updating the local Python runtime...
echo [AniFlow] No browser keys or video history will be deleted.
echo.
if not exist "scripts\setup_aniflow_windows.ps1" goto :missing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup_aniflow_windows.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :failed
echo [AniFlow] Install complete.
echo [AniFlow] Next, double click the AniFlow start/restart CMD.
pause
exit /b 0
:missing
echo [AniFlow] Missing runtime setup script. Re-extract a full Windows ZIP.
pause
exit /b 2
:failed
echo [AniFlow] Installation failed with exit code %RC%.
pause
exit /b %RC%
