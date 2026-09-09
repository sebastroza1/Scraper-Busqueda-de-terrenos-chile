from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from landfinder.models.enums import SourceType


def utc_now() -> datetime:
    return datetime.now(UTC)


class ParsedArea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_value: str
    value_m2: Decimal
    unit: str = "m2"
    confidence: float = Field(ge=0, le=1)


class ParsedPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_value: str
    amount: Decimal
    currency: str
    confidence: float = Field(ge=0, le=1)


class RawSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: SourceType
    external_id: str | None = None
    canonical_url: str | None = None
    title: str | None = None
    description: str | None = None
    publication_date: date | None = None
    price_raw: str | None = None
    area_raw: str | None = None
    region_raw: str | None = None
    province_raw: str | None = None
    commune_raw: str | None = None
    address_raw: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    image_urls: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=utc_now)


class NormalizedPropertyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    source_type: SourceType
    external_id: str | None = None
    canonical_url: str | None = None
    title: str | None = None
    description: str | None = None
    publication_date: date | None = None
    region: str | None = None
    province: str | None = None
    commune: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_precision: str = "UNKNOWN"
    location_source: str | None = None
    location_method: str | None = None
    geometry_status: str = "UNKNOWN"
    geometry_source: str | None = None
    geometry_type: str = "UNKNOWN"
    parcel_geometry: dict[str, Any] | None = None
    geometry_area_m2: float | None = None
    geometry_perimeter_m: float | None = None
    official_area_m2: float | None = None
    area_difference_percent: float | None = None
    geocoded_at: datetime | None = None
    geocoding_source: str | None = None
    geocoding_confidence: float = Field(default=0, ge=0, le=1)
    gross_area_m2: Decimal | None = None
    area_raw: str | None = None
    price_raw: str | None = None
    price_amount: Decimal | None = None
    price_currency: str | None = None
    price_clp: Decimal | None = None
    price_uf: Decimal | None = None
    uf_date: date | None = None
    uf_value: Decimal | None = None
    uf_rate: Decimal | None = None
    uf_rate_date: date | None = None
    uf_source: str | None = None
    uf_retrieved_at: datetime | None = None
    uf_cache_hit: bool | None = None
    price_uf_m2: Decimal | None = None
    image_urls: list[str] = Field(default_factory=list)
    preview_image_path: str | None = None
    image_sha256: str | None = None
    image_phash: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    data_quality_score: int = Field(default=40, ge=0, le=100)
    first_seen: datetime = Field(default_factory=utc_now)
    last_seen: datetime = Field(default_factory=utc_now)


class CanonicalPropertyMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    internal_id: str
    match_score: float = Field(ge=0, le=1)
    match_reason: list[str] = Field(default_factory=list)
    possible_duplicate: bool = False
