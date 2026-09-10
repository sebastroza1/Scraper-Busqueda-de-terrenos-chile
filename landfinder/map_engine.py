from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping, Point
from shapely.ops import transform as shp_transform

from .config import DEFAULT_TIMEOUT, USER_AGENT, source_config


def bbox_from_point(lat: float, lon: float, radius_m: float) -> Tuple[float, float, float, float]:
    lat_delta = radius_m / 111_320.0
    lon_scale = max(math.cos(math.radians(lat)), 0.15)
    lon_delta = radius_m / (111_320.0 * lon_scale)
    return lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta


def _get(url, params=None, timeout=DEFAULT_TIMEOUT):
    effective_timeout = min(timeout, source_config("mop")["timeout"]) if "rest-sit.mop.gob.cl" in url else timeout
    last_error = None
    attempts = 1
    for attempt in range(attempts):
        try:
            return requests.get(
                url,
                params=params,
                timeout=effective_timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.8)
                continue
            raise
    raise last_error


def _local_transformers(lat: float, lon: float):
    # Proyección Azimuthal Equidistant centrada en el terreno:
    # permite medir/recortar en metros sin depender de la zona UTM.
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs"
    )
    wgs84 = CRS.from_epsg(4326)
    to_local = Transformer.from_crs(wgs84, local, always_xy=True).transform
    to_wgs84 = Transformer.from_crs(local, wgs84, always_xy=True).transform
    return to_local, to_wgs84


def build_aoi_circle(lat: float, lon: float, radius_m: float):
    to_local, to_wgs84 = _local_transformers(lat, lon)
    center_local = shp_transform(to_local, Point(lon, lat))
    circle_local = center_local.buffer(radius_m, quad_segs=48)
    circle_wgs84 = shp_transform(to_wgs84, circle_local)
    return circle_local, circle_wgs84, to_local, to_wgs84


def _service_layer_urls(source: Dict[str, Any]) -> List[str]:
    url = source["url"].rstrip("/")

    if source["kind"] == "arcgis_layer":
        return [url]

    configured = source.get("map_layers")
    if configured:
        return [f"{url}/{layer_id}" for layer_id in configured]

    r = _get(url, {"f": "json"})
    r.raise_for_status()
    meta = r.json()
    if meta.get("error"):
        raise RuntimeError(meta["error"])

    layers = meta.get("layers") or []
    if not layers:
        return []
    return [f"{url}/{layers[0]['id']}"]


def _esri_geometry_to_geojson(g: Dict[str, Any]):
    if not g:
        return None
    if "x" in g and "y" in g:
        return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if "points" in g:
        return {"type": "MultiPoint", "coordinates": g["points"]}
    if "paths" in g:
        paths = g["paths"]
        return {"type": "LineString" if len(paths) == 1 else "MultiLineString",
                "coordinates": paths[0] if len(paths) == 1 else paths}
    if "rings" in g:
        # Conversión simple suficiente para visualización/clip preliminar.
        return {"type": "Polygon", "coordinates": g["rings"]}
    return None


def _esri_features_to_geojson(payload: Dict[str, Any]) -> Dict[str, Any]:
    features = []
    for feature in payload.get("features") or []:
        geometry = _esri_geometry_to_geojson(feature.get("geometry") or {})
        if geometry is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": feature.get("attributes") or {},
        })
    return {"type": "FeatureCollection", "features": features}


def _arcgis_query_json(layer_url, bbox, timeout, limit):
    xmin, ymin, xmax, ymax = bbox
    geometry = (
        '{"xmin":%.10f,"ymin":%.10f,"xmax":%.10f,"ymax":%.10f,'
        '"spatialReference":{"wkid":4326}}'
        % (xmin, ymin, xmax, ymax)
    )
    params = {
        "where": "1=1",
        "geometry": geometry,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": str(limit),
    }

    r = _get(layer_url + "/query", params, timeout)
    if r.status_code == 400:
        params.pop("resultRecordCount", None)
        r = _get(layer_url + "/query", params, timeout)

    r.raise_for_status()
    payload = r.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload


def _clean_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return str(value)
    text = str(value)
    return text if len(text) <= 250 else text[:247] + "..."


def _best_label(props: Dict[str, Any]) -> str:
    preferred = [
        "NOMBRE", "Nombre", "nombre", "NAME", "Name", "name",
        "NOM", "nom", "DESCRIPCION", "DESCRIPCIÓN", "Descripcion",
        "TIPO", "Tipo", "tipo", "PROYECTO", "Proyecto", "proyecto",
    ]
    for key in preferred:
        if props.get(key) not in (None, ""):
            return _clean_value(props[key])

    # Buscar heurísticamente algún campo nombre/descripcion.
    for key, value in props.items():
        lk = str(key).lower()
        if any(token in lk for token in ("nombre", "name", "nom_", "descripcion", "proyecto")):
            if value not in (None, ""):
                return _clean_value(value)

    # Último recurso: primer valor no vacío.
    for value in props.values():
        if value not in (None, ""):
            return _clean_value(value)
    return "Elemento sin nombre"


