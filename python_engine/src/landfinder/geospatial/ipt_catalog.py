from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from landfinder.geospatial.minvu import (
    MINVU_ARCGIS_ROOT,
    ArcGisLayerConfig,
    MinvuArcGisConnector,
    arcgis_geometry_to_geojson,
)
from landfinder.storage.repositories import GeospatialCacheRepository, utc_now

CATALOG_TTL = timedelta(days=14)
LAYER_AUDIT_TTL = timedelta(days=30)
ZONING_FIELD_HINTS = (
    "ZONA",
    "COD_ZONA",
    "CODZONA",
    "NOM_ZONA",
    "NOMBRE_ZONA",
    "ZONIFICACION",
    "ZONIF",
)


@dataclass(frozen=True)
class IptLayerRef:
    service_name: str
    service_url: str
    service_type: str
    layer_id: int
    layer_name: str
    geometry_type: str | None
    spatial_reference: dict[str, Any]
    zoning_fields: list[str]
    fields: list[dict[str, Any]]
    field_aliases: dict[str, str | None]
    feature_count: int | None = None
    feature_count_status: str = "NOT_REQUESTED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "service_url": self.service_url,
            "service_type": self.service_type,
            "layer_id": self.layer_id,
            "layer_name": self.layer_name,
            "geometry_type": self.geometry_type,
            "spatial_reference": self.spatial_reference,
            "zoning_fields": self.zoning_fields,
            "fields": self.fields,
            "field_aliases": self.field_aliases,
            "feature_count": self.feature_count,
            "feature_count_status": self.feature_count_status,
        }


@dataclass(frozen=True)
class UrbanZoneResult:
    zone_code: str | None
    zone_name: str | None
    instrument: str | None
    commune: str | None
    source_service: str | None
    source_layer: str | None
    raw_attributes: dict[str, Any]
    retrieved_at: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "zone_code": self.zone_code,
            "zone_name": self.zone_name,
            "instrument": self.instrument,
            "commune": self.commune,
            "source_service": self.source_service,
            "source_layer": self.source_layer,
            "raw_attributes": self.raw_attributes,
            "retrieved_at": self.retrieved_at,
            "confidence": self.confidence,
        }


