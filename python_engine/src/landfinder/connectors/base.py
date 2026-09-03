from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, model_validator

from landfinder.models.enums import (
    ConnectorStrategy,
    SourceAuditStatus,
    SourceHealthStatus,
    SourceRole,
    SourceType,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceUnavailableError(RuntimeError):
    """Raised when a connector cannot run under its documented conditions."""


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regions: list[str] = Field(default_factory=list)
    provinces: list[str] = Field(default_factory=list)
    communes: list[str] = Field(default_factory=list)
    polygon_geojson: dict[str, Any] | None = None
    keywords: list[str] = Field(default_factory=list)
    keyword_mode: Literal["ANY", "ALL"] = "ANY"
    price_min_clp: int | None = Field(default=None, ge=0)
    price_max_clp: int | None = Field(default=None, ge=0)
    gross_area_max_m2: float | None = Field(default=None, ge=0)
    currency: str | None = None
    sources: list[str] = Field(default_factory=list)
    search_sources: list[str] = Field(default_factory=list)
    enrichment_sources: list[str] = Field(default_factory=lambda: ["cmf_uf"])
    gross_area_min_m2: float | None = Field(default=None, ge=0)
    include_auctions: bool = True
    extra_filters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_legacy_sources(self) -> SearchQuery:
        if self.sources and not self.search_sources:
            self.search_sources = list(self.sources)
        if self.search_sources and not self.sources:
            self.sources = list(self.search_sources)
        return self


class SourceAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_name: str
    source_type: SourceType
    official_url: AnyUrl
    strategy: ConnectorStrategy
    status: SourceAuditStatus
    api_available: bool | None = None
    authentication: str | None = None
    rate_limits: str | None = None
    terms_notes: str | None = None
    obtainable_fields: list[str] = Field(default_factory=list)
    geolocation: str | None = None
    images: str | None = None
    checked_at: datetime = Field(default_factory=utc_now)
    references: list[AnyUrl] = Field(default_factory=list)
    notes: str | None = None


class ConnectorHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    status: SourceHealthStatus
    last_success_at: datetime | None = None
    recent_errors: list[str] = Field(default_factory=list)
    found_count: int = 0
    parser_version: str
    latency_ms: int | None = None
    checked_at: datetime = Field(default_factory=utc_now)


class ConnectorRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    status: SourceHealthStatus
    raw_records: list[dict[str, Any]] = Field(default_factory=list)
    audit_records: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=utc_now)


class SourceConnector(ABC):
    """Base contract for all source integrations.

    Implementations must prefer official APIs and structured geospatial services.
    Browser automation is a last resort and must never bypass access controls,
    CAPTCHA, rate limits, authentication or anti-bot systems.
    """

    source_id: str
    source_name: str
    source_type: SourceType
    strategy: ConnectorStrategy
    parser_version: str
    source_role: SourceRole = SourceRole.SEARCH

    @abstractmethod
    async def audit_source(self) -> SourceAuditResult:
        """Return current source audit metadata without extracting listings."""

    @abstractmethod
    async def health(self) -> ConnectorHealth:
        """Return connector health without claiming a search succeeded."""

    @abstractmethod
    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        """Discover candidate records from a source."""

    async def fetch_detail(self, external_id: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.source_id} does not implement detail extraction")

    def is_configured(self) -> bool:
        return True


class SearchSource(SourceConnector):
    source_role: SourceRole = SourceRole.SEARCH


class EnrichmentSource:
    source_role: SourceRole = SourceRole.ENRICHMENT
