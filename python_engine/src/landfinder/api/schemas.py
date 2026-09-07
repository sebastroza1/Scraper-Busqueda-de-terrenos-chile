from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from landfinder.models.enums import ManualClassification


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regions: list[str] = Field(default_factory=list)
    provinces: list[str] = Field(default_factory=list)
    communes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=lambda: ["terreno", "inmueble", "predio", "lote"])
    keyword_mode: Literal["ANY", "ALL"] = "ANY"
    price_min_clp: int | None = Field(default=None, ge=0)
    price_max_clp: int | None = Field(default=None, ge=0)
    gross_area_min_m2: float | None = Field(default=None, ge=0)
    gross_area_max_m2: float | None = Field(default=None, ge=0)
    currency: str | None = None
    sources: list[str] = Field(default_factory=list)
    search_sources: list[str] = Field(default_factory=list)
    enrichment_sources: list[str] = Field(default_factory=lambda: ["cmf_uf"])
    include_auctions: bool = True
    extra_filters: dict = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mercado_publico_ticket: str | None = None
    mercadolibre_access_token: str | None = None
    mercadolibre_refresh_token: str | None = None
    mercadolibre_access_token_expires_at: str | None = None
    cmf_api_key: str | None = None
    reference_property_id: str | None = None
    map_provider: str | None = None


class ManualClassificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_classification: ManualClassification


class ManualPropertyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    region: str | None = None
    province: str | None = None
    commune: str | None = None
    address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    gross_area_m2: float | None = Field(default=None, ge=0)
    asking_price_clp: int | None = Field(default=None, ge=0)
    asking_price_uf: float | None = Field(default=None, ge=0)
    url: str | None = None
    observations: str | None = None


class GeocodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    address: str | None = None
    commune: str | None = None
    region: str | None = None


class PropertyLocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str | None = None
    region: str | None = None
    commune: str | None = None
    location_precision: Literal[
        "EXACT",
        "APPROXIMATE",
        "CENTROID",
        "APPROXIMATE_PROPERTY",
        "PROPERTY_COMMUNE_CENTROID",
        "UNKNOWN",
    ] = "EXACT"
