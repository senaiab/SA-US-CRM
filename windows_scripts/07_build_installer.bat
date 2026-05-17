@echo off
setlocal enabledelayedexpansion
title SA-US ERP Installer Builder

set ROOT=%~dp0\..
set RELEASE_DIR=%ROOT%\release
set OUTPUT_EXE=%RELEASE_DIR%\SA-US-ERP-Setup.exe
set INSTALLER_DIR=%ROOT%\installer

echo ========================================
echo  SA-US ERP Installer Builder
echo ========================================
echo.
echo This script:
echo   1. Assembles the payload (server EXE, client EXE, configs, SQL)
echo   2. Creates payload.zip
echo   3. Compiles SA-US-ERP-Setup.exe (single self-contained installer)
echo.
echo IMPORTANT: Run windows_scripts\05_build_exe_files.bat first
echo if you have not already built the server and client EXEs.
echo.

:: Verify the EXEs exist before proceeding
if not exist "%ROOT%\server\dist\SA_US_ERP_Server.exe" (
  echo ERROR: Server EXE not found at server\dist\SA_US_ERP_Server.exe
  echo Run windows_scripts\05_build_exe_files.bat first, then re-run this script.
  echo.
  pause
  exit /b 1
)
if not exist "%ROOT%\client\dist\SA_US_ERP_Client.exe" (
  echo ERROR: Client EXE not found at client\dist\SA_US_ERP_Client.exe
  echo Run windows_scripts\05_build_exe_files.bat first, then re-run this script.
  echo.
  pause
  exit /b 1
)

echo Building installer...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER_DIR%\build_payload.ps1" ^
  -RootDir "%ROOT%" ^
  -ReleaseDir "%RELEASE_DIR%" ^
  -OutputExe "%OUTPUT_EXE%"

if errorlevel 1 (
  echo.
  echo Installer build FAILED. See error output above.
  echo.
  pause
  exit /b 1
)

echo.
echo Output: %OUTPUT_EXE%
echo.
pause
exit /b 0
