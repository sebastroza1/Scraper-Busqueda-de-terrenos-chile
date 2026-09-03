# Plan De Implementacion

## Fase 0 - Auditoria y base

Estado: iniciada.

- Inspeccionar repositorio.
- Crear `docs/SOURCE_AUDIT.md`.
- Definir arquitectura y arbol objetivo.
- Definir `PropertyCandidate`.
- Definir `SourceConnector`.
- Definir esquema SQLite.
- Definir pipeline y reglas YAML sin valores inventados.
- Definir API local Flutter <-> Python.
- Definir mockups textuales y riesgos.

## Fase 1 - MVP

Objetivo: producto local usable con pocas fuentes, mucha trazabilidad y cero
simulacion falsa.

Estado: implementada como vertical local inicial.

Fuentes activas del MVP:

- Mercado Publico API, con ticket oficial.
- MercadoLibre / PortalInmobiliario por API oficial de inmuebles, con OAuth.

Entregables:

- FastAPI local con token. Estado: listo.
- Busqueda con jobs y progreso. Estado: listo.
- Persistencia SQLite. Estado: listo.
- Deduplicacion inicial por URL, external_id, comuna, coordenadas, superficie,
  precio y titulo normalizado.
- Procesamiento de imagenes permitido. Estado: listo.
- Export Excel multipestana. Estado: listo.
- UI Flutter: dashboard, busqueda, resultados, mapa basico y detalle. Estado:
  listo como app Windows debug.

Postergado por decision explicita:

- nuevas fuentes inmobiliarias o masivas;
- scraping HTML de portales;
- integraciones GIS automaticas;
- reglas DS49/DS19 automaticas con valores no verificados.

## Fase 2 - Inteligencia territorial

- IDE MINVU, IDE Chile, DGA/MOP, MMA humedales y capas CONAF/Minagri.
- Intersecciones geoespaciales y superficie neta desarrollable.
- Geometria predial cuando exista poligono.
- DEM, pendientes y rangos configurables.

## Fase 3 - Motor habitacional

- Reglas DS49 y DS19 por llamado vigente.
- Accesibilidad con red peatonal cuando exista.
- Scoring 0-100 sin permitir que el score anule reglas criticas.
- Cabida preliminar con advertencia obligatoria.

## Fase 4 - Remates y fuentes especiales

- TGR, BancoEstado, SUPERIR, SERVIU regionales, EFE, CODELCO, CAPREDENA,
  DIPRECA y FF.AA. como `WatchConnector` o conectores especificos solo si la
  auditoria lo permite.

## Fase 5 - Hardening

- Empaquetado PyInstaller.
- Instalador.
- Recovery de jobs.
- Cache avanzado.
- Tests de integracion.
- Dashboard de source health.
