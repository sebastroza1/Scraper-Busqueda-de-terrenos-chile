# Reporte E2E MVP

Fecha local: 2026-08-30 America/Santiago

## Resultado

El MVP compila, levanta backend local, responde API, ejecuta jobs, persiste
estructura SQLite, genera Excel y compila la app Flutter Windows debug.

## Comandos Ejecutados

```powershell
cd python_engine
.\.venv\Scripts\python.exe -m pytest -q
```

Resultado: `27 passed, 2 warnings`.

```powershell
cd python_engine
.\.venv\Scripts\python.exe -m landfinder --port 8765 --data-dir ..\data
```

Resultado: backend local activo en `http://127.0.0.1:8765` con token efimero.

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8765/health
Invoke-RestMethod -Uri http://127.0.0.1:8765/session
Invoke-RestMethod -Uri http://127.0.0.1:8765/sources -Headers @{Authorization='Bearer <token>'}
Invoke-RestMethod -Uri http://127.0.0.1:8765/sources/health -Headers @{Authorization='Bearer <token>'}
```

Resultado:

- `/health`: `status=ok`.
- `/session`: token emitido.
- `/sources`: solo `mercado_publico` y `mercadolibre_real_estate`.
- `/sources/health`: ambos `DEGRADED` sin credenciales.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/searches ...
Invoke-RestMethod -Uri http://127.0.0.1:8765/searches/<id> ...
```

Resultado sin credenciales:

- Mercado Publico: warning por `MERCADO_PUBLICO_TICKET` faltante.
- MercadoLibre: warning por `MERCADOLIBRE_ACCESS_TOKEN` faltante.
- Job completa como `COMPLETED_WITH_ERRORS`.
- Corrida combinada final: `found_count=0`, `processed_count=0`,
  `error_count=0`, `warning_count=2`.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/exports/excel ...
```

Resultado: creado `data\exports\landfinder_export.xlsx`.

```powershell
cd desktop_app
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics analyze
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics test
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics build windows --debug
```

Resultado:

- `flutter analyze`: no issues.
- `flutter test`: all tests passed.
- Windows debug build: `build\windows\x64\runner\Debug\landfinder_desktop.exe`.

## Warnings

- `fastapi.testclient` emite `StarletteDeprecationWarning` por transicion de
  `httpx`; no bloquea el MVP.
- Pillow avisa de futura deprecacion de `Image.getdata`; planificar cambio a
  `get_flattened_data` cuando el minimo de Pillow lo permita.

## No Probado

No se probo adquisicion real de terrenos desde Mercado Publico ni MercadoLibre
porque no habia `MERCADO_PUBLICO_TICKET`, `MERCADOLIBRE_ACCESS_TOKEN` ni
`CMF_API_KEY` cargados en el entorno durante la validacion.

## Criterio De Aceptacion Actual

- El sistema no agrega fuentes masivas nuevas.
- Las reglas DS49/DS19 no verificadas quedan en revision manual.
- La app no afirma compatibilidad legal ni urbanistica.
- Los conectores oficiales fallan de forma explicita si faltan credenciales.
- La persistencia, deduplicacion, exportacion y UI estan conectadas al contrato
  real del backend.
