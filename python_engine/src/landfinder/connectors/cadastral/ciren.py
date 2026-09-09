from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from landfinder.catalog.chile import REGIONS
from landfinder.geospatial.arcgis import ArcGisRestClient, arcgis_polygon_to_geojson
from landfinder.geospatial.geometry import calculate_parcel_metrics
from landfinder.models.enums import SourceType
from landfinder.models.records import RawSourceRecord

CIREN_RURAL_PROPERTIES_SERVICE = (
    "https://esri.ciren.cl/server/rest/services/PROPIEDADES_RURALES_1/FeatureServer"
)
CIREN_RURAL_PROPERTIES_MAP_SERVICE = (
    "https://esri.ciren.cl/server/rest/services/PROPIEDADES_RURALES_1/MapServer"
)


class CirenRuralPropertiesProvider:
    source_id = "ciren_rural_properties"
    source_name = "CIREN Propiedades Rurales"

    def __init__(
        self,
        *,
        service_url: str = CIREN_RURAL_PROPERTIES_SERVICE,
        fallback_service_url: str = CIREN_RURAL_PROPERTIES_MAP_SERVICE,
        client: ArcGisRestClient | None = None,
    ) -> None:
        self.service_url = service_url.rstrip("/")
        self.fallback_service_url = fallback_service_url.rstrip("/")
        self.client = client or ArcGisRestClient(timeout_seconds=30)

    async def discover(
        self,
        *,
        region: str | None,
        commune: str | None,
        bbox: tuple[float, float, float, float],
        surface_min_m2: float | None = None,
        surface_max_m2: float | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        service_url, metadata = await self._service_metadata()
        layers = await self._matching_layers(service_url, metadata, region)
        candidates = []
        inspected_layers = []
        remaining = max(1, min(limit, 250))
        for layer in layers:
            if remaining <= 0:
                break
            layer_id = int(layer["id"])
            layer_meta = await self.client.layer_metadata(service_url, layer_id)
            max_record_count = int(layer_meta.get("maxRecordCount") or metadata.get("maxRecordCount") or 1000)
            batch_limit = min(remaining, max(1, min(max_record_count, 250)))
            where = _where_clause(commune=commune)
            payload = await self.client.query_layer(
                service_url=service_url,
                layer_id=layer_id,
                where=where,
                bbox=bbox,
                out_fields="*",
                return_geometry=True,
                offset=offset,
                limit=batch_limit,
            )
            features = payload.get("features") or []
            inspected_layers.append(
                {
                    "layer_id": layer_id,
                    "layer_name": layer.get("name"),
                    "http": 200,
                    "feature_count": len(features),
                    "maxRecordCount": max_record_count,
                }
            )
            for feature in features:
                raw = _feature_to_raw(
                    feature,
                    service_url=service_url,
                    layer_id=layer_id,
                    layer_name=str(layer.get("name") or layer_id),
                    region=region,
                    source_updated_at=_source_year(layer.get("name")),
                )
                surface = _safe_float(raw.raw_payload.get("landfinder", {}).get("surface_m2"))
                if surface_min_m2 is not None and (surface is None or surface < surface_min_m2):
                    continue
                if surface_max_m2 is not None and (surface is None or surface > surface_max_m2):
                    continue
                candidates.append(raw)
                remaining -= 1
                if remaining <= 0:
                    break
        return {
            "source": self.source_id,
            "service_url": service_url,
            "layers": inspected_layers,
            "items": candidates,
            "limit": limit,
            "offset": offset,
        }

    async def _service_metadata(self) -> tuple[str, dict[str, Any]]:
        try:
            return self.service_url, await self.client.service_metadata(self.service_url)
        except Exception:
            return self.fallback_service_url, await self.client.service_metadata(self.fallback_service_url)

    async def _matching_layers(
        self,
        service_url: str,
        metadata: dict[str, Any],
        region: str | None,
    ) -> list[dict[str, Any]]:
        layers = [layer for layer in metadata.get("layers") or [] if isinstance(layer, dict)]
        if not region:
            return layers[:1]
        normalized = _normalize_region(region)
        matches = [layer for layer in layers if _region_matches(str(layer.get("name") or ""), normalized)]
        return matches or layers[:1]


def _feature_to_raw(
    feature: dict[str, Any],
    *,
    service_url: str,
    layer_id: int,
    layer_name: str,
    region: str | None,
    source_updated_at: str | None,
) -> RawSourceRecord:
    attributes = feature.get("attributes") if isinstance(feature, dict) else {}
    attributes = attributes if isinstance(attributes, dict) else {}
    object_id = _first(attributes, "objectid", "OBJECTID", "ObjectId", "FID")
    external_id = f"{layer_id}:{object_id}"
    geometry = arcgis_polygon_to_geojson(feature.get("geometry") or {})
    official_area = _surface_from_attributes(attributes)
    geometry_area = None
    centroid_latitude = None
    centroid_longitude = None
    if geometry:
        metrics = calculate_parcel_metrics(
            geometry,
            input_epsg=4326,
            official_area_m2=official_area,
            source_name="CIREN Propiedades Rurales",
        )
        geometry = metrics.parcel_geometry
        geometry_area = metrics.geometric_area_m2
        centroid_latitude = metrics.centroid_latitude
        centroid_longitude = metrics.centroid_longitude
    surface_m2 = official_area or geometry_area
    surface_source = "ATTRIBUTE" if official_area else "GEOMETRY_CALCULATED" if geometry_area else "UNKNOWN"
    commune = _first(attributes, "desccomu", "DESCCOMU", "comuna", "COMUNA")
    rol = _first(attributes, "rol", "ROL")
    now = datetime.now(UTC)
    raw_payload = {
        "attributes": attributes,
        "geometry": feature.get("geometry"),
        "landfinder": {
            "candidate_type": "CADASTRAL_CANDIDATE",
            "source": "ciren_rural_properties",
            "layer_id": layer_id,
            "layer_name": layer_name,
            "object_id": object_id,
            "source_geometry": feature.get("geometry"),
            "parcel_geometry": geometry,
            "geometry_source": "CIREN Propiedades Rurales",
            "source_crs": "EPSG:4326",
            "source_epsg": 4326,
            "normalized_epsg": 4326,
            "centroid": {"lat": centroid_latitude, "lon": centroid_longitude},
            "surface_m2": surface_m2,
            "surface_source": surface_source,
            "surface_context": "PARCEL_AREA",
            "official_area_m2": official_area,
            "source_updated_at": source_updated_at,
            "discovered_at": now.isoformat(),
        },
    }
    return RawSourceRecord(
        source_id="ciren_rural_properties",
        source_type=SourceType.CADASTRAL,
        external_id=external_id,
        canonical_url=f"{service_url.rstrip('/')}/{layer_id}",
        title=f"Predio rural CIREN {rol or object_id}",
        description="Candidato territorial CIREN; no implica oferta en venta.",
        price_raw=None,
        area_raw=f"{surface_m2:.2f} m2" if surface_m2 is not None else None,
        region_raw=region or _region_from_layer(layer_name),
        commune_raw=str(commune) if commune else None,
        latitude=centroid_latitude,
        longitude=centroid_longitude,
        raw_payload=raw_payload,
        retrieved_at=now,
    )


def _where_clause(*, commune: str | None) -> str:
    if not commune:
        return "1=1"
    safe_commune = commune.replace("'", "''").upper()
    return f"UPPER(desccomu) = '{safe_commune}'"


def _surface_from_attributes(attributes: dict[str, Any]) -> float | None:
    for key, value in attributes.items():
        normalized = _normalize(str(key))
        if "area" not in normalized and "superficie" not in normalized:
            continue
        parsed = _safe_float(value)
        if parsed and parsed > 0:
            return parsed
    return None


def _first(attributes: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in attributes.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _source_year(name: Any) -> str | None:
    match = re.search(r"(20\d{2}|19\d{2})", str(name or ""))
    return match.group(1) if match else None


def _region_from_layer(layer_name: str) -> str | None:
    text = _normalize(layer_name)
    for region in REGIONS:
        if _region_matches(region["name"], text):
            return region["name"]
    return None


def _normalize_region(value: str) -> str:
    text = _normalize(value)
    for region in REGIONS:
        candidates = [region["name"], region["code"], region.get("legacy_code")]
        if any(_region_matches(str(candidate), text) for candidate in candidates if candidate):
            return _normalize(region["name"])
    return text


def _region_matches(layer_name: str, normalized_region: str) -> bool:
    normalized_layer = _normalize(layer_name)
    if "metropolitana" in normalized_region:
        return "metropolitana" in normalized_layer or " rm " in f" {normalized_layer} "
    return any(part and part in normalized_layer for part in normalized_region.split())


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(without_accents.replace("_", " ").split())
