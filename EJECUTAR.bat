@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo Ejecuta primero INSTALAR_Y_EJECUTAR.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m streamlit run app.py
