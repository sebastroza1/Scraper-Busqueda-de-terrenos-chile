# Fuentes nuevas añadidas respecto de la base anterior

## Alta prioridad

### Ministerio de Bienes Nacionales
Se añadió el WMS de **Propiedad Fiscal Administrada** encontrado en el
Geoportal IDE Chile. Esto corrige una brecha de la auditoría anterior: ahora
hay un servicio geoespacial identificable para probar, pero sigue pendiente
el gate legal/operativo antes de producción.

### SENAPRED
- Amenaza por Tsunami 2024.
- Amenaza por Incendio Forestal histórica.

La capa de incendio es antigua y queda como contexto, no como riesgo actual.

### MOP / DOH
- Servicios Sanitarios Rurales.
- Contratos de Obras MOP.
- Emergencias sobre infraestructura MOP.
- Zonas de Descanso.

### Ministerio de Energía
- Subestaciones.
- Líneas de transmisión.

Estas fuentes sirven como contexto de infraestructura. No reemplazan
certificados de factibilidad ni antecedentes legales de servidumbres.

### MINSAL
WFS de establecimientos de salud publicado con fecha 12-06-2026.

### IDE Chile
WMS de hidrografía parcial Arica-O'Higgins y monitor del catálogo nacional.

### CNR
Se registra el portal oficial de desarrolladores. La API requiere token y
autenticación básica, por lo que el estado esperado sin credenciales es
`AUTH_REQUIRED`.

## Contexto secundario

Se añadieron WMS de:
- establecimientos escolares;
- jardines JUNJI;
- municipios;
- compañías de bomberos;
- cuarteles de Carabineros.

Varios son antiguos y por eso quedan P2/CONTEXT_ONLY.

## Brechas que siguen abiertas

- SISS urbano: endpoint directo estable pendiente.
- SII/catastro: no se incorpora scraping ni endpoint privado/indocumentado.
- Portales inmobiliarios: fuera del MVP crítico.
- SERNAGEOMIN: candidato importante, pero no se inventa un endpoint GIS
  productivo mientras no se documente/valide uno estable.

## Nota

Que una URL responda no significa que su reutilización comercial esté
autorizada. El monitor separa deliberadamente `technical_status` y
`legal_gate`.
