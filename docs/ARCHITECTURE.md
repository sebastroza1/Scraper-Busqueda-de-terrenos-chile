# Arquitectura objetivo

## MVP actual
Streamlit consulta directamente fuentes públicas y mantiene estado local.

## Arquitectura SaaS futura

```text
Frontend
  ↓
API FastAPI
  ↓
Application services
  ├── Analysis
  ├── Comparison
  ├── Alerts
  ├── Reports
  └── Workspaces
  ↓
Source adapters
  ↓
Cache / PostGIS
  ↓
Fuentes externas
```

## Estados de una fuente
- ACTIVE
- DEGRADED
- SOURCE_ERROR
- QUARANTINED
- AUTH_REQUIRED
- NOT_CONFIGURED

## Regla
Un error nunca debe traducirse como ausencia de riesgo o cumplimiento.
