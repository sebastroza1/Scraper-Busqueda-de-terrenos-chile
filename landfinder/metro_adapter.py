from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .urban_value import (
    CURRENT_LINE_ORDER,
    CURRENT_METRO_META,
    FUTURE_LINE_ORDER,
    FUTURE_METRO_META,
    METRO_COLORS,
    analyze_line_in_aoi,
    haversine_m,
    query_current_metro_detailed,
    query_future_metro_detailed,
)


METRO_DIR = DATA_DIR / "metro"
METRO_FILES = {
    "current_lines": METRO_DIR / "metro_lines_current.geojson",
    "current_stations": METRO_DIR / "metro_stations_current.geojson",
    "future_lines": METRO_DIR / "metro_lines_future.geojson",
    "future_stations": METRO_DIR / "metro_stations_future.geojson",
}
METRO_CACHE_VERSION = "osm-overpass-cache-v1"
SANTIAGO_METRO_CENTER = (-33.4489, -70.6693)


def _feature_collection(features: list[dict[str, Any]], dataset: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "dataset": dataset,
            "version": METRO_CACHE_VERSION,
            "source": "OpenStreetMap Overpass",
        },
    }


def _segments_to_geometry(segments: list[list[list[float]]]) -> dict[str, Any] | None:
    clean_segments = [segment for segment in segments if len(segment) >= 2]
    if not clean_segments:
        return None
    coords = [
        [[float(lon), float(lat)] for lat, lon in segment]
        for segment in clean_segments
    ]
    if len(coords) == 1:
        return {"type": "LineString", "coordinates": coords[0]}
    return {"type": "MultiLineString", "coordinates": coords}


def _geometry_to_segments(geometry: dict[str, Any] | None) -> list[list[list[float]]]:
    if not geometry:
        return []
    if geometry.get("type") == "LineString":
        return [[[float(lat), float(lon)] for lon, lat in geometry.get("coordinates", [])]]
    if geometry.get("type") == "MultiLineString":
        return [
            [[float(lat), float(lon)] for lon, lat in segment]
            for segment in geometry.get("coordinates", [])
            if len(segment) >= 2
        ]
    return []


def _lines_to_geojson(lines: dict[str, Any], order: list[str], future: bool) -> dict[str, Any]:
    features = []
    for ref in order:
        line = lines.get(ref) or {}
        geometry = _segments_to_geometry(line.get("segments") or [])
        if not geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "ref": ref,
                    "name": line.get("name") or ref,
                    "color": line.get("color") or METRO_COLORS.get(ref, "#777777"),
                    "future": future,
                },
            }
        )
    return _feature_collection(features, "metro_lines_future" if future else "metro_lines_current")


def _stations_to_geojson(lines: dict[str, Any], future: bool) -> dict[str, Any]:
    stations: dict[str, dict[str, Any]] = {}
    for ref, line in lines.items():
        for station in line.get("stations") or []:
            if station.get("lat") is None or station.get("lon") is None:
                continue
            key = f"{station.get('name','').strip().lower()}:{float(station['lat']):.6f}:{float(station['lon']):.6f}"
            record = stations.setdefault(
                key,
                {
                    "name": station.get("name") or "Estación",
                    "lat": float(station["lat"]),
                    "lon": float(station["lon"]),
                    "refs": [],
                    "tags": station.get("tags") or {},
                },
            )
            if ref not in record["refs"]:
                record["refs"].append(ref)

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [station["lon"], station["lat"]]},
            "properties": {
                "name": station["name"],
                "refs": station["refs"],
                "future": future,
                "tags": station["tags"],
            },
        }
        for station in stations.values()
    ]
    return _feature_collection(features, "metro_stations_future" if future else "metro_stations_current")


