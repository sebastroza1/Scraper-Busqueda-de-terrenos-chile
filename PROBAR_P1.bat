@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python cli.py --priority P1 --json exports\ultima_prueba_P1.json
pause
