from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from landfinder.models.enums import PipelineEventType, PipelineStage


def utc_now() -> datetime:
    return datetime.now(UTC)


class PipelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    type: PipelineEventType
    stage: PipelineStage | None = None
    message: str
    processed: int = 0
    total: int | None = None
    source: str | None = None
    property_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


class EventStream:
    def __init__(self) -> None:
        self._events: list[PipelineEvent] = []
        self._queue: asyncio.Queue[PipelineEvent] = asyncio.Queue()

    @property
    def events(self) -> list[PipelineEvent]:
        return list(self._events)

    async def emit(self, event: PipelineEvent) -> None:
        self._events.append(event)
        await self._queue.put(event)

    async def next_event(self) -> PipelineEvent:
        return await self._queue.get()
