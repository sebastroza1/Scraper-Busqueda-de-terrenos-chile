from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from landfinder.connectors.base import SearchQuery
from landfinder.connectors.registry import default_connectors
from landfinder.core.settings import Settings
from landfinder.models.enums import JobStatus
from landfinder.pipeline.events import CancellationToken, EventStream
from landfinder.pipeline.mvp import SearchPipeline
from landfinder.storage.repositories import (
    Database,
    ScrapingRunRepository,
    SourceRunStatusRepository,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class SearchJob:
    job_id: str
    query: SearchQuery
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    found_count: int = 0
    processed_count: int = 0
    discarded_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    result: dict | None = None
    events: EventStream = field(default_factory=EventStream)
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    task: asyncio.Task | None = None


class JobManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jobs: dict[str, SearchJob] = {}
        self.database = Database(settings.database_path)
        self.runs = ScrapingRunRepository(self.database)
        self.source_runs = SourceRunStatusRepository(self.database)

    def create_search(self, query: SearchQuery) -> SearchJob:
        job = SearchJob(job_id=str(uuid4()), query=query)
        self.jobs[job.job_id] = job
        job.task = asyncio.create_task(self._run(job))
        return job

    def get(self, job_id: str) -> SearchJob | None:
        return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        job.status = JobStatus.CANCELLING
        job.cancellation.cancel()
        return True

    async def _run(self, job: SearchJob) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = utc_now()
        pipeline = SearchPipeline(
            database_path=self.settings.database_path,
            data_dir=self.settings.data_dir,
            connectors=default_connectors(),
            uf_api_key=self.settings.cmf_api_key,
        )
        try:
            result = await pipeline.run(
                job_id=job.job_id,
                query=job.query,
                events=job.events,
                cancellation=job.cancellation,
            )
            job.result = result
            job.status = JobStatus(result.get("status", JobStatus.COMPLETED))
            job.found_count = int(result.get("found_count", 0))
            job.processed_count = int(result.get("processed_count", 0))
            job.discarded_count = max(0, job.found_count - job.processed_count)
            job.error_count = int(result.get("error_count", 0))
            job.warning_count = int(result.get("warning_count", 0))
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED
            job.result = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            job.finished_at = utc_now()


def job_to_dict(job: SearchJob) -> dict:
    result = job.result or {}
    return {
        "id": job.job_id,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "filters": job.query.model_dump(mode="json"),
        "sources": job.query.search_sources or job.query.sources,
        "search_sources": job.query.search_sources or job.query.sources,
        "enrichment_sources": job.query.enrichment_sources,
        "found_count": job.found_count,
        "processed_count": job.processed_count,
        "discarded_count": job.discarded_count,
        "source_records_received": result.get("source_records_received", job.found_count),
        "source_records_classified": result.get("source_records_classified", 0),
        "accepted_candidates": result.get("accepted_candidates", job.processed_count),
        "normalized_candidates": result.get("normalized_candidates", 0),
        "persisted_properties": result.get("persisted_properties", job.processed_count),
        "possible_candidates": result.get("possible_candidates", 0),
        "rejected_records": result.get("rejected_records", job.discarded_count),
        "manually_reviewed": result.get("manually_reviewed", 0),
        "classifier_distribution": result.get("classifier_distribution", {}),
        "error_count": job.error_count,
        "warning_count": job.warning_count,
        "events": [event.model_dump(mode="json") for event in job.events.events[-200:]],
        "source_run_status": result.get("source_run_status", []),
        "result": job.result,
    }


def ensure_data_dirs(data_dir: str | Path) -> None:
    path = Path(data_dir)
    for child in ("images", "exports", "logs", "cache", "documents"):
        (path / child).mkdir(parents=True, exist_ok=True)
