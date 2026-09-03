# Scraper-Busqueda-de-terrenos-chile

Sistema local de inteligencia territorial para buscar, consolidar, auditar y
preevaluar terrenos potencialmente utiles para proyectos habitacionales en
Chile.

El principio del proyecto es calidad de informacion antes que volumen. La
aplicacion no aprueba terrenos ni reemplaza revision legal, SERVIU, DOM,
ambiental, urbanistica ni profesional. Todo resultado es preliminar y debe
mantener evidencia, fecha, fuente y confianza.

## Estado MVP

Implementado:

- backend local FastAPI en `python_engine`;
- token efimero por sesion y escucha restringida a `127.0.0.1`;
- SQLite con migraciones, repositorios y tablas de candidatos, fuentes,
  imagenes, historial de precios, UF, jobs, errores y canonicos;
- normalizacion de texto, precio, superficie y ubicacion MVP;
- servicio UF CMF con cache;
- conectores oficiales para `mercado_publico` y `mercadolibre_real_estate`;
- procesamiento de imagenes con preview, SHA-256 y hash perceptual;
- deduplicacion inicial por id, URL, ubicacion, area, precio, titulo e imagen;
- pipeline con eventos, tolerancia a fallos por fuente/registro y filtros
  locales post-normalizacion;
- export Excel multipestana;
- app Flutter Windows con dashboard, busqueda, resultados, mapa local de puntos,
  fuentes, exportacion y configuracion;
- auditoria de reglas DS49/DS19 como `TO_VERIFY`, sin descarte automatico.

No implementado en este MVP:

- nuevas fuentes masivas;
- scraping HTML de portales no auditados;
- reglas automaticas DS49/DS19 con valores normativos;
- GIS/DS49/DS19 avanzado, CIP, cabida, zonificacion o riesgos oficiales;
- mapa con proveedor externo de tiles.

## Fuentes Del MVP

- Mercado Publico / ChileCompra API: requiere `MERCADO_PUBLICO_TICKET`.
- MercadoLibre / PortalInmobiliario Real Estate API: requiere
  `MERCADOLIBRE_ACCESS_TOKEN`.
- CMF UF: requiere `CMF_API_KEY` o `UF_CMF_API_KEY`.

Sin esas credenciales, los conectores quedan `DEGRADED` y las busquedas
terminan con warnings trazables, no con datos simulados.

## Preparar Y Probar

```powershell
cd python_engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m landfinder --port 8765 --data-dir ..\data
```

```powershell
cd desktop_app
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics pub get
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics analyze
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics test
C:\flutter\bin\flutter.bat --no-version-check --suppress-analytics build windows --debug
```

## Documentacion

- `docs/RUNBOOK.md`: comandos operativos.
- `docs/E2E_REPORT.md`: validacion ejecutada.
- `docs/API_CONTRACT.md`: contrato real Flutter/Python.
- `docs/SOURCE_AUDIT.md`: auditoria de fuentes.
- `docs/RULE_AUDIT.md`: auditoria de reglas DS49/DS19.
- `docs/ADR_MAP_PROVIDER.md`: decision pendiente de mapa.
