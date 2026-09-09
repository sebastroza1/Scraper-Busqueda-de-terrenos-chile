# Revisión de la primera ejecución real

Resumen recibido:

- 29 fuentes probadas.
- 20 OK.
- 1 DEGRADED.
- 5 SOURCE_ERROR.
- 1 AUTH_REQUIRED.
- 2 NOT_CONFIGURED.

## Hallazgos

### Correctos / esperados
- CIREN respondió y fue correctamente mantenido como PROTOTYPE_ONLY.
- MINVU Límites, Riesgos y PRMS respondieron.
- MMA Humedales y Áreas Protegidas respondieron.
- DGA Derechos respondió.
- SEA respondió.
- BIP CKAN respondió y descubrió recursos 2019-2027.
- Bienes Nacionales WMS respondió.
- SENAPRED, Energía, MOP Obras/Emergencias, MINSAL y GTFS respondieron.
- CNR AUTH_REQUIRED es el comportamiento esperado.
- SISS/SII NOT_CONFIGURED son brechas intencionales.

### Errores que la v0.4 corrige
1. `PRC_Metropolitana`: endpoint incorrecto/404.
   Se reemplaza por `PRC_RM_Norte` y `PRC_RM_Sur`.
2. ChileCompra aparecía DEGRADED porque la página depende de JavaScript.
   Ahora se prueba la API OCDS real.
3. DTPM detectaba links visuales de contraste/width.
   Ahora prioriza archivos/servicios de datos reales.
4. MOP tuvo timeouts aislados.
   Se aumenta el timeout para ese host y se agrega un retry.
5. SERNAGEOMIN falló por TLS en una página web.
   Se reemplaza como prueba principal por FeatureServers GIS.

## Mapa
La v0.3 era un Source Lab, no un visor territorial. La v0.4 agrega la
pestaña `Mapa` y consultas geoespaciales por bbox alrededor del terreno.
