# API Flutter Python

Estado: MVP implementado.

## Transporte

- Host: `127.0.0.1`
- Puerto por defecto: `8765`
- Autenticacion: `Authorization: Bearer <token>`
- Token: efimero por sesion, obtenido en `GET /session`
- Progreso: eventos guardados en `GET /searches/{search_id}` y stream SSE en
  `GET /searches/{search_id}/events`

El backend no debe escuchar en interfaces externas.

## Endpoints implementados

```text
GET  /health
GET  /session
GET  /sources
GET  /sources/health
GET  /sources/{source_id}/audit
POST /searches
GET  /searches/{search_id}
GET  /searches/{search_id}/events
POST /searches/{search_id}/cancel
GET  /properties
GET  /properties/{property_id}
POST /exports/excel
GET  /settings
PUT  /settings
GET  /errors
```

## `POST /searches`

Request:

```json
{
  "regions": ["Metropolitana de Santiago"],
  "communes": ["Maipu"],
  "keywords": ["terreno"],
  "price_min_clp": null,
  "price_max_clp": null,
  "gross_area_min_m2": 1000,
  "gross_area_max_m2": null,
  "sources": ["mercado_publico", "mercadolibre_real_estate"],
  "include_auctions": true
}
```

Response:

```json
{
  "search_id": "uuid",
  "status": "QUEUED",
  "created_at": "2026-08-30T20:22:03-04:00"
}
```

## Job

`GET /searches/{search_id}` devuelve:

```json
{
  "id": "uuid",
  "status": "COMPLETED_WITH_ERRORS",
  "found_count": 0,
  "processed_count": 0,
  "discarded_count": 0,
  "warning_count": 1,
  "error_count": 0,
  "events": [
    {
      "type": "warning",
      "stage": "DISCOVERY",
      "message": "MERCADOLIBRE_ACCESS_TOKEN is required for MercadoLibre official API searches",
      "source": "mercadolibre_real_estate"
    }
  ]
}
```

Estados esperados: `QUEUED`, `RUNNING`, `CANCELLING`, `CANCELLED`,
`COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`.

## Configuracion

`GET /settings` no devuelve secretos, solo banderas:

```json
{
  "has_cmf_api_key": false,
  "has_mercado_publico_ticket": false,
  "has_mercadolibre_access_token": false
}
```

`PUT /settings` permite cargar en memoria del backend:

```json
{
  "mercado_publico_ticket": "...",
  "mercadolibre_access_token": "...",
  "cmf_api_key": "..."
}
```

## Contrato de propiedad resumida

Campos principales de `GET /properties`:

```json
{
  "items": [
    {
      "internal_id": "uuid",
      "source": "mercadolibre_real_estate",
      "source_type": "marketplace",
      "external_id": "MLC...",
      "canonical_url": "https://...",
      "publication_title": "Terreno urbano",
      "region": "Metropolitana de Santiago",
      "commune": "Maipu",
      "latitude": -33.5,
      "longitude": -70.7,
      "asking_price_clp": 100000000,
      "asking_price_uf": 2500,
      "uf_date": "2026-08-30",
      "gross_area_m2": 10000,
      "price_uf_m2_gross": 0.25,
      "data_quality_score": 70,
      "anomaly_flags_json": "[]"
    }
  ],
  "limit": 50,
  "offset": 0,
  "total": 1
}
```

## Seguridad

- Secretos no se versionan.
- El backend rechaza hosts distintos a `127.0.0.1`.
- Mercado Publico requiere `MERCADO_PUBLICO_TICKET`.
- MercadoLibre requiere `MERCADOLIBRE_ACCESS_TOKEN`.
- CMF UF requiere `CMF_API_KEY` o `UF_CMF_API_KEY`.
- Las reglas DS49/DS19 no verificadas no descartan automaticamente.
