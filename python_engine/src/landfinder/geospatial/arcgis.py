from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx


@dataclass(frozen=True)
class ArcGisServiceLayer:
    service_url: str
    layer_id: int
    name: str
    geometry_type: str | None = None
    max_record_count: int = 1000
    spatial_reference: int = 4326


class ArcGisRestClient:
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    async def service_metadata(self, service_url: str) -> dict[str, Any]:
        return await self._get_json(service_url, params={"f": "json"})

    async def layer_metadata(self, service_url: str, layer_id: int) -> dict[str, Any]:
        return await self._get_json(f"{service_url.rstrip('/')}/{layer_id}", params={"f": "json"})

    async def query_layer(
        self,
        *,
        service_url: str,
        layer_id: int,
        where: str = "1=1",
        bbox: tuple[float, float, float, float] | None = None,
        geometry: dict[str, Any] | None = None,
        geometry_type: str | None = None,
        in_sr: int = 4326,
        out_sr: int = 4326,
        out_fields: str = "*",
        return_geometry: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "f": "json",
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true" if return_geometry else "false",
            "outSR": str(out_sr),
            "resultOffset": str(max(0, offset)),
            "resultRecordCount": str(max(1, limit)),
        }
        if bbox:
            xmin, ymin, xmax, ymax = bbox
            data.update(
                {
                    "geometry": json.dumps(
                        {
                            "xmin": xmin,
                            "ymin": ymin,
                            "xmax": xmax,
                            "ymax": ymax,
                            "spatialReference": {"wkid": in_sr},
                        },
                        separators=(",", ":"),
                    ),
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": str(in_sr),
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )
        elif geometry:
            data.update(
                {
                    "geometry": json.dumps(geometry, separators=(",", ":")),
                    "geometryType": geometry_type or _geometry_type(geometry),
                    "inSR": str(in_sr),
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )
        return await self._post_json(f"{service_url.rstrip('/')}/{layer_id}/query", data=data)

    async def _get_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return _checked(response.json())

    async def _post_json(self, url: str, *, data: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            return _checked(response.json())


def arcgis_polygon_to_geojson(geometry: dict[str, Any]) -> dict[str, Any] | None:
    rings = geometry.get("rings") if isinstance(geometry, dict) else None
    if not isinstance(rings, list) or not rings:
        return None
    return {"type": "Polygon", "coordinates": rings}


def query_evidence(
    *,
    criterion: str,
    source: str,
    endpoint: str,
    layer_id: int | str | None,
    query_status: str,
    result: str,
    feature_ids: list[str],
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "criterion": criterion,
        "source": source,
        "endpoint": endpoint,
        "layer_id": layer_id,
        "queried_at": datetime.now(UTC).isoformat(),
        "query_status": query_status,
        "result": result,
        "feature_ids": feature_ids,
        "notes": notes,
    }


def _checked(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("ArcGIS response was not a JSON object")
    error = payload.get("error")
    if isinstance(error, dict):
        details = "; ".join(str(item) for item in error.get("details") or [])
        raise ValueError(f"{error.get('message') or 'ArcGIS REST error'} {details}".strip())
    return payload


def _geometry_type(geometry: dict[str, Any]) -> str:
    if "x" in geometry and "y" in geometry:
        return "esriGeometryPoint"
    if "rings" in geometry:
        return "esriGeometryPolygon"
    if "paths" in geometry:
        return "esriGeometryPolyline"
    return "esriGeometryEnvelope"
