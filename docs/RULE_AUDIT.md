# Rule Audit

Fecha de auditoria: 2026-08-30

## Criterio

Las reglas DS49/DS19 existentes son marcadores de estructura, no reglas
normativas verificadas. Ninguna tiene resolucion oficial, URL normativa,
valor normativo ni ambito geografico confirmado en el repositorio.

Por lo tanto, todas quedan con:

```yaml
verified: false
status: TO_VERIFY
automatic: false
```

Estas reglas no deben utilizarse para descartar automaticamente terrenos.

## Auditoria por regla

| rule_id | fuente oficial | resolucion/llamado | URL | valor normativo | anio | ambito geografico | verified | status | automatic | conclusion |
|---|---|---|---|---|---:|---|---:|---|---:|---|
| DS49_2026_CIP_REQUIRED | TO_VERIFY_MINVU_RESOLUTION | TO_VERIFY | null | UNKNOWN | 2026 | UNKNOWN | false | TO_VERIFY | false | Requiere revision manual; no descarta automaticamente. |
| DS49_2026_LOCALIZATION_POLYGON | TO_VERIFY_OFFICIAL_MINVU_LAYER_OR_RESOLUTION | TO_VERIFY | null | UNKNOWN | 2026 | UNKNOWN | false | TO_VERIFY | false | No hay poligono/llamado oficial cargado; no descarta automaticamente. |
| DS49_2026_URBANISM_MANUAL_REVIEW | TO_VERIFY_MINVU_RESOLUTION_AND_CIP | TO_VERIFY | null | UNKNOWN | 2026 | UNKNOWN | false | TO_VERIFY | false | Requiere CIP/IPT vigente; no descarta automaticamente. |
| DS19_2026_CALL_APPLICABILITY | TO_VERIFY_MINVU_DS19_CALL | TO_VERIFY | null | UNKNOWN | 2026 | UNKNOWN | false | TO_VERIFY | false | DS19 independiente; no usar sin llamado oficial. |

## Auditoria de implementacion existente

| Archivo | Estado | Observacion |
|---|---|---|
| `python_engine/src/landfinder/connectors/marketplaces/mercadolibre.py` | MVP | Usa API oficial, exige OAuth, transforma resultados a registros fuente y no simula datos sin token. |
| `python_engine/src/landfinder/connectors/public_procurement/mercado_publico.py` | MVP | Usa API oficial de licitaciones con ticket y filtra por keywords con terminos negativos basicos. |
| `python_engine/src/landfinder/storage/database.py` | MVP | Inicializa SQLite mediante migraciones versionadas. |
| `python_engine/src/landfinder/storage/repositories.py` | MVP | Repositorios para candidatos, registros fuente, imagenes, historial de precios, jobs, errores y canonicos. |
| `python_engine/src/landfinder/pipeline/mvp.py` | MVP | Ejecuta discovery, normalizacion, UF, imagenes, deduplicacion, persistencia y export-ready con eventos. |
| `python_engine/src/landfinder/api/app.py` | MVP | Expone health, session, sources, audit, jobs, properties, settings, errores y export Excel. |
| `python_engine/rules/ds49/**` | Placeholder seguro | Sin valores normativos, `verified: false`, `status: TO_VERIFY`, `automatic: false`. |
| `python_engine/rules/ds19/**` | Placeholder seguro | Sin valores normativos, `verified: false`, `status: TO_VERIFY`, `automatic: false`. |

## Fuentes oficiales consultadas

- Mercado Publico API: https://www.chilecompra.cl/api/
- MercadoLibre Developers, Items & Searches: https://developers.mercadolibre.cl/en_us/api-docs/items-and-searches
- MercadoLibre Localizar Inmuebles: https://developers.mercadolibre.cl/es_cl/localizar-inmuebles
- MercadoLibre Publica Inmuebles: https://developers.mercadolibre.cl/publica-inmueble
- CMF UF API: https://api.cmfchile.cl/documentacion/UF.html
