from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from landfinder.connectors.base import SearchQuery, SourceUnavailableError
from landfinder.models.enums import PipelineStage
from landfinder.pipeline.stages import PIPELINE_ORDER, StageResult, StageStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


StageHandler = Callable[["PipelineContext"], Awaitable[StageResult]]


class PipelineContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    query: SearchQuery
    raw_records: list[dict[str, Any]] = Field(default_factory=list)
    normalized_records: list[dict[str, Any]] = Field(default_factory=list)
    cancelled: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class PipelineRunner:
    def __init__(self) -> None:
        self._handlers: dict[PipelineStage, StageHandler] = {}

    def register(self, stage: PipelineStage, handler: StageHandler) -> None:
        self._handlers[stage] = handler

    async def run(self, context: PipelineContext) -> list[StageResult]:
        results: list[StageResult] = []
        for stage in PIPELINE_ORDER:
            if context.cancelled:
                results.append(
                    StageResult(
                        stage=stage,
                        status=StageStatus.CANCELLED,
                        finished_at=utc_now(),
                    )
                )
                break

            handler = self._handlers.get(stage)
            if handler is None:
                results.append(
                    StageResult(
                        stage=stage,
                        status=StageStatus.SKIPPED,
                        warnings=["No handler registered yet"],
                        finished_at=utc_now(),
                    )
                )
                continue

            try:
                results.append(await handler(context))
            except SourceUnavailableError as exc:
                results.append(
                    StageResult(
                        stage=stage,
                        status=StageStatus.FAILED,
                        errors=[str(exc)],
                        finished_at=utc_now(),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - pipeline must isolate stage failure.
                results.append(
                    StageResult(
                        stage=stage,
                        status=StageStatus.FAILED,
                        errors=[f"{type(exc).__name__}: {exc}"],
                        finished_at=utc_now(),
                    )
                )
        return results
