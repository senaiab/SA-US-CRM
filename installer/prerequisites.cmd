@echo off
setlocal
title SA-US ERP Database Prerequisite

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prerequisites.ps1"
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo Database prerequisite setup did not complete.
) else (
  echo Database prerequisite setup complete.
)
echo.
pause
exit /b %EXITCODE%
