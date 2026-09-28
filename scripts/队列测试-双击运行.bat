@echo off
chcp 65001 >nul
title AniFlow Queue Test
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0QueueTest.ps1"
