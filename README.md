# Landfinder Chile

Plataforma MVP de inteligencia territorial para buscar ubicaciones, crear áreas de análisis, activar capas, aplicar filtros y comparar zonas sobre un único mapa principal.

## Estado actual del MVP

El MVP actual está reorganizado como una experiencia map-first:

- un solo mapa central de Santiago;
- buscador global para direcciones en Chile vía Nominatim/OSM, comunas RM conocidas y coordenadas `lat,lng`;
- creación de múltiples áreas por punto + radio;
- áreas visibles simultáneamente, con selección, ocultamiento y eliminación;
- panel izquierdo colapsable con acordeones de capas y filtros;
- botón explícito `Aplicar filtros` para evitar consultas pesadas por cada checkbox;
- panel derecho contextual para resumen, comparación, reportes, perfil y estados futuros;
- clustering para equipamientos OSM cuando hay muchos puntos;
- estados por fuente: éxito, vacío, solo visual y error;
- leyenda compacta que muestra solo capas aplicadas;
- trazabilidad básica por fuente en resultados y reportes JSON.

No se inventan datasets, estaciones, trazados, proyectos ni puntajes de compra. Cuando una API falla o no está configurada, la UI lo informa sin bloquear el resto.

## Arquitectura

```text
app.py
  ├─ UI Streamlit map-first
  ├─ estado de sesión: áreas, capas, filtros, modo, resultados
  ├─ consultas por área y por fuente con try/except aislado
  └─ mapa Folium único

landfinder/
  ├─ registry.py      registro y validación de fuentes
  ├─ map_engine.py    consultas ArcGIS/WFS/WMS por AOI
  ├─ urban_value.py   OSM, Metro actual/futuro y utilidades geográficas
  ├─ probes.py        health checks de APIs
  ├─ storage.py       historial SQLite de health checks
  └─ runner.py        ejecución batch de probes

config/
  ├─ sources_registry.json
  └─ business_model.json
```

## Frontend

El frontend está implementado en Streamlit con Folium:

- header compacto con marca, buscador y navegación progresiva;
- mapa principal persistente como espacio de trabajo;
- panel izquierdo para capas, filtros y áreas;
- panel derecho contextual;
- diseño responsive básico mediante columnas Streamlit;
- selector de mapa base compatible con proveedores abiertos disponibles.

Limitación actual: Streamlit vuelve a renderizar el componente Folium entre interacciones. La app mantiene centro, zoom, áreas y resultados en `st.session_state`, pero una versión productiva debería migrar el mapa a frontend web dedicado si se requiere persistencia total de viewport sin remount.

## Backend

No hay backend HTTP separado todavía. El MVP local consulta fuentes desde Streamlit:

- `map_engine.py` consulta ArcGIS REST, WFS y WMS;
- `urban_value.py` consulta Overpass/OSM para equipamientos y metro;
- `probes.py` realiza canaries de salud;
- `storage.py` guarda historial técnico en SQLite local.

La arquitectura ya separa fuentes por proveedor para que una caída no bloquee el resto.

## Fuentes de datos

El registro principal vive en `config/sources_registry.json`. Cada fuente mantiene:

- `id`;
- proveedor;
- nombre;
- categoría;
- tipo técnico;
- estado de auditoría;
- política de runtime;
- gate legal;
- cobertura;
- notas;
- configuración de mapa cuando aplica.

Resumen de fuentes principales:

| Fuente | Finalidad | Autenticación | Endpoint/base | Estado |
|---|---|---:|---|---|
| OpenStreetMap / Overpass | Equipamientos, construcciones, metro cuando existe geometría | No | `https://overpass-api.de/api/interpreter` | funcional desde red abierta; falló en QA local por conexión |
| OpenStreetMap / Nominatim | Búsqueda de direcciones | No | `https://nominatim.openstreetmap.org/search` | funcional desde red abierta; requiere respetar política de uso |
| MINVU Límites Urbanos | Planificación territorial | No | ArcGIS FeatureServer | parcial, gate legal pendiente |
| MINVU PRMS uso suelo | Planificación RM | No | ArcGIS FeatureServer layer | parcial, gate legal pendiente |
| MINVU Áreas de Riesgo | Riesgos IPT | No | ArcGIS FeatureServer | parcial, gate legal pendiente |
| MMA Humedales | Ambiental/riesgos | No | ArcGIS FeatureServer | parcial, gate legal pendiente |
| MMA Áreas Protegidas | Ambiental/riesgos | No | ArcGIS FeatureServer | parcial, gate legal pendiente |
| SEA Proyectos SEIA | Proyectos ambientales | No | ArcGIS MapServer | parcial, gate legal pendiente |
| MOP Obras | Obras públicas | No | ArcGIS MapServer | parcial, gate legal pendiente |
| DGA Derechos / Prohibiciones | Contexto hídrico | No | ArcGIS MOP/SNIA | parcial, gate legal pendiente |
| MINSAL Salud 2026 | Servicios de salud | No | WFS Geoportal | parcial, revisar metadata |
| MercadoLibre / Portal Inmobiliario | Terrenos/oferta | No configurada | pendiente | pendiente |

Detalle completo: `docs/DATA_SOURCES.md`.

## Cómo ejecutar

### Windows fácil

```powershell
INSTALAR_Y_EJECUTAR.bat
```

### Manual

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Si el puerto `8501` está ocupado:

```powershell
python -m streamlit run app.py --server.port 8502
```

## Variables de entorno

Actualmente el MVP no requiere credenciales obligatorias. `.env.example` existe como base para futuras APIs:

```text
LANDFINDER_ENV=development
DEFAULT_TIMEOUT=12
```

No agregues tokens, cookies ni credenciales al repositorio.

## Limitaciones actuales

- Búsqueda de direcciones usa Nominatim/OSM con fallback local; para producción conviene contratar o alojar un geocoder con SLA y política de uso propia.
- Dibujo de polígonos está preparado conceptualmente, pero el flujo funcional actual es punto + radio.
- Streamlit/Folium no permite conservar el mapa montado con el mismo nivel de control que un frontend React/MapLibre.
- Overpass puede fallar por red, rate limit o restricciones del entorno.
- Metro futuro depende de geometría disponible en OSM; si no existe, no se inventa.
- Reportes PDF, alertas reales y persistencia cloud quedan fuera de este hito.
- Conectores inmobiliarios están declarados como candidatos, no como dependencia operativa.

## Próximos pasos

1. Crear backend FastAPI para desacoplar UI y fuentes.
2. Agregar cache por AOI/fuente y expiración configurable.
3. Migrar mapa a MapLibre/Leaflet web dedicado para viewport persistente.
4. Incorporar geocoder formal con política de uso validada.
5. Implementar polígonos dibujados y edición de geometría.
6. Añadir tests unitarios para filtros, estados de fuente y comparación.
7. Validar licencias de fuentes P0/P1 antes de uso comercial.
8. Diseñar persistencia de áreas/proyectos por usuario.
9. Generar reportes PDF con evidencia y disclaimers.
10. Definir motor de scoring solo cuando existan reglas auditables.
