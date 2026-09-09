from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.ops import transform

from landfinder.normalization.locations import normalize_key
from landfinder.storage.repositories import GeospatialCacheRepository, utc_now

ADMIN_BOUNDARIES_URL = "https://ideserver.sma.gob.cl/arcgis/rest/services/IDE/Limites/MapServer/2"
ADMIN_BOUNDARY_INDEX_CACHE_KEY = "admin-boundaries:comunas:index:v2"
ADMIN_BOUNDARY_FEATURE_CACHE_PREFIX = "admin-boundary:comuna-feature:v1:"
ADMIN_BOUNDARIES_SOURCE = (
    "Grupo de Trabajo de División Política Administrativa 2023 "
    "(DIFROL, SUBDERE, IGM, INE, CIREN) via SMA IDE ArcGIS REST"
)
BLOCKING_ADMIN_STATUSES = {
    "REGION_MISMATCH",
    "COMMUNE_AND_REGION_MISMATCH",
    "OUTSIDE_CHILE",
    "GEOMETRY_INVALID",
}
ADJACENT_REGION_NAMES = {
    "atacama": {"antofagasta", "coquimbo"},
    "antofagasta": {"tarapaca", "atacama"},
    "coquimbo": {"atacama", "valparaiso"},
}


@dataclass(frozen=True)
class AdministrativeValidationResult:
    source_region: str | None
    source_commune: str | None
    calculated_region: str | None
    calculated_commune: str | None
    admin_validation_status: str
    admin_validation_confidence: float
    admin_validation_reason: str
    source_epsg: int | None
    normalized_epsg: int
    validation_point: dict[str, float] | None
    boundary_source: str = ADMIN_BOUNDARIES_SOURCE
    boundary_url: str = ADMIN_BOUNDARIES_URL

    @property
    def blocks_territorial_analysis(self) -> bool:
        return self.admin_validation_status in BLOCKING_ADMIN_STATUSES

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_region": self.source_region,
            "source_commune": self.source_commune,
            "calculated_region": self.calculated_region,
            "calculated_commune": self.calculated_commune,
            "admin_validation_status": self.admin_validation_status,
            "admin_validation_confidence": self.admin_validation_confidence,
            "admin_validation_reason": self.admin_validation_reason,
            "source_epsg": self.source_epsg,
            "normalized_epsg": self.normalized_epsg,
            "validation_point": self.validation_point,
            "boundary_source": self.boundary_source,
            "boundary_url": self.boundary_url,
        }


