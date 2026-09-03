# ADR: Proveedor De Mapa

Fecha: 2026-08-31

## Estado

Aceptada para MVP GIS local.

## Decision

La app Flutter Desktop usa `flutter_map` con tiles raster publicos de
OpenStreetMap como mapa base inicial.

Las capas territoriales oficiales no se sirven como tiles permanentes en el
cliente. Se consultan bajo demanda desde el backend local contra IDE MINVU
ArcGIS REST y se dibujan sobre el mapa solo cuando el terreno seleccionado o el
viewport lo requiera.

## Implementacion MVP

- Paquetes Flutter: `flutter_map`, `latlong2`, `url_launcher`.
- Mapa base: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.
- Atribucion visible en el mapa: `(c) OpenStreetMap contributors`.
- User agent de tiles: `cl.landfinder.desktop`.
- Marcadores: propiedades con latitud/longitud WGS84.
- Poligonos: geometria predial almacenada y geometria retornada por MINVU en
  `outSR=4326`.
- Capas UI: Terrenos, Limites urbanos, Areas de riesgo.

## Condiciones De Uso

OpenStreetMap se usa como mapa base liviano de desarrollo. La app no debe hacer
bulk download, prefetch masivo, cache offline agresivo ni reemplazar un servicio
de tiles comercial para uso intensivo. La aplicacion debe honrar cabeceras de
cache razonables, mantener atribucion visible y no ocultar el origen del mapa.

Si el volumen de uso crece, se debe cambiar a un proveedor de tiles contratado o
a infraestructura propia compatible con la licencia.

## Consecuencias

- El MVP obtiene un mapa real en Windows sin SDK nativo adicional.
- La logica GIS sigue residiendo en el backend: CRS, cache, evidencia y consultas
  ArcGIS no se mezclan con widgets.
- Las capas oficiales no se cargan permanentemente; se activan por seleccion y
  quedan preparadas para carga por viewport.
- El mapa base no es una fuente normativa. Las conclusiones territoriales se
  sustentan solo en evidencia de conectores oficiales como IDE MINVU.

## Referencias

- OpenStreetMap Tile Usage Policy:
  https://operations.osmfoundation.org/policies/tiles/
- `flutter_map` package:
  https://pub.dev/packages/flutter_map
- `flutter_map` `TileLayer` API:
  https://pub.dev/documentation/flutter_map/latest/flutter_map/TileLayer-class.html
