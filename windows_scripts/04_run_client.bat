@echo off
cd /d "%~dp0\..\client"
call .venv\Scripts\activate
python client_app.py
pause
