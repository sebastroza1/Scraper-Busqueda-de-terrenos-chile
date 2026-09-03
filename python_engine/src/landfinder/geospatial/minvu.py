from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx

from landfinder.geospatial.geometry import stable_geometry_hash
from landfinder.storage.repositories import GeospatialCacheRepository, utc_now

MINVU_ARCGIS_ROOT = "https://geoide.minvu.cl/server/rest/services"
MINVU_URBAN_LIMITS_SERVICE = f"{MINVU_ARCGIS_ROOT}/IPT/Limites_Urbanos/FeatureServer"
MINVU_RISK_AREAS_SERVICE = f"{MINVU_ARCGIS_ROOT}/IPT/IPT_AREA_RIESGO/FeatureServer"


@dataclass(frozen=True)
class ArcGisLayerConfig:
    service_url: str
    layer_id: int
    layer_name: str
    source_name: str = "IDE MINVU ArcGIS REST"
    ttl: timedelta = timedelta(days=30)


URBAN_LIMIT_LAYERS = [
    ArcGisLayerConfig(
        service_url=MINVU_URBAN_LIMITS_SERVICE,
        layer_id=0,
        layer_name="Limites_Urbanos_PRC",
        ttl=timedelta(days=90),
    ),
    ArcGisLayerConfig(
        service_url=MINVU_URBAN_LIMITS_SERVICE,
        layer_id=1,
        layer_name="Limites_Urbanos_PRI",
        ttl=timedelta(days=90),
    ),
    ArcGisLayerConfig(
        service_url=MINVU_URBAN_LIMITS_SERVICE,
        layer_id=2,
        layer_name="Limites_Urbanos_PRMS",
        ttl=timedelta(days=90),
    ),
]

RISK_AREA_LAYERS = [
    ArcGisLayerConfig(
        service_url=MINVU_RISK_AREAS_SERVICE,
        layer_id=0,
        layer_name="PRC_Area_de_Riesgo",
        ttl=timedelta(days=30),
    ),
    ArcGisLayerConfig(
        service_url=MINVU_RISK_AREAS_SERVICE,
        layer_id=2,
        layer_name="PRI_Areas_de_Riesgo",
        ttl=timedelta(days=30),
    ),
]


