from __future__ import annotations

from decimal import Decimal
from typing import Any

from landfinder.geospatial.geometry import calculate_parcel_metrics
from landfinder.models.records import NormalizedPropertyRecord, RawSourceRecord
from landfinder.normalization.locations import normalize_location
from landfinder.normalization.parsers import clean_text, parse_area, parse_price


def normalize_raw_record(raw: RawSourceRecord) -> NormalizedPropertyRecord:
    title = clean_text(raw.title)
    description = clean_text(raw.description)
    location = normalize_location(
        region=raw.region_raw,
        province=raw.province_raw,
        commune=raw.commune_raw,
    )
    landfinder_raw = raw.raw_payload.get("landfinder") if isinstance(raw.raw_payload, dict) else {}
    landfinder = landfinder_raw if isinstance(landfinder_raw, dict) else {}
    location_precision = _location_precision(
        raw,
        landfinder if isinstance(landfinder, dict) else {},
    )
    surface_context = str(landfinder.get("surface_context") or "PARCEL_AREA").upper()
    area = parse_area(raw.area_raw) if surface_context in {"", "PARCEL_AREA"} else None
    price = parse_price(raw.price_raw)
    observations: list[str] = []
    geometry_payload = _geometry_payload(landfinder)
    geometry_fields = _geometry_fields(geometry_payload, raw)

    if raw.price_raw and price is None:
        observations.append("PRICE_NOT_NORMALIZED")
    if raw.area_raw and area is None and surface_context in {"", "PARCEL_AREA"}:
        observations.append("AREA_NOT_NORMALIZED")
    if raw.area_raw and surface_context not in {"", "PARCEL_AREA"}:
        observations.append(f"SURFACE_CONTEXT_{surface_context}")
    if raw.commune_raw and location.confidence < 0.7:
        observations.append("COMMUNE_TO_VERIFY")
    observations.extend(str(item) for item in landfinder.get("anomaly_flags") or [])

    score = 35
    score += 10 if title else 0
    score += 10 if raw.canonical_url else 0
    score += 15 if area else 0
    score += 15 if price else 0
    score += 10 if location.commune else 0
    score += 5 if raw.latitude is not None and raw.longitude is not None else 0

    return NormalizedPropertyRecord(
        source_id=raw.source_id,
        source_type=raw.source_type,
        external_id=raw.external_id,
        canonical_url=raw.canonical_url,
        title=title,
        description=description,
        publication_date=raw.publication_date,
        region=location.region,
        province=location.province,
        commune=location.commune,
        address=clean_text(raw.address_raw),
        latitude=geometry_fields.get("latitude", raw.latitude),
        longitude=geometry_fields.get("longitude", raw.longitude),
        location_precision=geometry_fields.get("location_precision", location_precision),
        location_source=geometry_fields.get("location_source")
        or (raw.source_id if raw.latitude is not None and raw.longitude is not None else None),
        location_method=geometry_fields.get("location_method")
        or (
            "source_coordinates" if raw.latitude is not None and raw.longitude is not None else None
        ),
        geometry_status=geometry_fields.get("geometry_status", "UNKNOWN"),
        geometry_source=geometry_fields.get("geometry_source"),
        geometry_type=geometry_fields.get("geometry_type", "UNKNOWN"),
        parcel_geometry=geometry_fields.get("parcel_geometry"),
        geometry_area_m2=geometry_fields.get("geometry_area_m2"),
        geometry_perimeter_m=geometry_fields.get("geometry_perimeter_m"),
        official_area_m2=geometry_fields.get("official_area_m2"),
        area_difference_percent=geometry_fields.get("area_difference_percent"),
        geocoded_at=raw.retrieved_at
        if (
            raw.latitude is not None
            and raw.longitude is not None
            or geometry_fields.get("latitude") is not None
        )
        else None,
        geocoding_source=geometry_fields.get("location_source")
        or (
            "source_coordinates" if raw.latitude is not None and raw.longitude is not None else None
        ),
        geocoding_confidence=geometry_fields.get(
            "location_confidence",
            0.55 if location_precision == "APPROXIMATE_PROPERTY" else 0,
        ),
        gross_area_m2=area.value_m2 if area else None,
        area_raw=area.raw_value if area else raw.area_raw,
        price_raw=price.raw_value if price else raw.price_raw,
        price_amount=price.amount if price else None,
        price_currency=price.currency if price else None,
        image_urls=raw.image_urls,
        raw_payload=raw.raw_payload,
        observations=observations,
        data_quality_score=min(score, 100),
        first_seen=raw.retrieved_at,
        last_seen=raw.retrieved_at,
    )


def _location_precision(raw: RawSourceRecord, landfinder: dict[str, Any]) -> str:
    explicit = str(landfinder.get("location_precision") or "").strip().upper()
    if explicit:
        return explicit
    if raw.latitude is not None and raw.longitude is not None:
        return "EXACT_COORDINATES"
    return "UNKNOWN"


def _geometry_payload(landfinder: dict[str, Any]) -> dict[str, Any] | None:
    geometry = landfinder.get("parcel_geometry") or landfinder.get("geometry")
    return geometry if isinstance(geometry, dict) else None


def _geometry_fields(
    geometry_payload: dict[str, Any] | None,
    raw: RawSourceRecord,
) -> dict[str, Any]:
    if not geometry_payload:
        return {}
    landfinder = raw.raw_payload.get("landfinder") if isinstance(raw.raw_payload, dict) else {}
    if not isinstance(landfinder, dict):
        landfinder = {}
    official_area = _safe_float(landfinder.get("official_area_m2"))
    try:
        metrics = calculate_parcel_metrics(
            geometry_payload,
            official_area_m2=official_area,
            source_name=str(landfinder.get("geometry_source") or raw.source_id),
        )
    except Exception:
        return {
            "parcel_geometry": geometry_payload,
            "geometry_status": "UNKNOWN",
            "geometry_type": str(geometry_payload.get("type") or "UNKNOWN").upper(),
            "geometry_source": landfinder.get("geometry_source") or raw.source_id,
        }
    return {
        "latitude": metrics.centroid_latitude,
        "longitude": metrics.centroid_longitude,
        "location_precision": "PARCEL_POLYGON",
        "location_source": metrics.geometry_source or raw.source_id,
        "location_method": "official_geometry",
        "location_confidence": metrics.geometry_confidence,
        "geometry_status": str(metrics.geometry_status),
        "geometry_source": metrics.geometry_source,
        "geometry_type": str(metrics.geometry_type),
        "parcel_geometry": metrics.parcel_geometry,
        "geometry_area_m2": metrics.geometric_area_m2,
        "geometry_perimeter_m": metrics.perimeter_m,
        "official_area_m2": metrics.official_area_m2,
        "area_difference_percent": metrics.area_difference_percent,
    }


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [as_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: as_jsonable(item) for key, item in value.items()}
    return value