class MinvuIptCatalog:
    def __init__(
        self,
        *,
        minvu: MinvuArcGisConnector,
        cache: GeospatialCacheRepository | None = None,
        max_services: int = 120,
        max_query_layers: int = 12,
    ) -> None:
        self.minvu = minvu
        self.cache = cache if cache is not None else getattr(minvu, "cache", None)
        self.max_services = max_services
        self.max_query_layers = max_query_layers

    async def build_catalog(
        self,
        *,
        region_hint: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        cache_key = _cache_key("ipt_catalog", region_hint or "all")
        cached = self._get_cached(cache_key, force_refresh=force_refresh)
        if cached is not None:
            return cached

        services = await self.minvu.discover_services("IPT")
        entries = []
        warnings = []
        for service in services:
            name = str(service.get("name") or "")
            service_type = str(service.get("type") or "")
            if not _is_supported_service(service_type) or not _is_ipt_candidate(name):
                continue
            if region_hint and not _service_matches_region(name, region_hint):
                continue
            service_url = _service_url(self.minvu, name, service_type)
            try:
                metadata = await self.minvu.service_metadata(service_url)
            except Exception as exc:  # noqa: BLE001 - audit should continue across services.
                warnings.append(
                    {
                        "service_name": name,
                        "service_url": service_url,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            entries.append(_catalog_entry(service, service_url, metadata))
            if len(entries) >= self.max_services:
                warnings.append({"warning": "SERVICE_LIMIT_REACHED", "limit": self.max_services})
                break

        payload = {
            "source": "IDE MINVU ArcGIS REST",
            "root_url": getattr(self.minvu, "root_url", MINVU_ARCGIS_ROOT),
            "region_hint": region_hint,
            "retrieved_at": utc_now().isoformat(),
            "service_count": len(entries),
            "services": entries,
            "warnings": warnings,
        }
        self._set_cached(cache_key, payload, ttl=CATALOG_TTL, layer_id="catalog")
        return payload

    async def layer_audit(
        self,
        *,
        region_hint: str | None = None,
        include_feature_counts: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        cache_scope = f"{region_hint or 'all'}:{include_feature_counts}"
        cache_key = _cache_key("ipt_layer_audit", cache_scope)
        cached = self._get_cached(cache_key, force_refresh=force_refresh)
        if cached is not None:
            return cached

        catalog = await self.build_catalog(
            region_hint=region_hint,
            force_refresh=force_refresh,
        )
        layers: list[dict[str, Any]] = []
        warnings = list(catalog.get("warnings") or [])
        for service in catalog["services"]:
            service_url = str(service["service_url"])
            for layer in service.get("layers") or []:
                layer_id = int(layer["id"])
                try:
                    metadata = await self.minvu.layer_metadata(service_url, layer_id)
                except Exception as exc:  # noqa: BLE001 - audit should continue across layers.
                    warnings.append(
                        {
                            "service_name": service["name"],
                            "layer_id": layer_id,
                            "layer_name": layer.get("name"),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                feature_count = None
                feature_count_status = "NOT_REQUESTED"
                if include_feature_counts:
                    try:
                        feature_count = await self.minvu.layer_feature_count(
                            service_url,
                            layer_id,
                        )
                        feature_count_status = "COUNTED"
                    except Exception as exc:  # noqa: BLE001 - count is useful, not required.
                        feature_count_status = f"UNAVAILABLE:{type(exc).__name__}"
                        warnings.append(
                            {
                                "service_name": service["name"],
                                "layer_id": layer_id,
                                "layer_name": layer.get("name"),
                                "count_error": f"{type(exc).__name__}: {exc}",
                            }
                        )
                layers.append(
                    _layer_audit_entry(
                        service_name=str(service["name"]),
                        service_url=service_url,
                        service_type=str(service["type"]),
                        layer_id=layer_id,
                        layer_metadata=metadata,
                        feature_count=feature_count,
                        feature_count_status=feature_count_status,
                    )
                )

        payload = {
            "source": "IDE MINVU ArcGIS REST",
            "root_url": getattr(self.minvu, "root_url", MINVU_ARCGIS_ROOT),
            "region_hint": region_hint,
            "retrieved_at": utc_now().isoformat(),
            "layer_count": len(layers),
            "layers": layers,
            "warnings": warnings,
        }
        self._set_cached(cache_key, payload, ttl=LAYER_AUDIT_TTL, layer_id="layer_audit")
        return payload

    async def determine_prc_zone(
        self,
        *,
        geometry: dict[str, Any],
        region_hint: str | None = None,
        commune_hint: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        audit = await self.layer_audit(region_hint=region_hint, force_refresh=force_refresh)
        candidates = _candidate_zoning_layers(
            audit.get("layers") or [],
            region_hint=region_hint,
            commune_hint=commune_hint,
        )
        if not candidates:
            return {
                "status": "UNKNOWN",
                "applicable_service": None,
                "applicable_layer": None,
                "zone": None,
                "source": "IDE MINVU ArcGIS REST",
                "source_url": getattr(self.minvu, "root_url", MINVU_ARCGIS_ROOT),
                "candidate_layers": [],
                "queried_layers": [],
                "warning": "No audited PRC zoning layer exposed a recognizable zone field.",
            }

        queried_layers = []
        for candidate in candidates[: self.max_query_layers]:
            layer = ArcGisLayerConfig(
                service_url=str(candidate["service_url"]),
                layer_id=int(candidate["layer_id"]),
                layer_name=str(candidate["layer_name"]),
                ttl=timedelta(days=90),
            )
            try:
                payload = await self.minvu.query_layer(
                    layer,
                    geometry=geometry,
                    geometry_type=_arcgis_geometry_type(geometry),
                    out_fields="*",
                    return_geometry=True,
                    force_refresh=force_refresh,
                )
            except Exception as exc:  # noqa: BLE001 - continue trying candidate layers.
                queried_layers.append(
                    {
                        **_candidate_summary(candidate),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            features = payload.get("features") or []
            queried_layers.append(
                {
                    **_candidate_summary(candidate),
                    "feature_count": len(features),
                    "cache": payload.get("landfinder_cache", {}).get("status"),
                }
            )
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                attributes = feature.get("attributes") or {}
                zone_field, zone_value = _extract_zone(attributes, candidate["zoning_fields"])
                if zone_value:
                    zone_name = _first_attribute(
                        attributes,
                        ("NOM", "NOMBRE", "NOMBRE_ZONA", "DESCRIPCION", "GLOSA"),
                    )
                    instrument = _first_attribute(
                        attributes,
                        ("INSTRUM", "INSTRUMENTO", "PLAN", "NOMBRE_IPT"),
                    )
                    urban_zone = UrbanZoneResult(
                        zone_code=zone_value,
                        zone_name=zone_name,
                        instrument=instrument or str(candidate["service_name"]),
                        commune=commune_hint,
                        source_service=str(candidate["service_url"]),
                        source_layer=str(candidate["layer_name"]),
                        raw_attributes=attributes,
                        retrieved_at=utc_now().isoformat(),
                        confidence=0.75,
                    )
                    return {
                        "status": "FOUND",
                        "applicable_service": candidate["service_name"],
                        "applicable_layer": candidate["layer_name"],
                        "service_url": candidate["service_url"],
                        "layer_id": candidate["layer_id"],
                        "zone": zone_value,
                        "urban_zone": urban_zone.as_dict(),
                        "zone_field": zone_field,
                        "source": "IDE MINVU ArcGIS REST",
                        "source_url": candidate["service_url"],
                        "candidate_layers": [_candidate_summary(item) for item in candidates[:20]],
                        "queried_layers": queried_layers,
                        "matched_attributes": attributes,
                        "matched_geometries": _feature_geometries(features),
                        "matched_geojson": _feature_geojsons(features),
                    }

        return {
            "status": "UNKNOWN",
            "applicable_service": None,
            "applicable_layer": None,
            "zone": None,
            "source": "IDE MINVU ArcGIS REST",
            "source_url": getattr(self.minvu, "root_url", MINVU_ARCGIS_ROOT),
            "candidate_layers": [_candidate_summary(item) for item in candidates[:20]],
            "queried_layers": queried_layers,
            "warning": (
                "Audited PRC candidate layers were queried, but no intersecting feature "
                "with an explicit zone attribute was found."
            ),
        }

    def _get_cached(self, cache_key: str, *, force_refresh: bool) -> dict[str, Any] | None:
        if force_refresh or self.cache is None:
            return None
        cached = self.cache.get(cache_key)
        if cached is not None:
            cached["landfinder_cache"] = {"status": "HIT", "cache_key": cache_key}
        return cached

    def _set_cached(
        self,
        cache_key: str,
        payload: dict[str, Any],
        *,
        ttl: timedelta,
        layer_id: str,
    ) -> None:
        if self.cache is None:
            return
        self.cache.set(
            cache_key=cache_key,
            service_url=getattr(self.minvu, "root_url", MINVU_ARCGIS_ROOT),
            layer_id=layer_id,
            geometry_hash="catalog",
            query_hash=cache_key,
            spatial_reference="metadata",
            response=payload,
            expires_at=utc_now() + ttl,
        )


def _catalog_entry(
    service: dict[str, Any],
    service_url: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    layers = [
        {
            "id": layer.get("id"),
            "name": layer.get("name"),
            "parent_layer_id": layer.get("parentLayerId"),
            "sub_layer_ids": layer.get("subLayerIds"),
        }
        for layer in metadata.get("layers") or []
        if isinstance(layer, dict)
    ]
    return {
        "name": service.get("name"),
        "type": service.get("type"),
        "service_url": service_url,
        "description": metadata.get("serviceDescription") or metadata.get("description"),
        "spatial_reference": _spatial_reference(metadata),
        "layer_count": len(layers),
        "layers": layers,
    }


def _layer_audit_entry(
    *,
    service_name: str,
    service_url: str,
    service_type: str,
    layer_id: int,
    layer_metadata: dict[str, Any],
    feature_count: int | None,
    feature_count_status: str,
) -> dict[str, Any]:
    fields = [
        {
            "name": field.get("name"),
            "alias": field.get("alias"),
            "type": field.get("type"),
        }
        for field in layer_metadata.get("fields") or []
        if isinstance(field, dict)
    ]
    zoning_fields = _zoning_fields(fields)
    return IptLayerRef(
        service_name=service_name,
        service_url=service_url,
        service_type=service_type,
        layer_id=layer_id,
        layer_name=str(layer_metadata.get("name") or layer_id),
        geometry_type=layer_metadata.get("geometryType"),
        spatial_reference=_spatial_reference(layer_metadata),
        zoning_fields=zoning_fields,
        fields=fields,
        field_aliases={str(field["name"]): field.get("alias") for field in fields},
        feature_count=feature_count,
        feature_count_status=feature_count_status,
    ).as_dict() | {
        "capabilities": layer_metadata.get("capabilities"),
        "type": layer_metadata.get("type"),
        "has_zoning_fields": bool(zoning_fields),
        "is_queryable": "Query" in str(layer_metadata.get("capabilities") or ""),
        "last_checked": utc_now().isoformat(),
    }


def _candidate_zoning_layers(
    layers: list[dict[str, Any]],
    *,
    region_hint: str | None,
    commune_hint: str | None,
) -> list[dict[str, Any]]:
    candidates = [
        layer
        for layer in layers
        if layer.get("has_zoning_fields")
        and _is_polygon_layer(str(layer.get("geometry_type") or ""))
        and _is_prc_service(str(layer.get("service_name") or ""))
    ]
    ranked = sorted(
        candidates,
        key=lambda layer: _location_score(layer, region_hint, commune_hint),
        reverse=True,
    )
    return ranked


def _location_score(
    layer: dict[str, Any],
    region_hint: str | None,
    commune_hint: str | None,
) -> int:
    text = _normalize(
        " ".join(
            [
                str(layer.get("service_name") or ""),
                str(layer.get("layer_name") or ""),
            ]
        )
    )
    score = 0
    commune = _normalize(commune_hint or "")
    region = _normalize(region_hint or "")
    if commune and commune in text:
        score += 5
    if region and _service_matches_region(text, region):
        score += 2
    if any(word in text for word in ("zon", "zona", "uso de suelo")):
        score += 1
    return score


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_name": candidate.get("service_name"),
        "service_url": candidate.get("service_url"),
        "layer_id": candidate.get("layer_id"),
        "layer_name": candidate.get("layer_name"),
        "zoning_fields": candidate.get("zoning_fields") or [],
    }


def _feature_geometries(features: list[Any]) -> list[dict[str, Any]]:
    geometries = []
    for feature in features:
        if isinstance(feature, dict) and isinstance(feature.get("geometry"), dict):
            geometries.append(feature["geometry"])
    return geometries


def _feature_geojsons(features: list[Any]) -> list[dict[str, Any]]:
    geometries = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
            continue
        geojson = arcgis_geometry_to_geojson(feature["geometry"])
        if geojson:
            geometries.append(geojson)
    return geometries


def _extract_zone(
    attributes: dict[str, Any],
    zoning_fields: list[str],
) -> tuple[str | None, str | None]:
    for field in zoning_fields:
        value = attributes.get(field)
        if value not in (None, ""):
            return field, str(value)
    normalized_lookup = {_normalize(key): key for key in attributes}
    for hint in ZONING_FIELD_HINTS:
        key = normalized_lookup.get(_normalize(hint))
        if key and attributes.get(key) not in (None, ""):
            return key, str(attributes[key])
    return None, None


def _first_attribute(attributes: dict[str, Any], names: tuple[str, ...]) -> str | None:
    normalized_lookup = {_normalize(key): key for key in attributes}
    for name in names:
        key = normalized_lookup.get(_normalize(name))
        if key and attributes.get(key) not in (None, ""):
            return str(attributes[key])
    return None


def _zoning_fields(fields: list[dict[str, Any]]) -> list[str]:
    result = []
    for field in fields:
        name = str(field.get("name") or "")
        alias = str(field.get("alias") or "")
        normalized = _normalize(f"{name} {alias}")
        if any(_normalize(hint) in normalized for hint in ZONING_FIELD_HINTS):
            result.append(name)
    return result


def _arcgis_geometry_type(geometry: dict[str, Any]) -> str:
    geometry_type = str(geometry.get("type") or "")
    if geometry_type == "Point":
        return "esriGeometryPoint"
    if geometry_type in {"Polygon", "MultiPolygon"}:
        return "esriGeometryPolygon"
    raise ValueError(f"Unsupported geometry type for IPT query: {geometry_type}")


def _spatial_reference(metadata: dict[str, Any]) -> dict[str, Any]:
    spatial_reference = metadata.get("spatialReference")
    if isinstance(spatial_reference, dict):
        return spatial_reference
    extent = metadata.get("extent")
    if isinstance(extent, dict) and isinstance(extent.get("spatialReference"), dict):
        return extent["spatialReference"]
    return {}


def _service_url(minvu: MinvuArcGisConnector, name: str, service_type: str) -> str:
    if name.startswith("http://") or name.startswith("https://"):
        return name
    root = getattr(minvu, "root_url", MINVU_ARCGIS_ROOT).rstrip("/")
    return f"{root}/{name.strip('/')}/{service_type}"


def _is_supported_service(service_type: str) -> bool:
    return service_type in {"FeatureServer", "MapServer"}


def _is_ipt_candidate(service_name: str) -> bool:
    normalized = _normalize(service_name)
    return any(
        token in normalized
        for token in (
            "limites urbanos",
            "area riesgo",
            "areas riesgo",
            "prc",
            "pri",
            "prm",
            "ipt",
        )
    )


def _is_prc_service(service_name: str) -> bool:
    normalized = _normalize(service_name)
    return "prc" in normalized


def _is_polygon_layer(geometry_type: str) -> bool:
    return "polygon" in geometry_type.lower()


def _service_matches_region(service_name: str, region_hint: str) -> bool:
    normalized_service = _normalize(service_name)
    normalized_region = _normalize(region_hint)
    if not normalized_region:
        return True
    if "metropolitana" in normalized_region:
        return "rm" in normalized_service or "metropolitana" in normalized_service
    return any(part and part in normalized_service for part in normalized_region.split())


def _cache_key(namespace: str, value: str) -> str:
    payload = f"{namespace}:{_normalize(value)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace("_", " ").replace("-", " ")
    return " ".join(normalized.split())