class MinvuArcGisConnector:
    def __init__(
        self,
        *,
        cache: GeospatialCacheRepository | None = None,
        root_url: str = MINVU_ARCGIS_ROOT,
        timeout_seconds: int = 30,
    ) -> None:
        self.cache = cache
        self.root_url = root_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def discover_services(self, folder: str = "IPT") -> list[dict[str, Any]]:
        payload = await self._get_json(f"{self.root_url}/{folder}", params={"f": "json"})
        services = payload.get("services") if isinstance(payload, dict) else None
        return list(services or [])

    async def service_metadata(self, service_url: str) -> dict[str, Any]:
        return await self._get_json(service_url, params={"f": "json"})

    async def layer_metadata(self, service_url: str, layer_id: int) -> dict[str, Any]:
        return await self._get_json(f"{service_url.rstrip('/')}/{layer_id}", params={"f": "json"})

    async def layer_feature_count(
        self,
        service_url: str,
        layer_id: int,
        *,
        where: str = "1=1",
    ) -> int | None:
        payload = await self._post_json(
            f"{service_url.rstrip('/')}/{layer_id}/query",
            data={"where": where, "returnCountOnly": "true", "f": "json"},
        )
        count = payload.get("count")
        return int(count) if count is not None else None

    async def discover_prc_services(self, region_hint: str | None = None) -> list[dict[str, Any]]:
        services = await self.discover_services("IPT")
        normalized_region = _normalize(region_hint or "")
        candidates = []
        for service in services:
            name = str(service.get("name") or "")
            service_type = str(service.get("type") or "")
            if "PRC_" not in name or service_type not in {"MapServer", "FeatureServer"}:
                continue
            if normalized_region and not _region_hint_matches(name, normalized_region):
                continue
            candidates.append(service)
        return candidates

    async def query_layer(
        self,
        layer: ArcGisLayerConfig,
        *,
        geometry: dict[str, Any],
        geometry_type: str,
        in_sr: int = 4326,
        out_sr: int = 4326,
        where: str = "1=1",
        out_fields: str = "*",
        return_geometry: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        arcgis_geometry = arcgis_geometry_from_geojson(geometry, in_sr)
        query = {
            "where": where,
            "geometry": arcgis_geometry,
            "geometryType": geometry_type,
            "inSR": in_sr,
            "outSR": out_sr,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "f": "json",
        }
        cache_key, geometry_hash, query_hash = self._cache_key(
            layer,
            geometry=geometry,
            query=query,
            spatial_reference=in_sr,
        )
        if self.cache and not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                cached["landfinder_cache"] = {"status": "HIT", "cache_key": cache_key}
                return cached

        payload = await self._post_json(
            f"{layer.service_url.rstrip('/')}/{layer.layer_id}/query",
            data={**query, "geometry": json.dumps(arcgis_geometry, separators=(",", ":"))},
        )
        if self.cache:
            self.cache.set(
                cache_key=cache_key,
                service_url=layer.service_url,
                layer_id=str(layer.layer_id),
                geometry_hash=geometry_hash,
                query_hash=query_hash,
                spatial_reference=str(in_sr),
                response=payload,
                expires_at=utc_now() + layer.ttl,
            )
        payload["landfinder_cache"] = {"status": "MISS", "cache_key": cache_key}
        return payload

    async def _get_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return _checked_arcgis_payload(response.json())

    async def _post_json(self, url: str, *, data: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            return _checked_arcgis_payload(response.json())

    @staticmethod
    def _cache_key(
        layer: ArcGisLayerConfig,
        *,
        geometry: dict[str, Any],
        query: dict[str, Any],
        spatial_reference: int,
    ) -> tuple[str, str, str]:
        geometry_hash = stable_geometry_hash(geometry, spatial_reference)
        query_payload = {
            key: value
            for key, value in query.items()
            if key not in {"geometry", "f", "returnGeometry"}
        }
        query_encoded = json.dumps(
            query_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        query_hash = hashlib.sha256(query_encoded.encode("utf-8")).hexdigest()
        raw_key = "|".join(
            [
                layer.service_url,
                str(layer.layer_id),
                geometry_hash,
                query_hash,
                str(spatial_reference),
            ]
        )
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest(), geometry_hash, query_hash


def arcgis_geometry_from_geojson(
    geometry: dict[str, Any],
    spatial_reference: int,
) -> dict[str, Any]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    sr = {"wkid": spatial_reference}
    if geometry_type == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        return {"x": coordinates[0], "y": coordinates[1], "spatialReference": sr}
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        return {"rings": coordinates, "spatialReference": sr}
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        rings = []
        for polygon in coordinates:
            rings.extend(polygon)
        return {"rings": rings, "spatialReference": sr}
    raise ValueError(f"Unsupported GeoJSON geometry for ArcGIS query: {geometry_type}")


def arcgis_geometry_to_geojson(geometry: dict[str, Any]) -> dict[str, Any] | None:
    if "x" in geometry and "y" in geometry:
        return {"type": "Point", "coordinates": [geometry["x"], geometry["y"]]}
    if "rings" in geometry:
        return {"type": "Polygon", "coordinates": geometry["rings"]}
    if "paths" in geometry:
        return {"type": "LineString", "coordinates": geometry["paths"][0]}
    return None


def _checked_arcgis_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("ArcGIS response was not a JSON object")
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or "ArcGIS REST error"
        details = "; ".join(str(item) for item in error.get("details") or [])
        raise ValueError(f"{message}: {details}" if details else str(message))
    return payload


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def _region_hint_matches(service_name: str, normalized_region: str) -> bool:
    normalized_service = _normalize(service_name)
    if "metropolitana" in normalized_region:
        return "rm" in normalized_service or "metropolitana" in normalized_service
    return any(part and part in normalized_service for part in normalized_region.split())