class AdministrativeLocationValidator:
    def __init__(
        self,
        *,
        cache: GeospatialCacheRepository | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cache = cache
        self.client = client
        self._boundaries_payload: dict[str, Any] | None = None

    async def validate_property(
        self,
        property_record: dict[str, Any],
        *,
        force_refresh: bool = False,
    ) -> AdministrativeValidationResult:
        source_region = _clean(property_record.get("region"))
        source_commune = _clean(property_record.get("commune"))
        if not source_region and not source_commune:
            return _result(
                property_record,
                status="SOURCE_ADMIN_UNKNOWN",
                confidence=0,
                reason="Source record does not provide region or commune.",
            )

        geometry, source_epsg = _property_geometry(property_record)
        if geometry is None:
            return _result(
                property_record,
                status="GEOMETRY_UNKNOWN",
                confidence=0,
                reason="Property has no parcel geometry or coordinates.",
                source_epsg=source_epsg,
            )
        try:
            normalized = _normalize_geometry(geometry, source_epsg)
            if not normalized.is_valid or normalized.is_empty:
                return _result(
                    property_record,
                    status="GEOMETRY_INVALID",
                    confidence=0,
                    reason="Geometry is empty or invalid after CRS normalization.",
                    source_epsg=source_epsg,
                )
            point = normalized.representative_point()
        except Exception as exc:  # noqa: BLE001
            return _result(
                property_record,
                status="GEOMETRY_INVALID",
                confidence=0,
                reason=f"{type(exc).__name__}: {exc}",
                source_epsg=source_epsg,
            )

        boundary = await self._admin_for_point(
            point,
            source_region=source_region,
            source_commune=source_commune,
            force_refresh=force_refresh,
        )
        if boundary is None:
            return _result(
                property_record,
                status="OUTSIDE_CHILE",
                confidence=0.7,
                reason="Validation point does not intersect an administrative commune boundary.",
                source_epsg=source_epsg,
                validation_point={"latitude": point.y, "longitude": point.x},
            )

        calculated_region = _clean(boundary.get("region"))
        calculated_commune = _clean(boundary.get("commune"))
        region_matches = _same_admin_name(source_region, calculated_region)
        commune_matches = _same_admin_name(source_commune, calculated_commune)
        if region_matches and commune_matches:
            status = "MATCH"
            reason = "Source region/commune match the administrative boundary."
            confidence = 0.95
        elif not region_matches and not commune_matches:
            status = "COMMUNE_AND_REGION_MISMATCH"
            reason = "Source region and commune differ from administrative boundary."
            confidence = 0.9
        elif not region_matches:
            status = "REGION_MISMATCH"
            reason = "Source region differs from administrative boundary."
            confidence = 0.9
        else:
            status = "COMMUNE_MISMATCH"
            reason = "Source commune differs from administrative boundary."
            confidence = 0.85
        return AdministrativeValidationResult(
            source_region=source_region,
            source_commune=source_commune,
            calculated_region=calculated_region,
            calculated_commune=calculated_commune,
            admin_validation_status=status,
            admin_validation_confidence=confidence,
            admin_validation_reason=reason,
            source_epsg=source_epsg,
            normalized_epsg=4326,
            validation_point={"latitude": point.y, "longitude": point.x},
        )

    async def _admin_for_point(
        self,
        point: Point,
        *,
        source_region: str | None,
        source_commune: str | None,
        force_refresh: bool,
    ) -> dict[str, str] | None:
        cache_key = _cache_key(point)
        if self.cache is not None and not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                boundary = _boundary_from_payload(cached)
                if boundary is not None or cached.get("landfinder_status") == "outside_chile":
                    return boundary

        params = {
            "f": "json",
            "where": "1=1",
            "outFields": "CUT_REG,CUT_COM,REGION,COMUNA",
            "returnGeometry": "false",
            "geometry": json.dumps({"x": point.x, "y": point.y}),
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "outSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        }
        payload = await self._request_json(f"{ADMIN_BOUNDARIES_URL}/query", params=params)
        boundary = _boundary_from_payload(payload)
        if boundary is None:
            boundary = await self._admin_for_point_from_boundaries(
                point,
                source_region=source_region,
                source_commune=source_commune,
                force_refresh=force_refresh,
            )
            payload = _payload_from_boundary(boundary)
        if self.cache is not None:
            self.cache.set(
                cache_key=cache_key,
                service_url=ADMIN_BOUNDARIES_URL,
                layer_id="2",
                geometry_hash=_hash(f"{point.x:.7f},{point.y:.7f}"),
                query_hash=_hash(json.dumps(params, sort_keys=True)),
                spatial_reference="EPSG:4326",
                response=payload,
                expires_at=utc_now() + timedelta(days=180),
            )
        return boundary

    async def _admin_for_point_from_boundaries(
        self,
        point: Point,
        *,
        source_region: str | None,
        source_commune: str | None,
        force_refresh: bool,
    ) -> dict[str, str] | None:
        index = await self._admin_boundary_index(force_refresh=force_refresh)
        for candidate in _boundary_candidates(index, source_region, source_commune):
            feature = await self._admin_boundary_feature(candidate, force_refresh=force_refresh)
            if _esri_geometry_covers_point(feature.get("geometry"), point):
                attributes = feature.get("attributes")
                return _boundary_from_attributes(attributes)
        return None

    async def _admin_boundary_index(self, *, force_refresh: bool) -> list[dict[str, Any]]:
        if self._boundaries_payload is not None and not force_refresh:
            features = self._boundaries_payload.get("features")
            return features if isinstance(features, list) else []
        if self.cache is not None and not force_refresh:
            cached = self.cache.get(ADMIN_BOUNDARY_INDEX_CACHE_KEY)
            if cached is not None and isinstance(cached.get("features"), list):
                self._boundaries_payload = cached
                return cached["features"]

        ids_payload = await self._request_json(
            f"{ADMIN_BOUNDARIES_URL}/query",
            params={
                "f": "json",
                "where": "OBJECTID_1 > 0",
                "returnIdsOnly": "true",
            },
        )
        object_ids = ids_payload.get("objectIds") if isinstance(ids_payload, dict) else None
        if not isinstance(object_ids, list):
            object_ids = list(range(1, 346))

        features: list[dict[str, Any]] = []
        for index in range(0, len(object_ids), 25):
            chunk = object_ids[index : index + 25]
            chunk_payload = await self._request_json(
                f"{ADMIN_BOUNDARIES_URL}/query",
                params={
                    "f": "json",
                    "objectIds": ",".join(str(item) for item in chunk),
                    "outFields": "OBJECTID_1,CUT_REG,CUT_COM,REGION,COMUNA",
                    "returnGeometry": "false",
                },
            )
            chunk_features = (
                chunk_payload.get("features") if isinstance(chunk_payload, dict) else None
            )
            if isinstance(chunk_features, list):
                features.extend(item for item in chunk_features if isinstance(item, dict))

        payload = {
            "features": features,
            "landfinder_cache_type": "admin_boundary_index",
            "source": ADMIN_BOUNDARIES_SOURCE,
        }
        self._boundaries_payload = payload
        if self.cache is not None:
            self.cache.set(
                cache_key=ADMIN_BOUNDARY_INDEX_CACHE_KEY,
                service_url=ADMIN_BOUNDARIES_URL,
                layer_id="2",
                geometry_hash=_hash("commune-index"),
                query_hash=_hash("OBJECTID_1 > 0 attrs"),
                spatial_reference="EPSG:4326",
                response=payload,
                expires_at=utc_now() + timedelta(days=180),
            )
        return features

    async def _admin_boundary_feature(
        self,
        candidate: dict[str, Any],
        *,
        force_refresh: bool,
    ) -> dict[str, Any]:
        attributes = candidate.get("attributes")
        object_id = attributes.get("OBJECTID_1") if isinstance(attributes, dict) else None
        if object_id is None:
            return candidate
        cache_key = f"{ADMIN_BOUNDARY_FEATURE_CACHE_PREFIX}{object_id}"
        if self.cache is not None and not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None and isinstance(cached.get("feature"), dict):
                return cached["feature"]

        payload = await self._request_json(
            f"{ADMIN_BOUNDARIES_URL}/query",
            params={
                "f": "json",
                "objectIds": str(object_id),
                "outFields": "CUT_REG,CUT_COM,REGION,COMUNA",
                "returnGeometry": "true",
                "geometryPrecision": "7",
                "outSR": "4326",
            },
        )
        features = payload.get("features") if isinstance(payload, dict) else None
        feature = features[0] if isinstance(features, list) and features else candidate
        if self.cache is not None:
            self.cache.set(
                cache_key=cache_key,
                service_url=ADMIN_BOUNDARIES_URL,
                layer_id="2",
                geometry_hash=_hash(str(object_id)),
                query_hash=_hash(f"objectIds={object_id} geometry"),
                spatial_reference="EPSG:4326",
                response={"feature": feature},
                expires_at=utc_now() + timedelta(days=180),
            )
        return feature

    async def _request_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        if self.client is not None:
            response = await self.client.get(url, params=params)
        else:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _property_geometry(property_record: dict[str, Any]) -> tuple[Any | None, int | None]:
    parcel = property_record.get("parcel_geometry")
    if isinstance(parcel, str) and parcel.strip():
        geometry = json.loads(parcel)
    elif isinstance(parcel, dict):
        geometry = parcel
    else:
        lat = _float(property_record.get("latitude"))
        lon = _float(property_record.get("longitude"))
        if lat is None or lon is None:
            return None, _epsg(property_record)
        return Point(lon, lat), _epsg(property_record) or 4326
    return shape(geometry), _epsg(property_record) or _epsg(geometry) or 4326


def _normalize_geometry(geometry: Any, source_epsg: int | None) -> Any:
    epsg = source_epsg or 4326
    if epsg == 4326:
        return geometry
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return transform(transformer.transform, geometry)


def _epsg(value: dict[str, Any] | Any) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in ("source_epsg", "epsg"):
        parsed = _int(value.get(key))
        if parsed:
            return parsed
    crs = value.get("crs")
    if isinstance(crs, dict):
        props = crs.get("properties") if isinstance(crs.get("properties"), dict) else {}
        for candidate in (props.get("name"), crs.get("name")):
            if candidate:
                match = str(candidate).upper().rsplit("EPSG:", maxsplit=1)
                if len(match) == 2:
                    return _int(match[1])
    return None


def _boundary_from_payload(payload: dict[str, Any]) -> dict[str, str] | None:
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        return None
    attributes = features[0].get("attributes") if isinstance(features[0], dict) else None
    return _boundary_from_attributes(attributes)


def _boundary_from_attributes(attributes: Any) -> dict[str, str] | None:
    if not isinstance(attributes, dict):
        return None
    return {
        "region": _clean(attributes.get("REGION") or attributes.get("region")),
        "commune": _clean(attributes.get("COMUNA") or attributes.get("commune")),
        "region_id": _clean(attributes.get("CUT_REG")),
        "commune_id": _clean(attributes.get("CUT_COM")),
    }


def _payload_from_boundary(boundary: dict[str, str] | None) -> dict[str, Any]:
    if boundary is None:
        return {"features": [], "landfinder_status": "outside_chile"}
    return {
        "features": [
            {
                "attributes": {
                    "CUT_REG": boundary.get("region_id"),
                    "CUT_COM": boundary.get("commune_id"),
                    "REGION": boundary.get("region"),
                    "COMUNA": boundary.get("commune"),
                }
            }
        ],
        "landfinder_status": "local_boundary_match",
    }


def _boundary_candidates(
    features: list[dict[str, Any]],
    source_region: str | None,
    source_commune: str | None,
) -> list[dict[str, Any]]:
    source_region_key = normalize_key(source_region or "")
    source_commune_key = normalize_key(source_commune or "")
    adjacent_regions = ADJACENT_REGION_NAMES.get(source_region_key, set())
    exact_commune: list[dict[str, Any]] = []
    same_region: list[dict[str, Any]] = []
    adjacent_region: list[dict[str, Any]] = []

    for feature in features:
        attributes = feature.get("attributes")
        if not isinstance(attributes, dict):
            continue
        region_key = normalize_key(str(attributes.get("REGION") or ""))
        commune_key = normalize_key(str(attributes.get("COMUNA") or ""))
        if source_commune_key and commune_key == source_commune_key:
            exact_commune.append(feature)
        elif source_region_key and region_key == source_region_key:
            same_region.append(feature)
        elif region_key in adjacent_regions:
            adjacent_region.append(feature)

    return [*exact_commune, *same_region, *adjacent_region]


def _esri_geometry_covers_point(geometry: Any, point: Point) -> bool:
    if not isinstance(geometry, dict):
        return False
    rings = geometry.get("rings")
    if not isinstance(rings, list):
        return False
    polygons = []
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            continue
        try:
            polygon = Polygon(ring)
        except Exception:  # noqa: BLE001
            continue
        if polygon.is_valid and not polygon.is_empty:
            polygons.append(polygon)
    if not polygons:
        return False
    return MultiPolygon(polygons).covers(point)


def _result(
    property_record: dict[str, Any],
    *,
    status: str,
    confidence: float,
    reason: str,
    source_epsg: int | None = None,
    validation_point: dict[str, float] | None = None,
) -> AdministrativeValidationResult:
    return AdministrativeValidationResult(
        source_region=_clean(property_record.get("region")),
        source_commune=_clean(property_record.get("commune")),
        calculated_region=None,
        calculated_commune=None,
        admin_validation_status=status,
        admin_validation_confidence=confidence,
        admin_validation_reason=reason,
        source_epsg=source_epsg,
        normalized_epsg=4326,
        validation_point=validation_point,
    )


def _cache_key(point: Point) -> str:
    return "admin-boundary:" + _hash(f"{point.x:.7f}:{point.y:.7f}:v2")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _same_admin_name(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return normalize_key(left) == normalize_key(right)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
