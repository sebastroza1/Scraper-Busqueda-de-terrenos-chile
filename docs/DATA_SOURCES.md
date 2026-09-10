# Landfinder Chile - Fuentes de datos

Fecha de revisión: 2026-09-09

La fuente de verdad del registro es `config/sources_registry.json`. Este documento resume su uso en el MVP y separa fuentes operativas, parciales, pendientes y candidatas.

## Modelo de trazabilidad

Cada resultado relevante debe preservar, cuando la fuente lo permite:

- `sourceId`;
- `sourceName`;
- `sourceUrl`;
- `retrievedAt`;
- `externalId`;
- atributos originales no sensibles;
- distancia al área o punto de análisis.

El MVP actual conserva trazabilidad en estados de fuente, popups OSM, registros GIS y exportación JSON.

## Fuentes operativas o integradas en mapa

| ID | Nombre | Finalidad | Autenticación | Endpoint/base | Estado |
|---|---|---|---:|---|---|
| `osm_overpass` | OpenStreetMap / Overpass | Equipamientos, construcciones, estaciones y geometría metro disponible | No | `https://overpass-api.de/api/interpreter` | funcional desde red abierta; puede fallar por conexión/rate limit |
| `osm_nominatim` | OpenStreetMap / Nominatim | Geocoding de direcciones chilenas | No | `https://nominatim.openstreetmap.org/search` | funcional desde red abierta; requiere respetar política de uso |
| `minvu_limites_urbanos` | MINVU Límites Urbanos | Contexto urbano/IPT | No | ArcGIS FeatureServer | parcial |
| `minvu_prms_uso_suelo` | MINVU PRMS uso suelo | Planificación RM | No | ArcGIS FeatureServer layer | parcial |
| `minvu_area_riesgo` | MINVU Áreas de Riesgo | Riesgos IPT | No | ArcGIS FeatureServer | parcial |
| `mma_humedales` | MMA Humedales | Ambiental, territorio y riesgo | No | ArcGIS FeatureServer | parcial |
| `mma_areas_protegidas` | MMA Áreas Protegidas | Protección ambiental | No | ArcGIS FeatureServer | parcial |
| `sea_proyectos` | SEA / SEIA Proyectos | Proyectos ambientales | No | ArcGIS MapServer | parcial |
| `mop_contratos_obras` | MOP Obras | Obras y contratos públicos | No | ArcGIS MapServer | parcial |
| `mop_red_vial` | MOP Red Vial | Accesibilidad/contexto vial | No | ArcGIS layer | parcial |
| `dga_derechos` | DGA Derechos de Aprovechamiento | Contexto hídrico | No | ArcGIS MOP/SNIA | parcial |
| `dga_prohibiciones` | DGA Zonas de Prohibición | Restricción hídrica | No | ArcGIS layer | parcial |
| `ide_hidrografia` | IDE Chile Hidrografía | Cuerpos/cursos de agua | No | WMS/WFS derivado cuando exista | parcial/visual |
| `minsal_salud_2026` | MINSAL Salud 2026 | Establecimientos de salud | No | WFS Geoportal | parcial |
| `senapred_tsunami` | SENAPRED Tsunami 2024 | Amenaza costera | No | ArcGIS FeatureServer | parcial |
| `sernageomin_relaves` | SERNAGEOMIN Relaves | Riesgo/contexto minero | No | ArcGIS FeatureServer layer | parcial |
| `sernageomin_instalaciones_mineras` | SERNAGEOMIN Instalaciones Mineras | Contexto minero | No | ArcGIS FeatureServer | parcial |
| `energia_lineas_transmision` | Energía Líneas de transmisión | Infraestructura eléctrica | No | ArcGIS MapServer layer | parcial |
| `energia_subestaciones` | Energía Subestaciones | Infraestructura eléctrica | No | ArcGIS MapServer layer | parcial |

## Fuentes para health check o descubrimiento

| ID | Nombre | Finalidad | Estado |
|---|---|---|---|
| `chilecompra_ocds` | ChileCompra OCDS | Demanda pública e inversión | funcional/parcial según canary |
| `bip_mdsf` | BIP MDSF | Iniciativas de inversión | funcional/parcial |
| `dtpm_gtfs` | DTPM GTFS | Transporte RM futuro | descubrimiento, no conectado al mapa |
| `ide_geoportal_catalog` | IDE Chile Catálogo | Descubrimiento de datasets | discovery only |
| `mbn_snap_catalog` | SNAP catálogo | Referencia ambiental | reference only |
| `osm_tile` | OpenStreetMap tile | Canary de mapa base | funcional para prueba liviana |

## Fuentes pendientes o no configuradas

| ID | Nombre | Motivo |
|---|---|---|
| `siss_gap` | Servicio sanitario urbano | Falta endpoint estable validado |
| `cnr_api_portal` | API CNR | Requiere credenciales/access token |
| `sii_catastro_gap` | SII Catastro/Avalúos | No hay API pública formal configurada |
| `mercadolibre_gap` | MercadoLibre oferta | No debe ser dependencia del MVP; falta API/permiso validado |
| `portal_inmobiliario_gap` | Portal Inmobiliario oferta | No hay API oficial configurada |

## Estado legal

Muchas fuentes figuran con `LEGAL_REVIEW`, `PENDIENTE` o `REVISAR`. Eso significa:

- pueden usarse para prototipo local;
- no deben tratarse automáticamente como autorizadas para explotación comercial;
- deben revisarse términos, licencias, límites de uso y atribución antes de producción.

## QA de fuentes

Durante la validación local del 2026-09-09:

- `test_registry.py` cargó correctamente 42 fuentes;
- `compileall` pasó;
- la app mostró estados de error aislados cuando Overpass no respondió;
- Nominatim respondió correctamente para una búsqueda de dirección de Ñuñoa con red permitida;
- no se detectó dependencia crítica de una sola fuente.

## Reglas de producto

- Una fuente caída no bloquea el mapa ni el resto de capas.
- Un resultado debe mostrar su procedencia.
- Si una fuente no tiene geometría, no se inventa.
- Si un trazado de Metro futuro no está disponible en OSM u otra fuente real conectada, no se dibuja.
- Si no hay fuente inmobiliaria oficial, filtros de mercado quedan preparados pero sin resultados simulados.