def _write_geojson(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_metro_cache(timeout: int = 45) -> None:
    lat, lon = SANTIAGO_METRO_CENTER
    current = query_current_metro_detailed(lat, lon, 1, timeout=timeout)
    future = query_future_metro_detailed(lat, lon, 1, timeout=timeout)
    _write_geojson(METRO_FILES["current_lines"], _lines_to_geojson(current, CURRENT_LINE_ORDER, future=False))
    _write_geojson(METRO_FILES["current_stations"], _stations_to_geojson(current, future=False))
    _write_geojson(METRO_FILES["future_lines"], _lines_to_geojson(future, FUTURE_LINE_ORDER, future=True))
    _write_geojson(METRO_FILES["future_stations"], _stations_to_geojson(future, future=True))


def ensure_metro_cache(timeout: int = 45) -> None:
    if all(path.exists() for path in METRO_FILES.values()):
        return
    refresh_metro_cache(timeout=timeout)


def _read_geojson(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _base_lines(order: list[str], future: bool) -> dict[str, Any]:
    lines = {}
    for ref in order:
        meta = FUTURE_METRO_META[ref] if future else CURRENT_METRO_META[ref]
        lines[ref] = {
            "ref": ref,
            **meta,
            "color": METRO_COLORS.get(ref, "#777777"),
            "segments": [],
            "stations": [],
            "station_sequences": [],
            "source": "local_geojson_cache",
        }
    return lines


def _load_network(kind: str, timeout: int = 45) -> dict[str, Any]:
    ensure_metro_cache(timeout=timeout)
    future = kind == "future"
    order = FUTURE_LINE_ORDER if future else CURRENT_LINE_ORDER
    lines_file = METRO_FILES["future_lines" if future else "current_lines"]
    stations_file = METRO_FILES["future_stations" if future else "current_stations"]
    lines = _base_lines(order, future=future)

    for feature in _read_geojson(lines_file).get("features") or []:
        props = feature.get("properties") or {}
        ref = props.get("ref")
        if ref not in lines:
            continue
        lines[ref]["segments"].extend(_geometry_to_segments(feature.get("geometry")))
        lines[ref]["name"] = props.get("name") or lines[ref].get("name")
        lines[ref]["color"] = props.get("color") or lines[ref].get("color")

    for feature in _read_geojson(stations_file).get("features") or []:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        station = {
            "name": props.get("name") or "Estación",
            "lat": float(coords[1]),
            "lon": float(coords[0]),
            "tags": props.get("tags") or {},
        }
        for ref in props.get("refs") or []:
            if ref in lines:
                lines[ref]["stations"].append(dict(station))

    return lines


def analyze_metro_network_for_area(
    lines: dict[str, Any],
    lat: float,
    lon: float,
    radius_m: float,
) -> dict[str, Any]:
    analyzed = deepcopy(lines)
    for line in analyzed.values():
        analysis = analyze_line_in_aoi(line.get("segments") or [], lat, lon, radius_m)
        distance_m = analysis.get("distance_m")
        line.update(analysis)
        line["distance_to_area_m"] = max(0.0, float(distance_m) - radius_m) if distance_m is not None else None
        line["stations_in_area"] = [
            station
            for station in line.get("stations") or []
            if haversine_m(lat, lon, station["lat"], station["lon"]) <= radius_m
        ]
        line["geometry_available"] = bool(line.get("segments"))
    return analyzed


def metro_current_for_area(lat: float, lon: float, radius_m: float, timeout: int = 45) -> dict[str, Any]:
    return analyze_metro_network_for_area(_load_network("current", timeout=timeout), lat, lon, radius_m)


def metro_future_for_area(lat: float, lon: float, radius_m: float, timeout: int = 45) -> dict[str, Any]:
    return analyze_metro_network_for_area(_load_network("future", timeout=timeout), lat, lon, radius_m)


def metro_area_summary(
    current_lines: dict[str, Any],
    future_lines: dict[str, Any],
    lat: float,
    lon: float,
    radius_m: float,
    nearby_threshold_m: float = 2000,
) -> dict[str, Any]:
    stations = {}
    stations_inside = {}
    for line in current_lines.values():
        for station in line.get("stations") or []:
            key = f"{station.get('name','').strip().lower()}:{station['lat']:.6f}:{station['lon']:.6f}"
            distance = haversine_m(lat, lon, station["lat"], station["lon"])
            stations[key] = {**station, "distance_m": round(distance, 1)}
        for station in line.get("stations_in_area") or []:
            key = f"{station.get('name','').strip().lower()}:{station['lat']:.6f}:{station['lon']:.6f}"
            stations_inside[key] = station

    nearest_station = min(stations.values(), key=lambda station: station["distance_m"]) if stations else None
    current_nearby = [
        {"ref": line["ref"], "distance_to_area_m": line.get("distance_to_area_m")}
        for line in current_lines.values()
        if line.get("distance_to_area_m") is not None and line["distance_to_area_m"] <= nearby_threshold_m
    ]
    future_nearby = [
        {"ref": line["ref"], "distance_to_area_m": line.get("distance_to_area_m")}
        for line in future_lines.values()
        if line.get("distance_to_area_m") is not None and line["distance_to_area_m"] <= nearby_threshold_m
    ]

    return {
        "current_intersecting": [line["ref"] for line in current_lines.values() if line.get("passes_area")],
        "current_nearby": sorted(current_nearby, key=lambda item: item["distance_to_area_m"]),
        "future_nearby": sorted(future_nearby, key=lambda item: item["distance_to_area_m"]),
        "nearest_station": nearest_station,
        "stations_inside_count": len(stations_inside),
        "radius_m": radius_m,
    }
