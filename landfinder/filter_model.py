from __future__ import annotations

from typing import Any

from shapely.geometry import Point, shape


PROXIMITY_ASSET_TYPES = {
    "near_hospital": "hospital",
    "near_supermarket": "supermarket",
    "near_park": "park",
}

EXCLUSION_SOURCE_IDS = {
    "exclude_risk": "minvu_area_riesgo",
    "exclude_wetlands": "mma_humedales",
    "exclude_protected": "mma_areas_protegidas",
}


def unique_ordered(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def visible_area_ids(areas: list[dict[str, Any]]) -> list[str]:
    return [area["id"] for area in areas if area.get("visible", True)]


def renderable_area_geometries(areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    geometries = []
    for area in areas:
        if not area.get("visible", True):
            continue
        geometries.append(
            {
                "id": area.get("id"),
                "name": area.get("name"),
                "sector": area.get("sector") or "",
                "geometry_type": area.get("geometry_type") or "circle",
                "lat": float(area["lat"]),
                "lon": float(area["lon"]),
                "radius_m": int(area.get("radius_m") or 0),
                "color": area.get("color"),
                "search_location": area.get("search_location"),
            }
        )
    return geometries


def overlay_signature(snapshot: dict[str, Any]) -> dict[str, Any]:
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


def active_area_record(areas: list[dict[str, Any]], active_area_id: str | None) -> dict[str, Any] | None:
    for area in areas:
        if area.get("id") == active_area_id:
            return area
    return areas[0] if areas else None


def build_source_plan(map_layers: dict[str, Any], terrain_filters: dict[str, Any]) -> dict[str, Any]:
    visible_built = set(map_layers.get("built") or [])
    filter_built = {
        asset_type
        for filter_key, asset_type in PROXIMITY_ASSET_TYPES.items()
        if terrain_filters.get(filter_key)
    }

    visible_risks = list(map_layers.get("risks") or [])
    exclusion_risks = [
        source_id
        for filter_key, source_id in EXCLUSION_SOURCE_IDS.items()
        if terrain_filters.get(filter_key)
    ]

    visible_territory = list(map_layers.get("territory") or [])
    if map_layers.get("road_network"):
        visible_territory.append("mop_red_vial")

    return {
        "built_query_types": sorted(visible_built | filter_built),
        "built_visual_types": sorted(visible_built),
        "metro_current": bool(map_layers.get("metro_current") or terrain_filters.get("near_metro")),
        "metro_current_visible": bool(map_layers.get("metro_current")),
        "metro_future": bool(map_layers.get("metro_future")),
        "metro_future_visible": bool(map_layers.get("metro_future")),
        "osm_construction": bool(map_layers.get("osm_construction")),
        "future_gis": [
            source_id
            for flag, source_id in {"seia": "sea_proyectos", "mop": "mop_contratos_obras"}.items()
            if map_layers.get(flag)
        ],
        "territory_sources": unique_ordered(visible_territory),
        "risk_sources": unique_ordered([*visible_risks, *exclusion_risks]),
        "risk_visual_sources": unique_ordered(visible_risks),
        "exclusion_sources": unique_ordered(exclusion_risks),
    }


def _feature_shapes(dataset: dict[str, Any] | None):
    if not dataset:
        return []
    shapes = []
    if dataset.get("type") == "geojson_layers":
        for layer in dataset.get("layers") or []:
            for feature in (layer.get("geojson") or {}).get("features") or []:
                geometry = feature.get("geometry")
                if geometry:
                    shapes.append(shape(geometry))
    elif dataset.get("type") == "FeatureCollection":
        for feature in dataset.get("features") or []:
            geometry = feature.get("geometry")
            if geometry:
                shapes.append(shape(geometry))
    return shapes


def _point_for_terrain(terrain: dict[str, Any]) -> Point | None:
    if terrain.get("lon") is not None and terrain.get("lat") is not None:
        return Point(float(terrain["lon"]), float(terrain["lat"]))
    geometry = terrain.get("geometry")
    if geometry:
        return shape(geometry).centroid
    return None


def terrain_intersects_any(terrain: dict[str, Any], dataset: dict[str, Any] | None) -> bool:
    point = _point_for_terrain(terrain)
    if point is None:
        return False
    return any(geom.intersects(point) for geom in _feature_shapes(dataset))


def terrain_passes_proximity(terrain: dict[str, Any], filters: dict[str, Any]) -> bool:
    proximity_map = {
        "near_metro": "metro_distance_m",
        "near_hospital": "hospital_distance_m",
        "near_supermarket": "supermarket_distance_m",
        "near_park": "park_distance_m",
    }
    for filter_key, distance_field in proximity_map.items():
        if not filters.get(filter_key):
            continue
        limit = filters.get(f"{filter_key}_distance", 1000)
        distance = terrain.get(distance_field)
        if distance is None or float(distance) > float(limit):
            return False
    return True


def apply_terrain_filters(
    terrains: list[dict[str, Any]],
    datasets: dict[str, Any],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    exclusion_pairs = {
        "exclude_risk": "minvu_area_riesgo",
        "exclude_wetlands": "mma_humedales",
        "exclude_protected": "mma_areas_protegidas",
    }
    kept = []
    for terrain in terrains:
        if not terrain_passes_proximity(terrain, filters):
            continue
        excluded = False
        for filter_key, source_id in exclusion_pairs.items():
            if filters.get(filter_key) and terrain_intersects_any(terrain, datasets.get(source_id)):
                excluded = True
                break
        if not excluded:
            kept.append(terrain)
    return kept
