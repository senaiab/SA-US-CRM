@echo off
setlocal enabledelayedexpansion
title SA-US ERP EXE Builder

set ROOT=%~dp0\..
set SERVER_DIR=%ROOT%\server
set CLIENT_DIR=%ROOT%\client

echo ========================================
echo SA-US ERP Windows EXE Builder
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python was not found in PATH.
  echo Install Python 3.11+ and enable "Add Python to PATH".
  pause
  exit /b 1
)

echo [1/6] Preparing server virtual environment...
cd /d "%SERVER_DIR%"
if not exist .venv (
  python -m venv .venv
  if errorlevel 1 goto :fail
)
call .venv\Scripts\activate
if errorlevel 1 goto :fail
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo [2/6] Building server EXE...
pyinstaller --clean --noconfirm --onefile --name SA_US_ERP_Server --hidden-import passlib.handlers.bcrypt app.py
if errorlevel 1 goto :fail
copy /Y server_config.ini dist\server_config.ini >nul

echo [3/6] Preparing client virtual environment...
cd /d "%CLIENT_DIR%"
if not exist .venv (
  python -m venv .venv
  if errorlevel 1 goto :fail
)
call .venv\Scripts\activate
if errorlevel 1 goto :fail
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

echo [4/6] Building client EXE...
pyinstaller --clean --noconfirm --onefile --windowed --name SA_US_ERP_Client --icon branding\app_icon.ico client_app.py
if errorlevel 1 goto :fail

echo [5/6] Copying client runtime files...
copy /Y client_config.ini dist\client_config.ini >nul
copy /Y tenant_branding.json dist\tenant_branding.json >nul
if exist company_logo.png copy /Y company_logo.png dist\company_logo.png >nul
xcopy /E /I /Y branding dist\branding >nul

echo [6/6] Build complete.
echo.
echo Server output:
echo   %SERVER_DIR%\dist\SA_US_ERP_Server.exe
echo   %SERVER_DIR%\dist\server_config.ini
echo.
echo Client output:
echo   %CLIENT_DIR%\dist\SA_US_ERP_Client.exe
echo   %CLIENT_DIR%\dist\client_config.ini
echo   %CLIENT_DIR%\dist\tenant_branding.json
echo   %CLIENT_DIR%\dist\branding\
echo.
pause
exit /b 0

:fail
echo.
echo Build failed. See error output above.
pause
exit /b 1