def _popup_html(source_name: str, props: Dict[str, Any], distance_m: float) -> str:
    rows = [
        f"<b>{source_name}</b>",
        f"<b>Distancia al punto:</b> {distance_m:,.0f} m".replace(",", "."),
        "<hr>",
    ]
    shown = 0
    for key, value in props.items():
        if value in (None, ""):
            continue
        value = _clean_value(value)
        rows.append(f"<b>{key}:</b> {value}")
        shown += 1
        if shown >= 12:
            break
    return "<br>".join(rows)


def filter_clip_geojson_to_circle(
    geojson: Dict[str, Any],
    source_name: str,
    lat: float,
    lon: float,
    radius_m: float,
):
    circle_local, _, to_local, to_wgs84 = build_aoi_circle(lat, lon, radius_m)
    center_local = shp_transform(to_local, Point(lon, lat))

    kept = []
    records = []

    for idx, feature in enumerate(geojson.get("features") or []):
        gj_geom = feature.get("geometry")
        if not gj_geom:
            continue

        try:
            geom_wgs = shape(gj_geom)
            if geom_wgs.is_empty:
                continue
            geom_local = shp_transform(to_local, geom_wgs)
        except Exception:
            continue

        if not geom_local.intersects(circle_local):
            continue

        # Distancia mínima del objeto al punto.
        distance_m = float(geom_local.distance(center_local))

        # Mostrar SOLAMENTE la parte que cae dentro del AOI.
        try:
            clipped_local = geom_local.intersection(circle_local)
            if clipped_local.is_empty:
                continue
            clipped_wgs = shp_transform(to_wgs84, clipped_local)
            display_geometry = mapping(clipped_wgs)
        except Exception:
            display_geometry = gj_geom

        props = dict(feature.get("properties") or {})
        props["__source"] = source_name
        props["__distance_m"] = round(distance_m, 1)
        props["__label"] = _best_label(props)
        props["__popup_html"] = _popup_html(source_name, props, distance_m)

        kept.append({
            "type": "Feature",
            "geometry": display_geometry,
            "properties": props,
        })

        # Registro puntual para tabla.
        record = {
            "Fuente": source_name,
            "Elemento": props["__label"],
            "Distancia_m": round(distance_m, 1),
        }
        # Añadir algunos atributos útiles sin llenar demasiado la tabla.
        useful = 0
        for key, value in props.items():
            if key.startswith("__") or value in (None, ""):
                continue
            record[str(key)] = _clean_value(value)
            useful += 1
            if useful >= 6:
                break
        records.append(record)

    records.sort(key=lambda r: r["Distancia_m"])
    return {"type": "FeatureCollection", "features": kept}, records


def query_arcgis_aoi(source, lat, lon, radius_m, timeout=DEFAULT_TIMEOUT, limit=500):
    bbox = bbox_from_point(lat, lon, radius_m)
    layers = []

    for layer_url in _service_layer_urls(source):
        payload = _arcgis_query_json(layer_url, bbox, timeout, limit)
        raw_geojson = _esri_features_to_geojson(payload)
        raw_count = len(payload.get("features") or [])
        normalized_count = len(raw_geojson.get("features") or [])

        clipped, records = filter_clip_geojson_to_circle(
            raw_geojson,
            source.get("map_label", source["name"]),
            lat,
            lon,
            radius_m,
        )

        layers.append({
            "layer_url": layer_url,
            "geojson": clipped,
            "count": len(clipped.get("features") or []),
            "records": records,
            "pipeline": {
                "raw": raw_count,
                "normalized": normalized_count,
                "matching": len(clipped.get("features") or []),
                "stored": len(records),
            },
        })

    return layers


def _geoserver_wfs_url(wms_url: str) -> str:
    parsed = urlparse(wms_url)
    path = parsed.path
    if path.lower().endswith("/wms"):
        path = path[:-4] + "/wfs"
    return urlunparse(parsed._replace(path=path, query=""))


