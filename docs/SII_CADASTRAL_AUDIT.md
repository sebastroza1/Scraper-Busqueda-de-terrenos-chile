# SII Cadastral Audit

Fecha: 2026-08-31

## Estado

`PARTIAL`

SII es una fuente critica para rol, superficie oficial, destino y avaluos, pero
en esta iteracion no se implementa scraping ni acceso autenticado. No se
automatizan datos privados ni flujos con clave tributaria.

## Fuentes Oficiales Revisadas

- Servicios online de avaluos y contribuciones:
  https://www.sii.cl/servicios_online/1048-.html
- Mis bienes raices:
  https://www.sii.cl/servicios_online/1048-4544.html
- Cartografia Digital y consulta de predio:
  https://www.sii.cl/destacados/impuesto_territorial/
- Descarga de informacion de catastro y roles semestrales:
  https://www.sii.cl/servicios_online/1048-2569.html
- Nota SII 2026 sobre Cartografia Digital:
  https://www.sii.cl/noticias/2026/240626noti01smn.htm

## Datos Por Tipo

| Dato | Valor para Landfinder | Automatizacion propuesta | Estado |
|---|---|---|---|
| Rol predial | Llave catastral para cruzar fuentes. | Revisar descarga oficial de catastro/roles semestrales antes de automatizar. | `TO_VERIFY` |
| Poligono predial | Base para superficie/perimetro reales. | No automatizar desde UI grafica; buscar descarga estructurada autorizada. | `TO_VERIFY` |
| Superficie oficial | Contraste con superficie publicada/GIS. | Datos abiertos estructurados o carga manual con evidencia. | `TO_VERIFY` |
| Destino | Contexto catastral, no norma urbanistica. | Datos abiertos estructurados o carga manual. | `TO_VERIFY` |
| Avaluo afecto/exento | Referencia fiscal, no tasacion comercial. | Datos abiertos estructurados o carga manual segun permisos. | `TO_VERIFY` |
| Cartografia Digital visual | Inspeccion asistida de predio/fuentes. | Usuario revisa y adjunta evidencia; la app no scrapea. | `ASSISTED` |
| Certificados y detalle privado | Puede requerir autenticacion/representacion. | Manual asistido, no scraping. | `MANUAL` |
| CAPTCHA o controles anti-automatizacion | No corresponde evadir controles. | No implementar. | `UNAVAILABLE` |

## Restricciones

- No usar scraping visual de Cartografia Digital.
- No automatizar acceso con clave tributaria.
- No guardar datos privados sin autorizacion explicita.
- No tratar avaluo fiscal como precio comercial.
- No usar el rol para inferir superficie neta desarrollable sin geometria y
  capas de afectacion verificadas.

## Arquitectura Recomendada

1. Crear `SiiCadastralConnector` solo cuando exista una fuente estructurada
   autorizada o carga manual trazable.
2. Registrar cada campo en `EvidenceRecord`.
3. Separar `official_area_m2` de `geometry_area_m2` y `advertised_area_m2`.
4. Vincular rol/poligono solo con confianza y fecha de recuperacion.
5. Mantener SII fuera de scores DS49/DS19 hasta auditar norma y datos.

## Nota De Vigencia

El SII informa que desde el 1 de enero de 2026 algunos datos de detalle de bienes
raices pueden no estar actualizados por el proceso de Reavaluo No Agricola 2026.
La app debe conservar fecha de obtencion y advertencias de vigencia.
