# ADR Territorial Discovery

Fecha: 2026-09-01

## Estado

Propuesto. No implementado en esta iteracion.

## Contexto

Landfinder hoy descubre candidatos desde fuentes publicadas, como Mercado Publico y MercadoLibre, y luego enriquece esos registros con CMF e IDE MINVU. La siguiente etapa territorial no debe comportarse como otro portal inmobiliario: su objetivo sera identificar poligonos candidatos de suelo aparentemente disponible, no propiedades legalmente disponibles para compra.

## Decision

Crear en una fase posterior un modulo separado llamado `territorial_discovery`, con salida `candidate_land_polygons`.

La arquitectura conceptual sera:

```text
IMAGENES SATELITALES
+
CATASTRO
+
MINVU
+
COBERTURA DE SUELO
+
VIALIDAD
->
candidate_land_polygons
```

El modulo solo podra clasificar `candidate_vacant_land`. No podra afirmar disponibilidad comercial, propiedad publica/privada, aptitud legal, cabida, DS49 o DS19 sin cruces posteriores con catastro, situacion juridica e instrumentos territoriales auditados.

## Fuentes Futuras Evaluables

| Fuente | Resolucion espacial | Frecuencia | APIs | Costos | Licencia | Notas |
|---|---:|---|---|---|---|---|
| Sentinel-2 | 10 m a 60 m | 5 dias aprox. | Copernicus Data Space, STAC | Gratuito con limites operativos | Copernicus/open data | Util para cobertura de suelo regional; no identifica predios pequenos con precision legal. |
| Landsat | 15 m a 30 m | 16 dias aprox. | USGS, STAC | Gratuito | USGS/open data | Historico largo; resolucion insuficiente para muchos terrenos urbanos. |
| Copernicus Land Monitoring | Variable | Variable | Descarga/API segun producto | Gratuito segun producto | Copernicus | Puede aportar cobertura de suelo, imperviousness y cambios. |
| Ortoimagenes oficiales/locales | Variable | Variable | Depende del organismo | TO_VERIFY | TO_VERIFY | Priorizar fuentes oficiales chilenas o municipales cuando existan APIs. |

## Limitaciones

La deteccion de suelo aparentemente vacio puede producir falsos positivos por vegetacion, agricultura, canteras, estacionamientos, patios industriales, servidumbres, sitios eriazos no disponibles, suelo protegido, equipamiento publico o restricciones urbanisticas.

La resolucion espacial limita el uso de Sentinel-2 y Landsat en predios pequenos. Ninguna fuente satelital por si sola prueba disponibilidad de compra.

No se usara Google Earth mediante scraping ni automatizacion visual. Solo se consideraran APIs, servicios geoespaciales oficiales/libres o datasets con licencia compatible.

## Consecuencias

`SearchSource` seguira reservado para fuentes que publican registros u oportunidades. `territorial_discovery` producira candidatos geoespaciales con otra semantica y otra calidad de evidencia.

La validacion posterior debera cruzar catastro, normativa, riesgo, vialidad y antecedentes juridicos antes de convertir un poligono candidato en una oportunidad evaluable.
