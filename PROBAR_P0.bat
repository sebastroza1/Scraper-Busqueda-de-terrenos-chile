@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python cli.py --priority P0 --json exports\ultima_prueba_P0.json
pause
