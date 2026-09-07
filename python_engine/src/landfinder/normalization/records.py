from __future__ import annotations

from decimal import Decimal
from typing import Any

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
    landfinder = raw.raw_payload.get("landfinder") if isinstance(raw.raw_payload, dict) else {}
    location_precision = _location_precision(
        raw,
        landfinder if isinstance(landfinder, dict) else {},
    )
    area = parse_area(raw.area_raw)
    price = parse_price(raw.price_raw)
    observations: list[str] = []

    if raw.price_raw and price is None:
        observations.append("PRICE_NOT_NORMALIZED")
    if raw.area_raw and area is None:
        observations.append("AREA_NOT_NORMALIZED")
    if raw.commune_raw and location.confidence < 0.7:
        observations.append("COMMUNE_TO_VERIFY")

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
        latitude=raw.latitude,
        longitude=raw.longitude,
        location_precision=location_precision,
        location_source=raw.source_id
        if raw.latitude is not None and raw.longitude is not None
        else None,
        location_method=(
            "source_coordinates" if raw.latitude is not None and raw.longitude is not None else None
        ),
        geocoded_at=raw.retrieved_at
        if raw.latitude is not None and raw.longitude is not None
        else None,
        geocoding_source=(
            "source_coordinates" if raw.latitude is not None and raw.longitude is not None else None
        ),
        geocoding_confidence=0.55 if location_precision == "APPROXIMATE_PROPERTY" else 0,
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
        return "APPROXIMATE_PROPERTY"
    return "UNKNOWN"


def as_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [as_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: as_jsonable(item) for key, item in value.items()}
    return value
