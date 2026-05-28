@echo off
setlocal

REM Official SA-US ERP Windows build entry point.
REM This wrapper keeps the release command stable even if internal scripts move later.

cd /d "%~dp0"
call windows_scripts\05_build_exe_files.bat
exit /b %ERRORLEVEL%
