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


class ManualClassificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_classification: ManualClassification
