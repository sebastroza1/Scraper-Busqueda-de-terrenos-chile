from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from landfinder.models.enums import PipelineStage


def utc_now() -> datetime:
    return datetime.now(UTC)


class StageStatus(str):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class StageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PipelineStage
    status: str
    processed: int = 0
    total: int | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


PIPELINE_ORDER = [
    PipelineStage.DISCOVERY,
    PipelineStage.DETAIL_EXTRACTION,
    PipelineStage.NORMALIZATION,
    PipelineStage.UF_ENRICHMENT,
    PipelineStage.IMAGE_PROCESSING,
    PipelineStage.DEDUPLICATION,
    PipelineStage.PERSISTENCE,
    PipelineStage.EXPORT_READY,
]
