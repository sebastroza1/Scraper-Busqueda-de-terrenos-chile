@echo off
title Landfinder Source Lab v0.3
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  set PY=py
) else (
  set PY=python
)

echo [1/4] Creando entorno virtual...
%PY% -m venv .venv
if errorlevel 1 goto error

echo [2/4] Activando entorno...
call .venv\Scripts\activate.bat
if errorlevel 1 goto error

echo [3/4] Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto error

echo [4/4] Abriendo Source Lab...
echo Si el navegador no abre automaticamente:
echo http://localhost:8501
python -m streamlit run app.py
goto end

:error
echo.
echo ERROR. Verifica Python 3.10+ y conexion a Internet.
pause

:end
