# Revisión visual de mapa - primera prueba

## Confirmado
- El mapa base OpenStreetMap renderiza.
- El punto de análisis y círculo de radio renderizan.
- MINVU Límites Urbanos se dibuja correctamente.
- MINVU PRMS se dibuja.
- SEA/SEIA devuelve elementos espaciales.
- La tabla separa OK/0 elementos de SOURCE_ERROR.

## Problema detectado
DGA Derechos, DGA Prohibiciones, MOP Red Vial y MOP SSR devolvieron HTTP 400
solo en la consulta espacial del mapa, aunque el health check era OK.

## Causa
La consulta espacial de v0.4 intentaba `f=geojson` y aplicaba
`raise_for_status()` antes de la ruta de fallback. ArcGIS Server antiguos
pueden rechazar ese formato o `resultRecordCount`.

## Corrección
v0.4.1 usa Esri JSON como formato primario, envelope JSON EPSG:4326 y retry
sin `resultRecordCount`.

## Observación
El título visible en capturas seguía mostrando v0.3. Se corrige en v0.4.1.
