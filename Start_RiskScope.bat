@echo off
REM RiskScope one-click launcher for Windows (double-click this file)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\start_riskscope_windows.ps1"
