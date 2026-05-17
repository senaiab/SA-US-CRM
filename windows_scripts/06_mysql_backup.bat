@echo off
setlocal enabledelayedexpansion
title SA-US ERP Database Backup

set BACKUP_DIR=C:\SA_US_ERP\Backups
set DB_NAME=sa_us_erp
set DB_USER=sa_us_user
set DB_PASS=SAUSERP2026!

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

:: Build a clean timestamp: YYYYMMDD_HHMM
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
set DATESTAMP=%dt:~0,8%_%dt:~8,4%

set OUTFILE=%BACKUP_DIR%\%DB_NAME%_%DATESTAMP%.sql

echo ========================================
echo SA-US ERP Database Backup
echo ========================================
echo Database : %DB_NAME%
echo Output   : %OUTFILE%
echo.

where mysqldump >nul 2>&1
if errorlevel 1 (
  echo ERROR: mysqldump not found in PATH.
  echo Make sure MariaDB/MySQL bin folder is in your system PATH.
  echo Default path: C:\Program Files\MariaDB xx.x\bin
  pause
  exit /b 1
)

mysqldump -u %DB_USER% -p%DB_PASS% %DB_NAME% > "%OUTFILE%"
if errorlevel 1 (
  echo.
  echo Backup FAILED. Check credentials in this script and ensure MariaDB is running.
  pause
  exit /b 1
)

echo.
echo Backup complete: %OUTFILE%
echo.

:: Keep only last 30 backups to avoid filling the disk
set COUNT=0
for /f "delims=" %%F in ('dir /b /o-d "%BACKUP_DIR%\%DB_NAME%_*.sql" 2^>nul') do (
  set /a COUNT+=1
  if !COUNT! GTR 30 del "%BACKUP_DIR%\%%F"
)

echo Old backups beyond 30 cleaned up.
pause
exit /b 0
