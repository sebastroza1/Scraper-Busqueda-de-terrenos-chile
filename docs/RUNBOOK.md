# Runbook MVP

Fecha: 2026-08-30

## Preparar Python

```powershell
cd python_engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Ejecutar Backend

```powershell
cd python_engine
.\.venv\Scripts\python.exe -m landfinder --port 8765 --data-dir ..\data
```

El proceso imprime:

```text
LANDFINDER_SESSION_TOKEN=<token>
```

Usar ese valor como:

```text
Authorization: Bearer <token>
```

## Credenciales

El MVP usa solo estas fuentes operativas:

- `mercado_publico`: requiere `MERCADO_PUBLICO_TICKET`.
- `mercadolibre_real_estate`: requiere `MERCADOLIBRE_ACCESS_TOKEN`.
- UF CMF: requiere `CMF_API_KEY` o `UF_CMF_API_KEY`.

Tambien se pueden cargar en runtime con `PUT /settings` desde Flutter.

## Smoke Test API

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8765/health
Invoke-RestMethod -Uri http://127.0.0.1:8765/session
Invoke-RestMethod -Uri http://127.0.0.1:8765/sources -Headers @{Authorization='Bearer <token>'}
Invoke-RestMethod -Uri http://127.0.0.1:8765/sources/health -Headers @{Authorization='Bearer <token>'}
```

Crear una busqueda:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/searches `
  -Headers @{Authorization='Bearer <token>'} `
  -ContentType 'application/json' `
  -Body '{"regions":["Metropolitana de Santiago"],"communes":["Maipu"],"keywords":["terreno"],"sources":["mercado_publico","mercadolibre_real_estate"],"gross_area_min_m2":1000}'
```

## Tests Python

```powershell
cd python_engine
.\.venv\Scripts\python.exe -m pytest -q
```

## Flutter Desktop

```powershell
cd desktop_app
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics pub get
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics analyze
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics test
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics build windows --debug
```

Ejecutable debug:

```text
desktop_app\build\windows\x64\runner\Debug\landfinder_desktop.exe
```

La app intenta usar el backend si ya esta activo en `127.0.0.1:8765`. Si no lo
esta, inicia `python_engine\.venv\Scripts\python.exe -m landfinder`.
