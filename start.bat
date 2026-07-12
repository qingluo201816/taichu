@echo off
setlocal EnableExtensions
chcp 65001 >nul

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
set "TAICHU_START_EXIT=%ERRORLEVEL%"

if not "%TAICHU_START_EXIT%"=="0" (
    if not defined TAICHU_NON_INTERACTIVE pause
    exit /b %TAICHU_START_EXIT%
)

if not defined TAICHU_NON_INTERACTIVE pause
exit /b 0