def _discover_wfs_typename(wfs_url: str, preferred_layer: str | None, timeout: int):
    r = _get(
        wfs_url,
        {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"},
        timeout,
    )
    r.raise_for_status()
    text = r.text

    import xml.etree.ElementTree as ET
    root = ET.fromstring(text)
    names = []
    for elem in root.iter():
        if elem.tag.split("}")[-1] == "FeatureType":
            for child in elem.iter():
                if child.tag.split("}")[-1] == "Name" and child.text:
                    names.append(child.text.strip())
                    break

    if not names:
        raise RuntimeError("WFS disponible pero sin FeatureType detectables.")

    if preferred_layer:
        for n in names:
            if n.split(":")[-1].lower() == preferred_layer.lower():
                return n

    return names[0]


def query_wfs_aoi(source, lat, lon, radius_m, timeout=DEFAULT_TIMEOUT, limit=500):
    bbox = bbox_from_point(lat, lon, radius_m)
    xmin, ymin, xmax, ymax = bbox

    wfs_url = source["url"]
    typename = source.get("wfs_typename")
    if not typename:
        preferred = None
        if source.get("wms_layers"):
            preferred = source["wms_layers"][0]
        typename = _discover_wfs_typename(wfs_url, preferred, timeout)

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": typename,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{xmin},{ymin},{xmax},{ymax},EPSG:4326",
        "count": str(limit),
    }
    r = _get(wfs_url, params, timeout)
    r.raise_for_status()
    raw = r.json()
    raw_count = len(raw.get("features") or []) if isinstance(raw, dict) else 0

    clipped, records = filter_clip_geojson_to_circle(
        raw,
        source.get("map_label", source["name"]),
        lat,
        lon,
        radius_m,
    )
    return [{
        "layer_url": wfs_url,
        "geojson": clipped,
        "count": len(clipped.get("features") or []),
        "records": records,
        "pipeline": {
            "raw": raw_count,
            "normalized": raw_count,
            "matching": len(clipped.get("features") or []),
            "stored": len(records),
        },
    }]


def log_pipeline(source: Dict[str, Any], result: Dict[str, Any]) -> None:
    rendered = sum(
        len((layer.get("geojson") or {}).get("features") or [])
        for layer in result.get("layers") or []
        if isinstance(layer, dict)
    )
    raw = sum((layer.get("pipeline") or {}).get("raw", 0) for layer in result.get("layers") or [] if isinstance(layer, dict))
    normalized = sum((layer.get("pipeline") or {}).get("normalized", 0) for layer in result.get("layers") or [] if isinstance(layer, dict))
    matching = sum((layer.get("pipeline") or {}).get("matching", 0) for layer in result.get("layers") or [] if isinstance(layer, dict))
    stored = len(result.get("records") or [])
    print(
        f"[SOURCE: {source.get('id')}] status={result.get('status')} "
        f"raw={raw} normalized={normalized} matching={matching} stored={stored} rendered={rendered}"
    )


def try_wms_as_wfs(source, lat, lon, radius_m, timeout, limit):
    # GeoServer normalmente publica WMS y WFS para la misma workspace.
    # Esto permite convertir capas antes "solo visuales" en datos vectoriales.
    wfs_source = dict(source)
    wfs_source["url"] = _geoserver_wfs_url(source["url"])
    wfs_source["kind"] = "wfs"
    wfs_source["wfs_typename"] = None
    return query_wfs_aoi(wfs_source, lat, lon, radius_m, timeout, limit)


def load_map_source(
    source: Dict[str, Any],
    lat: float,
    lon: float,
    radius_m: float,
    timeout: int,
    limit: int = 500,
) -> Dict[str, Any]:
    kind = source["kind"]

    if kind in ("arcgis_service", "arcgis_layer"):
        layers = query_arcgis_aoi(source, lat, lon, radius_m, timeout, limit)
        records = [r for layer in layers for r in layer.get("records", [])]
        result = {
            "status": "OK" if records else "OK_SIN_COINCIDENCIAS",
            "type": "geojson_layers",
            "layers": layers,
            "count": sum(x["count"] for x in layers),
            "records": records,
            "error": None,
        }
        log_pipeline(source, result)
        return result

    if kind == "wfs":
        layers = query_wfs_aoi(source, lat, lon, radius_m, timeout, limit)
        records = [r for layer in layers for r in layer.get("records", [])]
        result = {
            "status": "OK" if records else "OK_SIN_COINCIDENCIAS",
            "type": "geojson_layers",
            "layers": layers,
            "count": sum(x["count"] for x in layers),
            "records": records,
            "error": None,
        }
        log_pipeline(source, result)
        return result

    if kind == "wms":
        # Preferimos WFS para tener recorte, conteo y atributos.
        try:
            layers = try_wms_as_wfs(source, lat, lon, radius_m, timeout, limit)
            records = [r for layer in layers for r in layer.get("records", [])]
            result = {
                "status": "OK" if records else "OK_SIN_COINCIDENCIAS",
                "type": "geojson_layers",
                "layers": layers,
                "count": sum(x["count"] for x in layers),
                "records": records,
                "error": None,
                "note": "WMS convertido automáticamente a WFS para análisis vectorial.",
            }
            log_pipeline(source, result)
            return result
        except Exception as exc:
            # Si no hay WFS, se mantiene como referencia visual y NO se reporta 0.
            result = {
                "status": "VISUAL_ONLY",
                "type": "wms",
                "layers": source.get("wms_layers") or [],
                "count": None,
                "records": [],
                "error": None,
                "note": f"Sin WFS vectorial disponible; capa WMS solo visual. {exc}",
            }
            log_pipeline(source, result)
            return result

    return {
        "status": "NOT_SUPPORTED",
        "type": None,
        "layers": [],
        "count": None,
        "records": [],
        "error": f"Tipo {kind} no soportado todavía en el mapa.",
    }
