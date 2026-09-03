# Arquitectura Definitiva

## Vision

La aplicacion sera una plataforma local de prefactibilidad territorial. Flutter
Desktop sera la interfaz. Python correra como proceso local administrado por
Flutter y expondra una API FastAPI solo en `127.0.0.1` con token efimero por
sesion.

El sistema no aprueba terrenos. Clasifica evidencia preliminar en:

- `COMPATIBLE_PRELIMINARMENTE`
- `COMPATIBLE_CON_OBSERVACIONES`
- `INFORMACION_INSUFICIENTE`
- `INCOMPATIBLE_POR_REGLA_VERIFICABLE`

## Componentes

1. `desktop_app`
   Interfaz Flutter Desktop. Inicia el backend, guarda el token local, consume
   REST y escucha progreso por SSE o WebSocket.

2. `python_engine`
   Backend local Python. Contiene API, modelos, conectores, normalizacion,
   almacenamiento, pipeline, reglas, scoring y exportadores.

3. `data`
   Directorio local de trabajo no versionado. Guarda SQLite, cache HTTP,
   imagenes originales/previews, documentos cargados, snapshots y exportes.

4. `rules`
   Reglas versionadas por programa, anio, llamado, region y comuna. Los valores
   no confirmados quedan como `UNKNOWN`.

5. `docs`
   Decision record vivo: auditoria de fuentes, API, riesgos, mockups y plan de
   implementacion.

## Arbol objetivo

```text
.
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API_CONTRACT.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── REPOSITORY_INSPECTION.md
│   ├── RISKS.md
│   ├── SOURCE_AUDIT.md
│   └── UI_MOCKUPS.md
├── desktop_app/
│   ├── pubspec.yaml
│   └── lib/
│       ├── app.dart
│       ├── features/
│       │   ├── dashboard/
│       │   ├── search/
│       │   ├── results/
│       │   ├── map/
│       │   ├── property_detail/
│       │   └── comparison/
│       └── services/
│           └── landfinder_api_client.dart
├── python_engine/
│   ├── pyproject.toml
│   ├── rules/
│   │   ├── ds49/
│   │   │   └── 2026/
│   │   └── ds19/
│   │       └── 2026/
│   ├── src/
│   │   └── landfinder/
│   │       ├── api/
│   │       ├── core/
│   │       ├── models/
│   │       ├── storage/
│   │       ├── connectors/
│   │       │   ├── marketplaces/
│   │       │   ├── brokers/
│   │       │   ├── public_procurement/
│   │       │   ├── auctions/
│   │       │   └── geo/
│   │       ├── normalization/
│   │       ├── geocoding/
│   │       ├── deduplication/
│   │       ├── images/
│   │       ├── geospatial/
│   │       ├── urbanism/
│   │       ├── risks/
│   │       ├── accessibility/
│   │       ├── rules/
│   │       ├── scoring/
│   │       └── reports/
│   └── tests/
│       └── fixtures/
└── data/
    ├── cache/
    ├── documents/
    ├── exports/
    ├── images/
    └── snapshots/
```

## Flujo

Flujo MVP implementado:

```text
DISCOVERY
↓
DETAIL_EXTRACTION
↓
NORMALIZATION
↓
UF_ENRICHMENT
↓
IMAGE_PROCESSING
↓
DEDUPLICATION
↓
PERSISTENCE
↓
EXPORT_READY
```

Flujo objetivo futuro:

```text
DISCOVERY
↓
DETAIL_EXTRACTION
↓
NORMALIZATION
↓
GEOCODING
↓
DEDUPLICATION
↓
IMAGE_PROCESSING
↓
CADASTRAL_ENRICHMENT
↓
GIS_ENRICHMENT
↓
URBAN_ANALYSIS
↓
RISK_ANALYSIS
↓
ACCESSIBILITY_ANALYSIS
↓
PROGRAM_RULE_ENGINE
↓
SCORING
↓
USER_REVIEW
↓
EXPORT
```

Cada etapa debe reportar progreso, tolerar fallos por registro, registrar
evidencia y permitir reintento. Un fallo de conector no detiene toda la busqueda.

## Reglas

Las reglas DS49 y DS19 no viven hardcodeadas en Python. El motor carga YAML y
registra:

- version;
- fuente legal;
- fecha efectiva;
- aplicabilidad territorial;
- severidad;
- automatico/manual;
- resultado;
- evidencia usada.

Si una regla depende de llamado vigente, CIP, DOM, tasacion, promesa,
factibilidad o interpretacion profesional, el resultado sera
`MANUAL_REVIEW_REQUIRED` o `UNKNOWN`.

## Persistencia

SQLite es suficiente para el MVP. Las geometrias se guardan como GeoJSON/WKB y
los valores derivados mantienen evidencia por campo. Para analisis masivo se
puede agregar DuckDB + GeoParquet sin cambiar el contrato principal.
