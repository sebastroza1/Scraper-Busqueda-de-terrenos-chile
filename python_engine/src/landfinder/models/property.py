from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from landfinder.models.enums import (
    CIPStatus,
    CompatibilityStatus,
    ConnectorStrategy,
    GeometryStatus,
    GeometryType,
    ListingStatus,
    LocationPrecision,
    Program,
    RiskStatus,
    RuleResultStatus,
    SellerType,
    SourceType,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    property_id: str | None = None
    category: str | None = None
    field: str
    value: Any | None = None
    source_name: str | None = None
    source_url: AnyUrl | None = None
    layer_name: str | None = None
    source_record_id: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_value: Any | None = None
    normalized_value: Any | None = None
    source: str
    url: AnyUrl | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    method: ConnectorStrategy | str | None = None
    parser_version: str | None = None
    rule_version: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class DataProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    property_id: str
    field_name: str
    value: Any | None = None
    source_id: str
    source_type: str
    method: ConnectorStrategy | str | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(default=0.0, ge=0, le=1)
    source_url: AnyUrl | str | None = None


class PriceHistoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime = Field(default_factory=utc_now)
    asking_price_clp: Decimal | None = None
    asking_price_uf: Decimal | None = None
    uf_date: date | None = None
    source: str
    evidence_url: AnyUrl | None = None


class GeometryMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry_status: GeometryStatus = GeometryStatus.UNKNOWN
    geometry_type: GeometryType = GeometryType.UNKNOWN
    geometry_source: str | None = None
    geometry_retrieved_at: datetime | None = None
    geometry_confidence: float = Field(default=0.0, ge=0, le=1)
    parcel_geometry: dict[str, Any] | None = None
    polygon_geojson: dict[str, Any] | None = None
    official_area_m2: float | None = Field(default=None, ge=0)
    area_difference_percent: float | None = None
    geometric_area_m2: float | None = Field(default=None, ge=0)
    perimeter_m: float | None = Field(default=None, ge=0)
    estimated_width_m: float | None = Field(default=None, ge=0)
    estimated_depth_m: float | None = Field(default=None, ge=0)
    width_depth_ratio: float | None = Field(default=None, ge=0)
    verified_street_frontage_m: float | None = Field(default=None, ge=0)
    estimated_main_frontage_m: float | None = Field(default=None, ge=0)
    secondary_frontages_m: list[float] = Field(default_factory=list)
    approximate_depth_m: float | None = Field(default=None, ge=0)
    frontage_depth_ratio: float | None = Field(default=None, ge=0)
    public_road_frontage_count: int | None = Field(default=None, ge=0)
    compactness_index: float | None = Field(default=None, ge=0)
    elongation: float | None = Field(default=None, ge=0)
    irregularity_index: float | None = Field(default=None, ge=0)
    orientation_degrees: float | None = Field(default=None, ge=0, le=360)
    bounding_box: tuple[float, float, float, float] | None = None
    centroid_latitude: float | None = Field(default=None, ge=-90, le=90)
    centroid_longitude: float | None = Field(default=None, ge=-180, le=180)
    shape_quality_score: int | None = Field(default=None, ge=0, le=100)
    shape_warnings: list[str] = Field(default_factory=list)


class NetDevelopableExclusion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str
    source: str
    retrieved_at: datetime = Field(default_factory=utc_now)
    intersected_area_m2: float = Field(ge=0)
    rule_applied: str
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None


class CadastralInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_role: str | None = None
    cadastral_area_m2: float | None = Field(default=None, ge=0)
    land_use: str | None = None
    fiscal_valuation_clp: Decimal | None = None
    taxable_valuation_clp: Decimal | None = None
    exempt_valuation_clp: Decimal | None = None
    information_date: date | None = None
    source: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class UrbanFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any | None = None
    source: str
    source_document: str | None = None
    effective_date: date | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    confidence: float = Field(default=0.0, ge=0, le=1)
    manual_review_required: bool = False


class CIPInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CIPStatus = CIPStatus.NOT_REQUESTED
    document_id: str | None = None
    source_url: AnyUrl | None = None
    uploaded_at: datetime | None = None
    parsed_at: datetime | None = None
    extracted_facts: list[UrbanFact] = Field(default_factory=list)
    pending_fields: list[str] = Field(default_factory=list)


class RiskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    severity: str | None = None
    status: RiskStatus = RiskStatus.UNKNOWN
    intersected_area_m2: float | None = Field(default=None, ge=0)
    distance_m: float | None = Field(default=None, ge=0)
    source: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence_url: AnyUrl | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)


class InfrastructureAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sanitary_operational_area: str | None = None
    water_network_distance_m: float | None = Field(default=None, ge=0)
    sewer_network_distance_m: float | None = Field(default=None, ge=0)
    electricity_distance_m: float | None = Field(default=None, ge=0)
    road_access_distance_m: float | None = Field(default=None, ge=0)
    formal_feasibility_available: bool | None = None
    notes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class AccessibilityMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    nearest_name: str | None = None
    straight_line_distance_m: float | None = Field(default=None, ge=0)
    walking_network_distance_m: float | None = Field(default=None, ge=0)
    methodology: str
    source: str
    confidence: float = Field(default=0.0, ge=0, le=1)


class CapacityScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conservative_capacity: int | None = Field(default=None, ge=0)
    base_capacity: int | None = Field(default=None, ge=0)
    optimistic_capacity: int | None = Field(default=None, ge=0)
    assumptions: list[str] = Field(default_factory=list)
    warning_label: str = "ESTIMACION PRELIMINAR - REQUIERE ANTEPROYECTO"


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_score: int | None = Field(default=None, ge=0, le=100)
    price: int | None = Field(default=None, ge=0, le=100)
    net_area: int | None = Field(default=None, ge=0, le=100)
    geometry: int | None = Field(default=None, ge=0, le=100)
    urbanism: int | None = Field(default=None, ge=0, le=100)
    risks: int | None = Field(default=None, ge=0, le=100)
    transport: int | None = Field(default=None, ge=0, le=100)
    facilities: int | None = Field(default=None, ge=0, le=100)
    infrastructure: int | None = Field(default=None, ge=0, le=100)
    information_quality: int | None = Field(default=None, ge=0, le=100)
    program_compatibility: int | None = Field(default=None, ge=0, le=100)
    blocking_rule_ids: list[str] = Field(default_factory=list)


class RuleEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    program: Program
    year: int
    call: str | None = None
    status: RuleResultStatus = RuleResultStatus.UNKNOWN
    severity: str
    description: str
    legal_source: str | None = None
    effective_date: date | None = None
    automatic: bool
    checked_at: datetime = Field(default_factory=utc_now)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    notes: str | None = None


class CompatibilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: Program
    status: CompatibilityStatus = CompatibilityStatus.INFORMACION_INSUFICIENTE
    confidence: float = Field(default=0.0, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    passed_rules: list[str] = Field(default_factory=list)
    failed_rules: list[str] = Field(default_factory=list)
    unknown_rules: list[str] = Field(default_factory=list)
    pending_documents: list[str] = Field(default_factory=list)
    evaluations: list[RuleEvaluation] = Field(default_factory=list)


class DocumentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(default_factory=lambda: str(uuid4()))
    document_type: str
    original_filename: str
    stored_path: str
    sha256: str
    mime_type: str
    uploaded_at: datetime = Field(default_factory=utc_now)
    source: str = "manual"
    notes: str | None = None


class ImageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(default_factory=lambda: str(uuid4()))
    source_url: AnyUrl | None = None
    original_path: str | None = None
    preview_path: str | None = None
    sha256: str | None = None
    perceptual_hash: str | None = None
    mime_type: str | None = None
    retrieved_at: datetime | None = None
    allowed_to_download: bool | None = None


class PropertySourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    source_type: SourceType
    external_id: str | None = None
    canonical_url: AnyUrl | None = None
    first_seen: datetime = Field(default_factory=utc_now)
    last_seen: datetime = Field(default_factory=utc_now)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    parser_version: str | None = None


class PropertyCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    internal_id: str = Field(default_factory=lambda: str(uuid4()))

    # Identification
    source: str
    source_type: SourceType
    external_id: str | None = None
    canonical_url: AnyUrl | None = None
    alternative_urls: list[AnyUrl] = Field(default_factory=list)
    publication_title: str | None = None
    publication_date: date | None = None
    last_seen: datetime = Field(default_factory=utc_now)
    seller_type: SellerType = SellerType.UNKNOWN
    broker: str | None = None
    listing_status: ListingStatus = ListingStatus.UNKNOWN

    # Location
    region: str | None = None
    province: str | None = None
    commune: str | None = None
    locality: str | None = None
    original_address: str | None = None
    normalized_address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_precision: LocationPrecision = LocationPrecision.UNKNOWN
    geocoding_source: str | None = None
    geocoding_confidence: float = Field(default=0.0, ge=0, le=1)
    geometry_status: GeometryStatus = GeometryStatus.UNKNOWN
    geometry_source: str | None = None
    geometry_type: GeometryType = GeometryType.UNKNOWN
    parcel_geometry: dict[str, Any] | None = None

    # Economics
    asking_price_clp: Decimal | None = None
    asking_price_uf: Decimal | None = None
    uf_date: date | None = None
    uf_rate: Decimal | None = None
    uf_rate_date: date | None = None
    uf_source: str | None = None
    uf_retrieved_at: datetime | None = None
    uf_cache_hit: bool | None = None
    gross_area_m2: float | None = Field(default=None, ge=0)
    advertised_area_m2: float | None = Field(default=None, ge=0)
    official_area_m2: float | None = Field(default=None, ge=0)
    area_difference_percent: float | None = None
    price_uf_m2_gross: Decimal | None = None
    estimated_usable_area_m2: float | None = Field(default=None, ge=0)
    price_uf_m2_usable: Decimal | None = None
    estimated_dwelling_capacity: int | None = Field(default=None, ge=0)
    estimated_land_cost_per_dwelling: Decimal | None = None
    auction_minimum: Decimal | None = None
    auction_guarantee: Decimal | None = None
    auction_commission: Decimal | None = None
    auction_date: datetime | None = None
    price_history: list[PriceHistoryPoint] = Field(default_factory=list)

    # Enrichment
    geometry: GeometryMetrics | None = None
    estimated_net_developable_area_m2: float | None = Field(default=None, ge=0)
    net_developable_ratio: float | None = Field(default=None, ge=0, le=1)
    usable_price_uf_m2: Decimal | None = None
    net_area_exclusions: list[NetDevelopableExclusion] = Field(default_factory=list)
    cadastral: CadastralInfo | None = None
    urban_facts: list[UrbanFact] = Field(default_factory=list)
    cip: CIPInfo = Field(default_factory=CIPInfo)
    risks: list[RiskRecord] = Field(default_factory=list)
    infrastructure: InfrastructureAssessment | None = None
    accessibility: list[AccessibilityMetric] = Field(default_factory=list)
    capacity: CapacityScenario | None = None

    # Program evaluation
    ds49_assessment: CompatibilityAssessment = Field(
        default_factory=lambda: CompatibilityAssessment(program=Program.DS49)
    )
    ds19_assessment: CompatibilityAssessment = Field(
        default_factory=lambda: CompatibilityAssessment(program=Program.DS19)
    )
    score: ScoreBreakdown = Field(default_factory=ScoreBreakdown)

    # Traceability and quality
    source_records: list[PropertySourceRecord] = Field(default_factory=list)
    data_provenance: list[DataProvenance] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    documents: list[DocumentRecord] = Field(default_factory=list)
    images: list[ImageRecord] = Field(default_factory=list)
    data_quality_score: int | None = Field(default=None, ge=0, le=100)
    anomaly_flags: list[str] = Field(default_factory=list)
    documents_pending: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
