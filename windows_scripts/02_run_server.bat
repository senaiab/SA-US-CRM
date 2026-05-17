@echo off
cd /d "%~dp0\..\server"
call .venv\Scripts\activate
python app.py
pause
