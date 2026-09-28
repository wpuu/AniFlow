@echo off
chcp 65001 >nul
title AniFlow Queue Test
cd /d "%~dp0"
if not exist "%~dp0QueueTest.ps1" (
  echo.
  echo [!] QueueTest.ps1 not found in this folder.
  echo     Put BOTH files in the SAME folder, then run again.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0QueueTest.ps1"
