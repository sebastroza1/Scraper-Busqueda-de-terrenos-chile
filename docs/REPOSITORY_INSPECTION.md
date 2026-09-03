# Inspeccion Del Repositorio

Fecha de inspeccion: 2026-08-30

## Que existe

El repositorio contenia solamente:

```text
README.md
```

El archivo tenia un titulo y no habia codigo, dependencias, tests, estructura
Flutter, motor Python, conectores, modelos, base de datos, reglas ni
documentacion tecnica.

`git status --short` no reportaba cambios antes de comenzar esta entrega.

## Que falta

Faltaba todo el producto:

- arquitectura de escritorio Flutter + backend local Python;
- modelo canonico `PropertyCandidate`;
- abstraccion `SourceConnector`;
- auditoria de fuentes;
- motor de reglas versionado DS49 / DS19;
- pipeline de descubrimiento, normalizacion, enriquecimiento y scoring;
- esquema persistente local;
- API localhost para Flutter;
- estrategia de imagenes, documentos, historico y trazabilidad;
- tests de integridad y fixtures;
- politica explicita para no inventar scrapers, endpoints, selectores ni reglas.

## Decision inicial

Como el repositorio estaba vacio, la primera implementacion crea una base
conservadora:

- documentacion revisable antes de codigo ejecutable complejo;
- modelos ricos pero sin suponer campos normativos desconocidos;
- conectores base y conectores iniciales solo para fuentes con API oficial
  documentada;
- reglas YAML con valores `UNKNOWN` o `MANUAL_REVIEW_REQUIRED` cuando no hay
  fuente normativa confirmada;
- esquema SQLite auditable, preparado para evolucionar a GeoPackage,
  GeoParquet o DuckDB sin bloquear el MVP.

## Revision 2026-08-31

Estado actual auditado antes de continuar:

- Backend canonico: `python_engine/src/landfinder`.
- Paquete Python unico: `python_engine/pyproject.toml`.
- Esquema SQLite canonico: `python_engine/src/landfinder/storage/schema.sql`.
- No existe un segundo `src/landfinder` en la raiz del repositorio.
- Flutter canonico: `desktop_app/lib`.
- Compatibilidad Flutter historica: `desktop_app/lib/src/api.dart` y
  `desktop_app/lib/src/secret_store.dart` solo reexportan las rutas nuevas.

Refactor Flutter actual:

- `desktop_app/lib/main.dart` queda como entrypoint minimo.
- `desktop_app/lib/app` contiene app, router y tema.
- `desktop_app/lib/core/api` contiene el cliente local.
- `desktop_app/lib/core/security` contiene SecretStore y OAuth MercadoLibre.
- `desktop_app/lib/core/widgets` contiene widgets compartidos.
- `desktop_app/lib/features/shell` contiene la pantalla principal.
- `desktop_app/lib/features/map` contiene el mapa real con `flutter_map`.

Validacion estructural:

- Imports Python resuelven desde `python_engine/src/landfinder`.
- No se agregaron fuentes masivas nuevas.
- Mercado Publico, MercadoLibre, CMF, MINVU, repositorios, jobs, Excel y UI se
  mantienen sobre el MVP existente.
