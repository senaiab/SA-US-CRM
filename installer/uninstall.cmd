@echo off
setlocal
title SA-US ERP Uninstaller

cd /d "%TEMP%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" -InstallDir "%~dp0." %*
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
  echo SA-US ERP uninstall failed or was cancelled.
) else (
  echo SA-US ERP uninstall complete.
)
echo.
if not "%SAUS_NO_PAUSE%"=="1" pause
exit /b %EXITCODE%
