@echo off
chcp 65001 >nul
title AniFlow Queue Test - Watch Mode
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0QueueTest.ps1" -Watch
