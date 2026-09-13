from __future__ import annotations

import json
import math
from typing import Any

from .persistent_cache import CACHE_SCHEMA_VERSION


def area_bounds_context(area: dict[str, Any]) -> dict[str, float | int | str | None]:
    lat = float(area["lat"])
    lon = float(area["lon"])
    radius_m = int(area.get("radius_m") or 0)
    lat_delta = radius_m / 111_320.0
    lon_scale = max(math.cos(math.radians(lat)), 0.15)
    lon_delta = radius_m / (111_320.0 * lon_scale)
    return {
        "area_id": area.get("id"),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "radius_m": radius_m,
        "south": round(lat - lat_delta, 6),
        "west": round(lon - lon_delta, 6),
        "north": round(lat + lat_delta, 6),
        "east": round(lon + lon_delta, 6),
    }


def source_cache_key(area: dict[str, Any], source_id: str, params: Any) -> str:
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "source": source_id,
        "spatial": area_bounds_context(area),
        "params": params,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def with_area_context(
    state: dict[str, Any],
    area_id: str,
    source_id: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    enriched = dict(state)
    enriched["area_id"] = area_id
    enriched["source_id"] = source_id
    if request_id is not None:
        enriched["request_id"] = request_id
    return enriched


def make_area_bundle(area: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    return {
        "area_id": area.get("id"),
        "request_id": request_id,
    }


def store_area_bundle(
    area_results: dict[str, dict[str, Any]],
    target_area_id: str,
    bundle: dict[str, Any],
) -> None:
    result_area_id = bundle.get("area_id")
    if result_area_id != target_area_id:
        raise ValueError(f"Area result mismatch: target={target_area_id} result={result_area_id}")
    area_results[target_area_id] = bundle


def layer_snapshot_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    def normalized(snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "built": tuple(snapshot.get("built") or []),
            "metro_current": bool(snapshot.get("metro_current")),
            "metro_future": bool(snapshot.get("metro_future")),
            "road_network": bool(snapshot.get("road_network")),
            "osm_construction": bool(snapshot.get("osm_construction")),
            "seia": bool(snapshot.get("seia")),
            "mop": bool(snapshot.get("mop")),
            "territory": tuple(snapshot.get("territory") or []),
            "risks": tuple(snapshot.get("risks") or []),
        }

    return normalized(before) != normalized(after)


def layer_snapshot_has_active_layers(snapshot: dict[str, Any]) -> bool:
    return any(
        (
            bool(snapshot.get("built")),
            bool(snapshot.get("metro_current")),
            bool(snapshot.get("metro_future")),
            bool(snapshot.get("road_network")),
            bool(snapshot.get("osm_construction")),
            bool(snapshot.get("seia")),
            bool(snapshot.get("mop")),
            bool(snapshot.get("territory")),
            bool(snapshot.get("risks")),
        )
    )
