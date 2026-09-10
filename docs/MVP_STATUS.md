# Landfinder Chile - Estado técnico del MVP

Fecha de revisión: 2026-09-09

## 1. Qué encontré al iniciar

- Repositorio Python/Streamlit con `app.py` como entrada principal.
- Módulos separados para registro de fuentes, probes, almacenamiento SQLite, consultas GIS y consultas OSM/Metro.
- `config/sources_registry.json` con 42 fuentes registradas.
- README previo ya describía intención map-first, pero la UI mantenía tabs tipo dashboard y un segundo mapa para comparación.
- Existían puntajes preliminares numéricos, aunque no hay motor formal de scoring territorial.

## 2. Problemas detectados

- Comparar usaba otro mapa, contra el principio de mapa único.
- El panel izquierdo mostraba capas con multiselects y grupos simples, no como acordeones completos.
- Varias capas estaban activadas por defecto.
- El buscador global solo resolvía coordenadas de forma parcial.
- El flujo de creación de área dependía demasiado del sidebar y no del mapa como espacio de trabajo.
- El panel derecho mostraba scoring numérico como si fuera evaluación madura.
- Los estados por fuente no estaban suficientemente visibles para el usuario final.
- Terrenos/oferta aparecían conceptualmente, pero no hay API oficial configurada.

## 3. Qué modifiqué

- Reorganicé `app.py` como una pantalla map-first con header, panel izquierdo, mapa central y panel derecho contextual.
- Reemplacé tabs de producto por modos sobre el mismo mapa.
- Eliminé el mapa separado de comparación.
- Implementé buscador para direcciones en Chile vía Nominatim/OSM, con fallback a comunas RM principales y coordenadas `lat,lng`.
- Dejé creación de áreas por punto + radio, usando el centro del mapa o clic como punto base.
- Agregué selección, ocultamiento y eliminación de áreas.
- Cambié capas a acordeones con buscador de capa.
- Separé capas de territorio y riesgos, aunque algunas fuentes puedan reutilizarse internamente.
- Agregué filtros configurables y botón explícito `Aplicar filtros`.
- Conservo aislamiento de errores por fuente con estados visibles.
- Sustituí scoring numérico por indicadores preliminares cuantitativos.
- Agregué clustering para equipamientos OSM.
- Agregué leyenda horizontal compacta con solo capas aplicadas.
- Actualicé README y documenté fuentes.

## 4. Archivos principales modificados

- `app.py`
- `README.md`
- `docs/MVP_STATUS.md`
- `docs/DATA_SOURCES.md`

## 5. Funcionalidades terminadas

- Mapa único principal.
- Layout header + panel izquierdo + mapa + panel derecho.
- Buscador global básico.
- Múltiples áreas simultáneas.
- Área activa.
- Ocultar/mostrar área.
- Eliminar área.
- Panel izquierdo colapsable.
- Acordeones de capas.
- Buscador de capas.
- Filtros con aplicación explícita.
- Capas OSM construidas sobre adaptadores existentes.
- Metro actual/futuro usando geometría real cuando Overpass responde.
- Desarrollo futuro vía SEIA/MOP cuando las fuentes responden.
- Territorio y riesgos desde fuentes registradas.
- Estados de fuente por área.
- Comparación básica de áreas en el panel derecho sobre el mismo mapa.
- Reporte JSON de evidencia por área.
- Perfil demo/progresivo.
- Admin/API para health checks.

## 6. Funcionalidades parciales

- Búsqueda de direcciones: funcional vía Nominatim/OSM cuando hay red, pero sin SLA propio; fallback local para comunas RM y coordenadas.
- Dibujo de polígonos: pendiente; el MVP funcional usa punto + radio.
- Click sobre elementos: funcional para marcadores OSM/metro cercanos; polígonos GIS aún muestran tooltip en mapa.
- Responsive: básico mediante Streamlit columns; no reemplaza un frontend dedicado.
- Filtros de precio/superficie: UI preparada, sin fuente inmobiliaria conectada.
- Reportes: JSON funcional; PDF pendiente.
- Alertas: estado próximo, sin scheduler propio del producto.

## 7. APIs funcionando

El registro carga correctamente y valida 42 fuentes. Los adaptadores disponibles son:

- ArcGIS REST;
- WFS;
- WMS con intento WFS cuando aplica;
- CKAN;
- ChileCompra OCDS;
- web/download probes;
- Overpass/OSM para equipamientos y metro.

## 8. APIs con errores

En QA local del 2026-09-09, Overpass falló por conexión desde el sandbox inicial:

- equipamientos OSM;
- Metro actual;
- Metro futuro.

La app no se cayó y reportó errores por fuente. Esta falla puede depender de red, DNS, rate limit o sandbox local.

La prueba de geocoding con red permitida respondió correctamente para `Av. Irarrazaval 2401, Nunoa, Chile`.

## 9. Datos que todavía son simulados

- Perfil demo y workspace local.
- Navegación de Proyectos/Alertas como estados progresivos.
- Gazetteer local de comunas RM con centros aproximados como fallback.
- Filtros de mercado/precio/superficie sin fuente inmobiliaria activa.

No se simulan estaciones, líneas, proyectos SEIA/MOP ni resultados territoriales.

## 10. Deuda técnica

- `app.py` concentra demasiada lógica de UI y debería dividirse en componentes.
- Falta suite de tests para funciones de estado, filtros y comparación.
- Falta cache persistente por fuente/AOI.
- Falta backend FastAPI para desacoplar UI y proveedores externos.
- Falta geocoder formal y política de uso.
- Falta persistencia de áreas/proyectos.
- Falta manejo visual más profundo para click en polígonos GIS.
- Falta control de permisos/licencias antes de producción comercial.

## 11. Próximos 10 pasos recomendados

1. Extraer componentes Streamlit desde `app.py`.
2. Agregar tests unitarios para `resolve_search`, `bundle_counts`, filtros y estados.
3. Implementar cache por `(source_id, lat, lon, radius, filters)`.
4. Crear backend FastAPI con endpoints por fuente.
5. Añadir PostGIS para áreas, resultados y geometrías.
6. Integrar geocoding oficial o proveedor validado.
7. Implementar dibujo/edición de polígonos.
8. Validar licencias P0/P1 y documentar permisos comerciales.
9. Conectar fuentes inmobiliarias oficiales o acuerdos privados.
10. Diseñar motor de indicadores con reglas auditables antes de volver a mostrar scoring.
