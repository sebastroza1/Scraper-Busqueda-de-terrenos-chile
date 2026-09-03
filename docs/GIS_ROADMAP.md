# GIS Roadmap

Este roadmap describe la arquitectura futura posterior al MVP GIS MINVU. No
implementa reglas legales automaticas ni scores DS49/DS19 en esta iteracion.

## Principios

- Priorizar APIs oficiales, servicios ArcGIS REST/WFS/WMS y datos descargables
  verificables.
- Guardar evidencia por indicador: fuente, URL, capa, id de registro, fecha,
  confianza y metadata cruda.
- Separar ubicacion aproximada, punto verificado y poligono predial real.
- Usar CRS del servicio y reproyeccion explicita; calcular metros y superficies
  solo en CRS metrico adecuado.
- Cachear consultas por servicio, capa, geometria, query y spatial reference.
- Mantener cada dominio como conector independiente y activar capas bajo demanda.

## Fuentes Futuras

| Dominio | Arquitectura propuesta | Estado |
|---|---|---|
| 1. SII/catastro | Conector catastral separado con rol, destino, superficie oficial y geometria solo si existe fuente estructurada autorizada. | Pendiente |
| 2. CONAF | Conector de capas oficiales para bosque nativo, areas protegidas e incendio forestal cuando exista servicio estructurado. | Pendiente |
| 3. DGA | Conector oficial para cauces, derechos de agua, acuiferos y restricciones hidricas. | Pendiente |
| 4. Humedales | Conector de inventarios oficiales MMA/IDE Chile; interseccion predial con evidencia de capa. | Pendiente |
| 5. Riesgos naturales | Agregar remocion en masa, inundacion, tsunami, volcanismo y fallas desde fuentes oficiales auditadas. | Pendiente |
| 6. Transporte | Capas de paraderos, estaciones, corredores y tiempos de acceso; separar distancia euclidiana de red vial. | Pendiente |
| 7. Colegios | Conector de establecimientos oficiales MINEDUC; calcular proximidad y cobertura sin inferir calidad educativa. | Pendiente |
| 8. Salud | Conector MINSAL/DEIS para centros de salud; indicadores de distancia y tipo de prestacion. | Pendiente |
| 9. Areas verdes | Capas municipales/IDE Chile para plazas, parques y areas verdes; interseccion y distancia. | Pendiente |
| 10. DEM/topografia | Raster DEM oficial; pendientes, orientacion, variabilidad y advertencias de resolucion. | Pendiente |
| 11. Vialidad | Red vial oficial; acceso a via publica, jerarquia y distancia, sin afirmar frente legal sin evidencia. | Pendiente |
| 12. Superficie neta desarrollable | Motor de exclusiones por capas verificadas: riesgo, proteccion, utilidad publica, cesiones y pendientes. | Pendiente |
| 13. DS49 | Reglas parametrizadas por convocatoria, ano y fuente legal; ejecutar solo con datos verificables. | Pendiente |
| 14. DS19 | Reglas parametrizadas por convocatoria, ano y fuente legal; separar elegibilidad preliminar de veredicto. | Pendiente |
| 15. Cabida preliminar | Modulo de escenarios con supuestos explicitos; no usar como cabida normativa definitiva. | Pendiente |

## Modulos Recomendados

1. `connectors.geo`: conectores oficiales por institucion.
2. `geospatial`: cache, reproyeccion, metricas e intersecciones.
3. `evidence`: trazabilidad de cada campo mostrado en UI.
4. `urbanism`: interpretacion auditada de IPT por comuna/capa.
5. `rules`: reglas DS49/DS19 versionadas por fuente legal.
6. `reports`: anexos Excel/PDF con matriz de evidencia.

## Proxima Fase Recomendada

Auditar esquemas reales de PRC por region/comuna y construir un `IptSchemaMapper`
que pueda declarar, por capa, cuales atributos representan zona, norma, fecha,
instrumento y fuente. Solo despues de esa auditoria se deben incorporar
densidad, constructibilidad, altura, ocupacion o uso residencial.

## Estado Implementado En 2026-08-31

- `MinvuArcGisConnector` consulta servicios ArcGIS REST oficiales.
- `MinvuIptCatalog` descubre servicios IPT, audita capas y cachea metadatos.
- La determinacion de PRC/zona usa interseccion espacial y atributos auditados
  de zona cuando existen.
- `TerritorialAnalyzer` guarda evidencia para limite urbano, riesgo y PRC/zona.
- La UI muestra evidencia y mapa base real con capas activables.

## Pendiente Antes De Normativa Urbanistica Fina

- Auditar alias/campos por capa PRC y comuna.
- Versionar un mapeo explicito por IPT vigente.
- Asociar cada zona a ordenanza/documento fuente.
- Incorporar fechas de publicacion/modificacion del IPT.
- Solo despues calcular o mostrar densidad, constructibilidad, altura,
  ocupacion, uso residencial o superficie neta desarrollable.
