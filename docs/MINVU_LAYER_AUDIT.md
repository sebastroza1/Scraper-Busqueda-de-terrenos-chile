# MINVU Layer Audit

Fecha: 2026-08-31

## Estado

`PARTIAL_LIVE_AUDIT`

Se implemento `MinvuIptCatalog` para descubrir servicios IPT desde IDE MINVU
ArcGIS REST y auditar capas sin mantener una lista manual gigante. La auditoria
usa metadatos de servicios/capas y, cuando se solicita, conteo `returnCountOnly`
para no descargar features completas.

## Endpoint Base

```text
https://geoide.minvu.cl/server/rest/services
```

## Servicios Detectados Para Region Metropolitana

Consulta live:

```text
https://geoide.minvu.cl/server/rest/services/IPT?f=json
```

Resultado:

```json
{
  "service_count": 6,
  "services": [
    "IPT/PRC_RM_Norte",
    "IPT/PRC_RM_Sur",
    "IPT/PRMC",
    "IPT/PRMC",
    "IPT/PRMS",
    "IPT/PRMS"
  ],
  "warnings": []
}
```

## Capa Auditada Live: PRC Santiago

| Campo | Valor |
|---|---|
| service | `https://geoide.minvu.cl/server/rest/services/IPT/PRC_RM_Norte/MapServer` |
| layer_id | `31` |
| layer_name | `PRC_Santiago` |
| geometry_type | `esriGeometryPolygon` |
| spatial_reference | `EPSG:32719` |
| capabilities | `Map,Query,Data` |
| feature_count | `192` |
| last_checked | `2026-08-31` |

Schema real consultado:

| field | alias | type |
|---|---|---|
| `REG` | Region | `esriFieldTypeString` |
| `COM` | Comuna | `esriFieldTypeString` |
| `ZONA` | Zona | `esriFieldTypeString` |
| `NOM` | Nombre de zona | `esriFieldTypeString` |
| `LOC` | Localidad | `esriFieldTypeString` |
| `UPERM` | Uso permitido | `esriFieldTypeString` |
| `UPROH` | Uso prohibido | `esriFieldTypeString` |
| `P_DO` | Fecha publicacion en DO | `esriFieldTypeString` |
| `N_DOC` | Numero de documento | `esriFieldTypeString` |
| `T_DO` | Tipo de documento | `esriFieldTypeString` |
| `OBS` | Observacion | `esriFieldTypeString` |
| `OBJECTID` | OBJECTID_1 | `esriFieldTypeOID` |
| `Shape` | Shape | `esriFieldTypeGeometry` |

## Consulta Puntual De Zona

Coordenada usada:

```json
{
  "latitude": -33.4489,
  "longitude": -70.6693
}
```

Endpoint:

```text
https://geoide.minvu.cl/server/rest/services/IPT/PRC_RM_Norte/MapServer/31/query
```

Resultado:

```json
{
  "feature_count": 1,
  "attributes": {
    "REG": "Metropolitana",
    "COM": "Santiago",
    "ZONA": "B",
    "NOM": "Zona B",
    "LOC": "Santiago",
    "P_DO": "27/01/1990",
    "N_DOC": "26",
    "T_DO": "Resolucion",
    "OBJECTID": 29
  }
}
```

`UPERM` y `UPROH` fueron recibidos como atributos crudos de la capa, pero no se
interpretan todavia como reglas automaticas de uso, densidad, altura,
constructibilidad, ocupacion ni subdivisiones.

## Campos Del Catalogo

Cada entrada auditada por `MinvuIptCatalog.layer_audit` expone:

```text
service
layer_id
layer_name
geometry_type
spatial_reference
fields
field_aliases
feature_count
feature_count_status
capabilities
last_checked/retrieved_at
```

## Semantica De Zona

`UrbanZoneResult` se crea solo cuando una feature intersectada entrega
explicitamente un atributo de zona.

Campos:

```text
zone_code
zone_name
instrument
commune
source_service
source_layer
raw_attributes
retrieved_at
confidence
```

## Pendiente

- Auditar PRC por comuna/region con fixtures live acotados.
- Confirmar vigencia normativa contra documento/ordenanza fuente.
- Crear mapeo versionado de alias de campos por IPT.
- No interpretar automaticamente `UPERM`, `UPROH`, densidad,
  constructibilidad, altura, ocupacion ni subdivision minima hasta tener
  auditoria normativa.
