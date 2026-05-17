@echo off
setlocal
title SA-US ERP Installer

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo SA-US ERP installation failed.
) else (
  echo SA-US ERP installation complete.
)
echo.
if not "%SAUS_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%
