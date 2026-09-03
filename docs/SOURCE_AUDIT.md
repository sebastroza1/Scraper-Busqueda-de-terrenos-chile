# Source Audit

Fecha de auditoria inicial: 2026-08-30

Esta auditoria no prueba scrapers ni declara que una fuente sea automatizable.
Solo registra evidencia publica revisada y la estrategia recomendada. Donde no
hay API, permiso o estructura confirmada se usa `TO_VERIFY`.

## Estados

- `ACTIVE`: existe interfaz oficial/documentada utilizable bajo sus condiciones.
- `PARTIAL`: hay datos publicos o estructura visible, pero falta confirmar
  cobertura, permisos, limites o estabilidad.
- `MANUAL`: debe operar mediante carga/asistencia humana.
- `BLOCKED`: automatizacion no permitida o fuente protegida.
- `TO_VERIFY`: requiere auditoria especifica antes de implementar.

## Evidencia consultada

- [Mercado Publico API](https://www.chilecompra.cl/api/): documenta API publica
  con ticket, JSON/XML/JSONP, licitaciones, ordenes de compra, proveedores,
  condiciones de uso y limite diario.
- [MercadoLibre Developers - Inmuebles](https://developers.mercadolibre.cl/):
  documenta guias de inmuebles, publicacion, busqueda y ubicacion con OAuth.
- [MercadoLibre Items & Searches](https://developers.mercadolibre.cl/en_us/api-docs/items-and-searches):
  documenta recursos de busqueda de items activos.
- [MercadoLibre Publica Inmuebles](https://developers.mercadolibre.cl/publica-inmueble):
  indica integracion de inmuebles y uso de `CMG_SITE` para PortalInmobiliario
  en Chile.
- [IDE MINVU ArcGIS REST](https://geoide.minvu.cl/server/rest/services):
  expone directorio ArcGIS REST con carpetas IPT, Suelo, Urbano, Subsidios,
  Proyectos Habitacionales y otros.
- [IDE Chile](https://www.ide.cl/): portal nacional con catalogo, servicios
  OGC, datos abiertos y geonodo.
- [CMF UF API](https://api.cmfchile.cl/documentacion/UF.html): documenta
  recurso UF por fecha, mes, anio y rangos, con API key.
- [Portal de Licitaciones MBN](https://licitaciones.mbienes.gob.cl/): publica
  ventas, concesiones y arriendos de inmuebles fiscales.
- [TGR Remates](https://remates.tgr.cl/): publica propiedades en remate y avisos
  PDF, sin API verificada.
- [BancoEstado Propiedades en Remate](https://nwm.bancoestado.cl/content/bancoestado-public/cl/es/home/home/informate/propiedades-en-remate.html):
  publica listados referenciales y deriva a agentes externos.
- [SII Cartografia Digital](https://www4.sii.cl/mapasui/internet/#/contenido/index.html):
  aplicacion grafica oficial de bienes raices; no se verifico API publica.
- [MMA Humedales Urbanos FeatureServer](https://arcgis.mma.gob.cl/server/rest/services/MMA/HUMEDALES_URBANOS/FeatureServer):
  servicio ArcGIS para humedales urbanos.
- [MOP/DGA ArcGIS REST](https://rest-sit.mop.gob.cl/arcgis/rest/services/DGA):
  carpeta ArcGIS REST con capas DGA.
- [IDE Minagri Servicios](https://ide.minagri.gob.cl/geoweb/directorio-de-servicios/):
  lista servicios WMS/WFS/WCS/CSW, incluyendo recursos forestales y propiedades
  rurales.

## Fuentes inmobiliarias

| Fuente | URL oficial | API disponible | Auth | Campos obtenibles esperados | Geo | Imagenes | Estrategia | Estado | Notas |
|---|---|---:|---|---|---|---|---|---|---|
| MercadoLibre Inmuebles | https://www.mercadolibre.cl/inmuebles | Si, API oficial ML | OAuth | item id, titulo, precio, moneda, atributos, ubicacion, fotos segun API | Parcial segun `location` y filtros | Si, via `pictures` | `official_api` | `PARTIAL` | Falta validar categorias chilenas de terrenos y alcance exacto de resultados con token real. |
| PortalInmobiliario | https://www.portalinmobiliario.com/ | Parcial, via ecosistema ML | OAuth | similar ML; `CMG_SITE` documentado para publicar en PortalInmobiliario | Parcial | Si | `official_api` primero | `PARTIAL` | Documentada integracion de publicacion; falta probar busqueda de listings PortalInmobiliario desde API. |
| TocToc | https://www.toctoc.com/ | No verificada | TO_VERIFY | publicaciones, precio, comuna, superficie si HTML lo permite | TO_VERIFY | TO_VERIFY | auditoria ToS/robots, luego `html` o manual | `TO_VERIFY` | No implementar hasta verificar permisos y estabilidad. |
| Yapo.cl | https://www.yapo.cl/ | No verificada | TO_VERIFY | publicaciones clasificadas | TO_VERIFY | TO_VERIFY | auditoria ToS/robots, luego `html` o manual | `TO_VERIFY` | Existe sitio publico; no se encontro documentacion API inmobiliaria oficial para consumo. |
| LUN Propiedades | TO_VERIFY | No verificada | TO_VERIFY | TO_VERIFY | TO_VERIFY | TO_VERIFY | `manual_assisted` hasta encontrar portal oficial | `TO_VERIFY` | No se confirmo URL canonica actual en esta auditoria rapida. |
| Emol Propiedades | https://www.propiedades.emol.com/ | No verificada | No verificada | titulo, precio, comuna, tipo, superficie, fecha visible en resultados | Parcial | Si | `html` solo si ToS/robots lo permiten | `PARTIAL` | Busqueda publica SSR visible; requiere fixture y permiso antes de automatizar. |

## Corretaje y macrolotes

| Fuente | URL oficial | API disponible | Auth | Campos obtenibles esperados | Geo | Imagenes | Estrategia | Estado | Notas |
|---|---|---:|---|---|---|---|---|---|---|
| ProUrbano | https://prourbano.cl/ | No verificada | No verificada | destacados, precio UF, tipo, area en algunos casos | Baja | Si | `html` o `manual_assisted` | `PARTIAL` | Sitio publico con propiedades destacadas; falta ToS/robots y detalle. |
| GPS Property | https://gpsproperty.cl/ | No verificada | No verificada | codigo, comuna, tipo, precio UF, superficie | Parcial | Si | `html` o `manual_assisted` | `PARTIAL` | Sitio muestra codigos y terrenos; candidato a WatchConnector con fixture. |
| Colliers Chile | https://www.colliers.com/es-cl | No verificada | No verificada | reportes y enlaces a propiedades | Parcial | Si | `manual_assisted` o ML store si procede | `PARTIAL` | Existe tienda Colliers en PortalInmobiliario; preferir API ML si cubre activos. |
| CBRE Chile | https://www.cbre.cl/ | No verificada | No verificada | oportunidades, servicios, reportes | TO_VERIFY | TO_VERIFY | `manual_assisted` / `watch` | `TO_VERIFY` | No automatizar sin revisar portal de propiedades y permisos. |
| Gestateco | TO_VERIFY | No verificada | TO_VERIFY | TO_VERIFY | TO_VERIFY | TO_VERIFY | `manual_assisted` | `TO_VERIFY` | Nombre/URL requieren confirmacion. |

## Publicas, remates y licitaciones

| Fuente | URL oficial | API disponible | Auth | Campos obtenibles esperados | Geo | Imagenes/docs | Estrategia | Estado | Notas |
|---|---|---:|---|---|---|---|---|---|---|
| Mercado Publico / ChileCompra | https://www.chilecompra.cl/api/ | Si | Ticket oficial | licitaciones, OC, compradores, proveedores, estados, fechas | No nativo | Bases/documentos fuera de una consulta completa | `official_api` | `ACTIVE` | Usar keywords configurables. Respeta limite diario y condiciones. |
| Ministerio de Bienes Nacionales | https://licitaciones.mbienes.gob.cl/ | No verificada | No verificada | inmuebles fiscales, region, uso, estado, bases | Si, mapa publico | Bases | `html`/`manual_assisted` tras auditoria | `PARTIAL` | Portal especifico y relevante; buen candidato de vigilancia. |
| SERVIU / MINVU | https://www.minvu.gob.cl/ | Parcial | Depende | llamados DS49/DS19, concursos, resoluciones, terrenos SERVIU | Parcial via IDE MINVU | PDFs | `open_data`/`html`/`manual_assisted` | `PARTIAL` | Reglas se extraen de resoluciones, no se inventan. |
| TGR Remates | https://remates.tgr.cl/ | No verificada | No verificada | fecha, tribunal, rol, ubicacion, avaluo/tasacion, PDF | Direccion/rol | PDFs | `html`/`pdf` tras auditoria | `PARTIAL` | Contiene datos sensibles; limitar campos y trazabilidad. |
| SUPERIR / Boletin Concursal | https://www.superir.gob.cl/ | No verificada | No verificada | boletin, publicidad de remates | TO_VERIFY | PDFs/docs | `watch`/`manual_assisted` | `PARTIAL` | Requiere validar buscador y terminos. |
| BancoEstado Remates | https://nwm.bancoestado.cl/content/bancoestado-public/cl/es/home/home/informate/propiedades-en-remate.html | No verificada | No | listados referenciales, comuna, direccion, fecha | Direccion | Deriva a Macal/Tattersall | `watch`/`manual_assisted` | `PARTIAL` | El propio sitio indica informacion referencial y agentes externos. |
| EFE | TO_VERIFY | No verificada | TO_VERIFY | oportunidades ocasionales | TO_VERIFY | TO_VERIFY | `WatchConnector` | `TO_VERIFY` | No asumir portal inmobiliario permanente. |
| CODELCO | https://www.codelco.com/licitaciones-en-proceso | No API verificada | Depende de Ariba/email | licitaciones en proceso | No | Bases condicionadas | `watch` | `PARTIAL` | No esta orientado a terrenos; monitoreo por keywords. |
| CAPREDENA | https://www.capredena.gob.cl/ | No verificada | TO_VERIFY | compras/licitaciones | TO_VERIFY | TO_VERIFY | Mercado Publico + watch | `TO_VERIFY` | Priorizar API Mercado Publico por organismo si aplica. |
| DIPRECA | https://dipreca.gob.cl/ | No verificada | TO_VERIFY | compras/licitaciones | TO_VERIFY | TO_VERIFY | Mercado Publico + watch | `TO_VERIFY` | Priorizar Mercado Publico; no se verifico portal de inmuebles. |
| Ejercito | https://www.ejercito.cl/propuesta-publica | No API verificada | No verificada | propuestas publicas, PDFs, inmuebles ocasionales | Baja | PDFs | `watch`/`pdf` | `PARTIAL` | Se observo propuesta publica con venta inmueble historica. |
| Armada | https://www.armada.cl/ | No API verificada | TO_VERIFY | transparencia/contratos, oportunidades ocasionales | Baja | PDFs | `watch` | `TO_VERIFY` | Usar transparencia y Mercado Publico; no asumir portal de ventas. |
| Fuerza Aerea | https://fach.mil.cl/licitaciones-publicas-de-obras-de-la-fuerza-aerea-de-chile | No API verificada | Registro/MP en algunos casos | obras, registro, licitaciones | Baja | Documentos | `watch` | `PARTIAL` | Algunas publicaciones remiten a Mercado Publico. |
| Municipios | Variable | Variable | Variable | adquisiciones/ventas/PRC/CIP | Variable | PDFs | Mercado Publico + `watch` | `TO_VERIFY` | Auditar comuna por comuna. |

## Geoespaciales y normativas

| Fuente | URL oficial | API/servicio | Auth | Datos | Estrategia | Estado | Notas |
|---|---|---|---|---|---|---|---|
| IDE MINVU | https://geoide.minvu.cl/server/rest/services | ArcGIS REST | No verificada como abierta por capa | IPT, suelo, urbano, subsidios, proyectos | `arcgis_rest` | `ACTIVE` | Verificar capa especifica, CRS y atributos antes de usar. |
| Observatorio Urbano / Centro Estudios MINVU | https://centrodeestudios.minvu.gob.cl/ | Descargas/catalogo | No verificada | estadisticas, vivienda, permisos | `open_data` | `PARTIAL` | Datos agregados, no reemplazan CIP. |
| IDE Chile | https://www.ide.cl/ | OGC/CSW/Geoportal | Publico | capas y metadatos estatales | `wms`/`wfs`/`geojson` | `ACTIVE` | Punto de entrada para catalogo nacional. |
| SII Cartografia | https://www4.sii.cl/mapasui/internet/#/contenido/index.html | No API publica verificada | Puede tener areas publicas y privadas | rol, avaluo, superficie, destino segun consulta | `manual_assisted` | `MANUAL` | No automatizar datos privados ni acceso autenticado. |
| CMF UF | https://api.cmfchile.cl/documentacion/UF.html | API | API key | valor UF por fecha | `official_api` | `ACTIVE` | Toda conversion UF debe guardar fecha exacta. |
| MMA Humedales | https://arcgis.mma.gob.cl/server/rest/services/MMA/HUMEDALES_URBANOS/FeatureServer | ArcGIS FeatureServer | No verificada | humedales urbanos | `arcgis_rest` | `ACTIVE` | Confirmar vigencia y campos antes de reglas. |
| DGA / MOP | https://rest-sit.mop.gob.cl/arcgis/rest/services/DGA | ArcGIS REST | No verificada | acuiferos, escasez, restricciones, red hidrometrica | `arcgis_rest` | `ACTIVE` | Capas utiles para riesgos hidricos. |
| CONAF / Minagri | https://ide.minagri.gob.cl/geoweb/directorio-de-servicios/ | WMS/WFS/WCS/descargas | No verificada | recursos forestales, propiedades rurales, incendios | `wms`/`wfs`/`open_data` | `PARTIAL` | Confirmar licencia/capa y resolucion por caso. |
| Areas protegidas | IDE Chile / MMA / CONAF | Mixto | No verificada | SNASPE, areas protegidas, santuarios | `arcgis_rest`/`wfs` | `TO_VERIFY` | Seleccionar fuente oficial por capa. |
| IPT comunales PRC/PRI/PRM | Municipios / MINVU | Mixto | Variable | zonificacion, limite urbano, afectaciones | `arcgis_rest`/`pdf`/`manual` | `TO_VERIFY` | Requiere version vigente y documento fuente. |

## MVP recomendado

1. Mercado Publico API para licitaciones con keywords.
2. MercadoLibre / PortalInmobiliario por API oficial, condicionado a token OAuth
   y validacion de categorias chilenas de terrenos.
3. CMF UF como enriquecimiento base, no como fuente inmobiliaria.
4. IDE MINVU, MBN, TGR, BancoEstado, SERVIU y otros quedan postergados hasta
   una fase posterior con auditoria y autorizacion explicita.
5. No implementar fuentes HTML privadas ni fuentes masivas nuevas en el MVP
   actual.

## Auditorias Especificas 2026-08-31

- MercadoLibre Real Estate: `docs/MERCADOLIBRE_REAL_ESTATE_AUDIT.md`.
- MINVU IPT layers: `docs/MINVU_LAYER_AUDIT.md`.
- SII catastro: `docs/SII_CADASTRAL_AUDIT.md`.

## Datos automaticos vs revision manual

Automaticos con fuente confirmada:

- UF por fecha desde CMF con API key.
- Licitaciones Mercado Publico con ticket.
- Capas GIS oficiales con servicios ArcGIS/OGC disponibles.
- Metadatos de publicaciones desde API ML si el token y las categorias lo
  permiten.

Revision manual o asistida:

- CIP y certificados DOM.
- Estudio de titulos, gravamenes, promesa y escritura.
- Factibilidad sanitaria/electrica formal.
- Tasacion.
- Reglas DS49/DS19 de llamados no cargados desde resolucion oficial.
- Fuentes privadas sin API o sin permiso confirmado.
- Datos SII que requieran autenticacion, representacion o informacion privada.
