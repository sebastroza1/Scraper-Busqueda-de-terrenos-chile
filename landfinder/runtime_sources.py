from __future__ import annotations

from typing import Any


INTERNAL_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "osm_poi": {
        "id": "osm_poi",
        "provider": "overpass",
        "name": "OpenStreetMap POI",
        "category": "Equipamiento",
        "kind": "overpass_query",
        "depends_on_overpass": True,
    },
    "osm_poi_batch": {
        "id": "osm_poi_batch",
        "provider": "overpass",
        "name": "OpenStreetMap POI agrupado",
        "category": "Equipamiento",
        "kind": "overpass_query",
        "depends_on_overpass": True,
    },
    "osm_construction": {
        "id": "osm_construction",
        "provider": "overpass",
        "name": "Construcciones OSM",
        "category": "Desarrollo futuro",
        "kind": "overpass_query",
        "depends_on_overpass": True,
    },
    "metro_current": {
        "id": "metro_current",
        "provider": "local_cache",
        "name": "Metro actual",
        "category": "Transporte",
        "kind": "local_geojson",
        "depends_on_overpass": False,
    },
    "metro_future": {
        "id": "metro_future",
        "provider": "local_cache",
        "name": "Metro futuro",
        "category": "Transporte",
        "kind": "local_geojson",
        "depends_on_overpass": False,
    },
}


def runtime_source_record(source_id: str, official_sources: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if source_id.startswith("built_"):
        record = dict(INTERNAL_SOURCE_REGISTRY["osm_poi"])
        record["id"] = source_id
        record["name"] = f"OpenStreetMap POI · {source_id.removeprefix('built_')}"
        return record
    if source_id in INTERNAL_SOURCE_REGISTRY:
        return INTERNAL_SOURCE_REGISTRY[source_id]
    if official_sources and source_id in official_sources:
        return official_sources[source_id]
    return {"id": source_id, "provider": source_id, "kind": "unknown", "depends_on_overpass": False}


def provider_key_for(source_id: str, official_sources: dict[str, dict[str, Any]] | None = None) -> str:
    record = runtime_source_record(source_id, official_sources)
    provider = str(record.get("provider") or source_id).strip().lower()
    if record.get("depends_on_overpass") or provider == "overpass":
        return "provider:overpass"
    if provider == "local_cache":
        return f"source:{source_id}"
    return f"provider:{provider}"


def source_uses_overpass(source_id: str, official_sources: dict[str, dict[str, Any]] | None = None) -> bool:
    return bool(runtime_source_record(source_id, official_sources).get("depends_on_overpass"))
