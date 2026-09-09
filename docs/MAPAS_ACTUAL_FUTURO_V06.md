# V0.6 - Separación mapa actual / mapa futuro

## 1. Construido hoy
El mapa de valor urbano actual muestra por separado:
- malls / centros comerciales;
- supermercados;
- hospitales y clínicas;
- universidades / educación superior;
- parques;
- farmacias;
- red Metro operativa L1, L2, L3, L4, L4A, L5 y L6.

Los equipamientos se consultan con OpenStreetMap/Overpass y nunca se mezclan
con los proyectos futuros.

## 2. Futuro / en desarrollo
El segundo mapa contiene:
- líneas Metro futuras/en desarrollo, dibujadas segmentadas;
- construcciones registradas en OSM;
- proyectos SEIA cercanos;
- opcionalmente contratos/obras MOP.

Las líneas Metro conservan colores por línea:
- L6 morado (extensión);
- L7 gris;
- L8 naranja;
- L9 rosado.

## 3. Estados Metro futuros
Datos de referencia incorporados:
- Extensión L6: en construcción; puesta en servicio referencial actualizada a 2028.
- L7: en construcción; 2028.
- L9: fases 2030/2032/2033.
- L8: 2033.

Las fechas son metadata informativa, no geometría OSM.

## 4. Fuente de geometría Metro
La geometría de red se obtiene desde OpenStreetMap/Overpass.
La aplicación prioriza `colour=*` de las relaciones OSM y usa una paleta
fallback por línea.

Las líneas futuras se muestran punteadas/segmentadas para no confundirlas
con infraestructura operativa.

## 5. Advertencia
- Un proyecto SEIA no es una obra garantizada.
- Una geometría `construction` en OSM depende de edición comunitaria.
- Un trazado futuro de Metro puede modificarse.
- El mapa debe conservar fuente, fecha y estado.
