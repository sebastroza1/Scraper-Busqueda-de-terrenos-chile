from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from landfinder.connectors.base import SearchQuery, SourceConnector, SourceUnavailableError
from landfinder.core.uf import UFService, UFUnavailableError, calculate_price_fields
from landfinder.deduplication.engine import DeduplicationEngine
from landfinder.geocoding.resolver import GeolocationResolver
from landfinder.geospatial.ipt_catalog import MinvuIptCatalog
from landfinder.geospatial.minvu import MinvuArcGisConnector
from landfinder.geospatial.territorial import TerritorialAnalyzer
from landfinder.images.processor import ImageProcessor
from landfinder.models.enums import (
    JobStatus,
    PipelineEventType,
    PipelineStage,
    SourceRole,
    SourceRunStatus,
)
from landfinder.models.records import NormalizedPropertyRecord, RawSourceRecord
from landfinder.normalization.records import normalize_raw_record
from landfinder.pipeline.events import CancellationToken, EventStream, PipelineEvent
from landfinder.storage.repositories import (
    CanonicalRepository,
    Database,
    GeospatialCacheRepository,
    PropertyRepository,
    ScrapingErrorRepository,
    ScrapingRunRepository,
    SourceRecordAuditRepository,
    SourceRunStatusRepository,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class SearchPipeline:
    def __init__(
        self,
        *,
        database_path: str | Path,
        data_dir: str | Path,
        connectors: list[SourceConnector],
        uf_api_key: str | None,
    ) -> None:
        self.database = Database(database_path)
        self.data_dir = Path(data_dir)
        self.connectors = connectors
        self.uf_service = UFService(database_path, uf_api_key)
        self.image_processor = ImageProcessor(data_dir)
        self.deduper = DeduplicationEngine()
        self.properties = PropertyRepository(self.database)
        self.canonical = CanonicalRepository(self.database)
        self.runs = ScrapingRunRepository(self.database)
        self.errors = ScrapingErrorRepository(self.database)
        self.source_runs = SourceRunStatusRepository(self.database)
        self.source_records = SourceRecordAuditRepository(self.database)
        self.geolocation = GeolocationResolver(database=self.database)

    async def run(
        self,
        *,
        job_id: str,
        query: SearchQuery,
        events: EventStream,
        cancellation: CancellationToken,
    ) -> dict[str, Any]:
        raw_records: list[RawSourceRecord] = []
        normalized: list[NormalizedPropertyRecord] = []
        persisted = 0
        warnings = 0
        errors = 0
        source_received: dict[str, int] = {}
        source_status: dict[str, SourceRunStatus] = {}
        source_started: dict[str, datetime] = {}
        source_finished: dict[str, datetime] = {}
        source_warnings: dict[str, list[str]] = {}
        source_errors: dict[str, list[str]] = {}

        enabled_search_sources = _resolve_search_sources(query, self.connectors)
        enabled_enrichment_sources = set(query.enrichment_sources)

        self.runs.create(job_id, query.model_dump(mode="json"), sorted(enabled_search_sources))
        self.runs.update(job_id, status=JobStatus.RUNNING)
        self._initialize_source_runs(
            job_id=job_id,
            query=query,
            enabled_search_sources=enabled_search_sources,
            enabled_enrichment_sources=enabled_enrichment_sources,
        )

        await _emit(
            events, job_id, PipelineEventType.STARTED, PipelineStage.DISCOVERY, "Starting discovery"
        )
        for connector in self.connectors:
            if connector.source_id not in enabled_search_sources:
                continue
            if cancellation.is_cancelled:
                return await self._cancel(job_id, events)
            if not connector.is_configured():
                message = f"{connector.source_id}: SKIPPED_NOT_CONFIGURED"
                warnings += 1
                source_received[connector.source_id] = 0
                source_status[connector.source_id] = SourceRunStatus.SKIPPED_NOT_CONFIGURED
                source_warnings[connector.source_id] = [message]
                self.source_runs.upsert(
                    job_id=job_id,
                    source_id=connector.source_id,
                    source_type=SourceRole.SEARCH.value,
                    enabled=True,
                    configured=False,
                    attempted=False,
                    status=SourceRunStatus.SKIPPED_NOT_CONFIGURED.value,
                    finished_at=utc_now(),
                    warnings=[message],
                    queries=_query_terms(query),
                )
                await _emit(
                    events,
                    job_id,
                    PipelineEventType.WARNING,
                    PipelineStage.DISCOVERY,
                    message,
                    source=connector.source_id,
                )
                continue
            source_started[connector.source_id] = utc_now()
            try:
                result = await connector.discover(query)
                audit_records = result.audit_records or _audit_records_from_raw(result.raw_records)
                if audit_records:
                    self.source_records.upsert_many(job_id, audit_records)
                for item in result.raw_records:
                    raw_records.append(RawSourceRecord.model_validate(item))
                source_received[connector.source_id] = len(audit_records) or len(result.raw_records)
                source_warnings[connector.source_id] = [
                    _safe_message(item) for item in result.warnings
                ]
                source_errors[connector.source_id] = [_safe_message(item) for item in result.errors]
                source_status[connector.source_id] = (
                    SourceRunStatus.SUCCESS_WITH_WARNINGS
                    if result.warnings or result.errors
                    else SourceRunStatus.SUCCESS
                )
                source_finished[connector.source_id] = utc_now()
                warnings += len(result.warnings)
                errors += len(result.errors)
                self.source_runs.upsert(
                    job_id=job_id,
                    source_id=connector.source_id,
                    source_type=SourceRole.SEARCH.value,
                    enabled=True,
                    configured=True,
                    attempted=True,
                    status=source_status[connector.source_id].value,
                    started_at=source_started[connector.source_id],
                    finished_at=source_finished[connector.source_id],
                    records_received=source_received[connector.source_id],
                    records_accepted=len(result.raw_records),
                    records_rejected=max(
                        0,
                        source_received[connector.source_id] - len(result.raw_records),
                    ),
                    warnings=source_warnings[connector.source_id],
                    errors=source_errors[connector.source_id],
                    queries=_query_terms(query),
                )
                await _emit(
                    events,
                    job_id,
                    PipelineEventType.PROGRESS,
                    PipelineStage.DISCOVERY,
                    (
                        f"{connector.source_id}: {len(result.raw_records)} candidate(s) "
                        f"from {source_received[connector.source_id]} source record(s)"
                    ),
                    source=connector.source_id,
                    processed=len(raw_records),
                )
            except SourceUnavailableError as exc:
                warnings += 1
                status = _source_status_for_unavailable(exc)
                source_received[connector.source_id] = 0
                source_status[connector.source_id] = status
                source_finished[connector.source_id] = utc_now()
                source_warnings[connector.source_id] = [_safe_message(exc)]
                self.source_runs.upsert(
                    job_id=job_id,
                    source_id=connector.source_id,
                    source_type=SourceRole.SEARCH.value,
                    enabled=True,
                    configured=True,
                    attempted=True,
                    status=status.value,
                    started_at=source_started.get(connector.source_id),
                    finished_at=source_finished[connector.source_id],
                    warnings=source_warnings[connector.source_id],
                    queries=_query_terms(query),
                )
                self.errors.add(
                    run_id=job_id,
                    source_id=connector.source_id,
                    stage=PipelineStage.DISCOVERY,
                    property_id=None,
                    message=_safe_message(exc),
                )
                await _emit(
                    events,
                    job_id,
                    PipelineEventType.WARNING,
                    PipelineStage.DISCOVERY,
                    _safe_message(exc),
                    source=connector.source_id,
                )
            except Exception as exc:  # noqa: BLE001 - one source must not stop the whole job.
                errors += 1
                source_received[connector.source_id] = 0
                source_status[connector.source_id] = SourceRunStatus.FAILED
                source_finished[connector.source_id] = utc_now()
                source_errors[connector.source_id] = [_safe_message(exc)]
                self.source_runs.upsert(
                    job_id=job_id,
                    source_id=connector.source_id,
                    source_type=SourceRole.SEARCH.value,
                    enabled=True,
                    configured=True,
                    attempted=True,
                    status=SourceRunStatus.FAILED.value,
                    started_at=source_started.get(connector.source_id),
                    finished_at=source_finished[connector.source_id],
                    errors=source_errors[connector.source_id],
                    queries=_query_terms(query),
                )
                self.errors.add(
                    run_id=job_id,
                    source_id=connector.source_id,
                    stage=PipelineStage.DISCOVERY,
                    property_id=None,
                    message="Connector failed",
                    exception=f"{type(exc).__name__}: {exc}",
                )
                await _emit(
                    events,
                    job_id,
                    PipelineEventType.ERROR,
                    PipelineStage.DISCOVERY,
                    f"{connector.source_id} failed: {_safe_message(exc)}",
                    source=connector.source_id,
                )

        self.runs.update(job_id, status=JobStatus.RUNNING, found_count=len(raw_records))
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.DISCOVERY,
            "Discovery completed",
            processed=len(raw_records),
        )

        await _emit(
            events,
            job_id,
            PipelineEventType.STARTED,
            PipelineStage.DETAIL_EXTRACTION,
            "Detail extraction",
        )
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.DETAIL_EXTRACTION,
            "No detail endpoint required for MVP raw records",
            processed=len(raw_records),
        )

        await _emit(
            events,
            job_id,
            PipelineEventType.STARTED,
            PipelineStage.NORMALIZATION,
            "Normalizing records",
            total=len(raw_records),
        )
        for index, raw in enumerate(raw_records, start=1):
            if cancellation.is_cancelled:
                return await self._cancel(job_id, events)
            try:
                normalized.append(normalize_raw_record(raw))
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self.errors.add(
                    run_id=job_id,
                    source_id=raw.source_id,
                    stage=PipelineStage.NORMALIZATION,
                    property_id=None,
                    message="Normalization failed",
                    exception=f"{type(exc).__name__}: {exc}",
                )
            await _emit(
                events,
                job_id,
                PipelineEventType.PROGRESS,
                PipelineStage.NORMALIZATION,
                "Normalized",
                processed=index,
                total=len(raw_records),
            )
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.NORMALIZATION,
            "Normalization completed",
            processed=len(normalized),
            total=len(raw_records),
        )

        await _emit(
            events,
            job_id,
            PipelineEventType.STARTED,
            PipelineStage.UF_ENRICHMENT,
            "Enriching UF values",
            total=len(normalized),
        )
        cmf_enabled = "cmf_uf" in enabled_enrichment_sources
        cmf_started = utc_now() if cmf_enabled else None
        cmf_attempted = 0
        cmf_accepted = 0
        cmf_rejected = 0
        cmf_warnings: list[str] = []
        cmf_status = SourceRunStatus.SUCCESS
        for index, record in enumerate(normalized, start=1):
            uf_date = record.publication_date or date.today()
            uf = None
            if record.price_amount is not None:
                clp, uf_price, uf_m2 = calculate_price_fields(
                    amount=record.price_amount,
                    currency=record.price_currency,
                    area_m2=record.gross_area_m2,
                    uf=None,
                )
                record.price_clp = clp
                record.price_uf = uf_price
                record.price_uf_m2 = uf_m2
                if cmf_enabled:
                    cmf_attempted += 1
                    try:
                        uf = await self.uf_service.get_uf(uf_date)
                    except UFUnavailableError as exc:
                        cmf_rejected += 1
                        cmf_status = _uf_unavailable_status(exc)
                        record.observations.append("UF_NO_DISPONIBLE")
                        message = _safe_message(exc)
                        if message not in cmf_warnings:
                            cmf_warnings.append(message)
                            warnings += 1
                            await _emit(
                                events,
                                job_id,
                                PipelineEventType.WARNING,
                                PipelineStage.UF_ENRICHMENT,
                                message,
                                property_id=record.internal_id,
                            )
                    except Exception as exc:  # noqa: BLE001 - CMF must not block a record.
                        cmf_rejected += 1
                        cmf_status = SourceRunStatus.SERVICE_UNAVAILABLE
                        record.observations.append("UF_NO_DISPONIBLE")
                        message = f"{type(exc).__name__}: {_safe_message(exc)}"
                        if message not in cmf_warnings:
                            cmf_warnings.append(message)
                            warnings += 1
                            await _emit(
                                events,
                                job_id,
                                PipelineEventType.WARNING,
                                PipelineStage.UF_ENRICHMENT,
                                message,
                                property_id=record.internal_id,
                            )
                if uf:
                    cmf_accepted += 1
                    record.uf_date = uf.date
                    record.uf_value = uf.value
                    record.uf_rate = uf.value
                    record.uf_rate_date = uf.date
                    record.uf_source = uf.source
                    record.uf_retrieved_at = uf.retrieved_at
                    record.uf_cache_hit = uf.cache_hit
                    clp, uf_price, uf_m2 = calculate_price_fields(
                        amount=record.price_amount,
                        currency=record.price_currency,
                        area_m2=record.gross_area_m2,
                        uf=uf,
                    )
                    record.price_clp = clp
                    record.price_uf = uf_price
                    record.price_uf_m2 = uf_m2
            await _emit(
                events,
                job_id,
                PipelineEventType.PROGRESS,
                PipelineStage.UF_ENRICHMENT,
                "UF enrichment",
                processed=index,
                total=len(normalized),
            )
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.UF_ENRICHMENT,
            "UF enrichment completed",
            processed=len(normalized),
        )
        if cmf_enabled:
            if cmf_attempted == 0:
                cmf_status = SourceRunStatus.SUCCESS
            elif cmf_accepted and cmf_warnings:
                cmf_status = SourceRunStatus.SUCCESS_WITH_WARNINGS
            elif cmf_accepted:
                cmf_status = SourceRunStatus.SUCCESS
            self.source_runs.upsert(
                job_id=job_id,
                source_id="cmf_uf",
                source_type=SourceRole.ENRICHMENT.value,
                enabled=True,
                configured=bool(self.uf_service.api_key) or cmf_accepted > 0,
                attempted=cmf_attempted > 0,
                status=cmf_status.value,
                started_at=cmf_started,
                finished_at=utc_now(),
                records_received=cmf_attempted,
                records_accepted=cmf_accepted,
                records_rejected=cmf_rejected,
                warnings=cmf_warnings,
                queries=["UF"],
            )

        filtered = [record for record in normalized if _matches_query_filters(record, query)]
        discarded_by_filters = len(normalized) - len(filtered)
        if discarded_by_filters:
            await _emit(
                events,
                job_id,
                PipelineEventType.PROGRESS,
                PipelineStage.UF_ENRICHMENT,
                f"{discarded_by_filters} records discarded by local filters",
                processed=len(filtered),
                total=len(normalized),
            )
        normalized = filtered

        await _emit(
            events,
            job_id,
            PipelineEventType.STARTED,
            PipelineStage.IMAGE_PROCESSING,
            "Processing images",
            total=len(normalized),
        )
        for index, record in enumerate(normalized, start=1):
            if cancellation.is_cancelled:
                return await self._cancel(job_id, events)
            processed = await self.image_processor.process_first(
                property_id=record.internal_id,
                image_urls=record.image_urls,
            )
            if processed:
                record.preview_image_path = str(processed.preview_path)
                record.image_sha256 = processed.sha256
                record.image_phash = processed.perceptual_hash
            elif record.image_urls:
                warnings += 1
                record.observations.append("IMAGE_PROCESSING_FAILED")
            await _emit(
                events,
                job_id,
                PipelineEventType.PROGRESS,
                PipelineStage.IMAGE_PROCESSING,
                "Image processing",
                processed=index,
                total=len(normalized),
            )
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.IMAGE_PROCESSING,
            "Image processing completed",
            processed=len(normalized),
        )

        await _emit(
            events, job_id, PipelineEventType.STARTED, PipelineStage.DEDUPLICATION, "Deduplicating"
        )
        matches = self.deduper.cluster(normalized)
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.DEDUPLICATION,
            "Deduplication completed",
            processed=len(matches),
        )

        await _emit(
            events,
            job_id,
            PipelineEventType.STARTED,
            PipelineStage.PERSISTENCE,
            "Persisting records",
        )
        persisted_ids: set[str] = set()
        persisted_by_source: dict[str, int] = {}
        for record in normalized:
            try:
                persisted_id = self.properties.upsert(record)
                persisted_ids.add(persisted_id)
                persisted_by_source[record.source_id] = (
                    persisted_by_source.get(record.source_id, 0) + 1
                )
                self.source_records.link_property(
                    job_id=job_id,
                    source=record.source_id,
                    external_id=record.external_id,
                    property_id=persisted_id,
                )
                persisted += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self.errors.add(
                    run_id=job_id,
                    source_id=record.source_id,
                    stage=PipelineStage.PERSISTENCE,
                    property_id=record.internal_id,
                    message="Persistence failed",
                    exception=f"{type(exc).__name__}: {exc}",
                )
        persisted_matches = [match for match in matches if match.internal_id in persisted_ids]
        self.canonical.save_matches(persisted_matches)
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.PERSISTENCE,
            "Persistence completed",
            processed=persisted,
        )

        await _emit(
            events,
            job_id,
            PipelineEventType.STARTED,
            PipelineStage.GEOCODING,
            "Resolving property locations",
            total=len(persisted_ids),
        )
        geocoded = 0
        for index, property_id in enumerate(sorted(persisted_ids), start=1):
            if cancellation.is_cancelled:
                return await self._cancel(job_id, events)
            property_record = self.properties.get(property_id)
            if not property_record or _has_coordinates(property_record):
                geocoded += 1 if property_record and _has_coordinates(property_record) else 0
                continue
            resolution = await self.geolocation.resolve_property(property_id, persist=True)
            if resolution.result:
                geocoded += 1
            for warning in resolution.warnings:
                await _emit(
                    events,
                    job_id,
                    PipelineEventType.WARNING,
                    PipelineStage.GEOCODING,
                    warning,
                    property_id=property_id,
                )
            await _emit(
                events,
                job_id,
                PipelineEventType.PROGRESS,
                PipelineStage.GEOCODING,
                "Location resolution",
                processed=index,
                total=len(persisted_ids),
                property_id=property_id,
            )
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.GEOCODING,
            "Location resolution completed",
            processed=geocoded,
            total=len(persisted_ids),
        )

        for connector in self.connectors:
            if connector.source_id not in enabled_search_sources:
                continue
            if source_status.get(connector.source_id) in {
                SourceRunStatus.SKIPPED_NOT_CONFIGURED,
                SourceRunStatus.INVALID_CREDENTIAL,
                SourceRunStatus.RATE_LIMITED,
                SourceRunStatus.SERVICE_UNAVAILABLE,
                SourceRunStatus.FAILED,
            }:
                continue
            received = source_received.get(connector.source_id, 0)
            accepted = persisted_by_source.get(connector.source_id, 0)
            self.source_runs.upsert(
                job_id=job_id,
                source_id=connector.source_id,
                source_type=SourceRole.SEARCH.value,
                enabled=True,
                configured=True,
                attempted=True,
                status=source_status.get(connector.source_id, SourceRunStatus.SUCCESS).value,
                started_at=source_started.get(connector.source_id),
                finished_at=source_finished.get(connector.source_id) or utc_now(),
                records_received=received,
                records_accepted=accepted,
                records_rejected=max(0, received - accepted),
                warnings=source_warnings.get(connector.source_id, []),
                errors=source_errors.get(connector.source_id, []),
                queries=_query_terms(query),
            )

        minvu_result = await self._run_minvu_enrichment(
            job_id=job_id,
            enabled="minvu" in enabled_enrichment_sources,
            property_ids=sorted(persisted_ids),
            events=events,
            cancellation=cancellation,
        )
        warnings += minvu_result["warnings"]
        errors += minvu_result["errors"]
        source_record_distribution = self.source_records.distribution(job_id)
        source_records_received = source_record_distribution["total_analyzed"] or len(raw_records)

        if errors:
            status = JobStatus.COMPLETED_WITH_ERRORS
        elif warnings:
            status = JobStatus.COMPLETED_WITH_WARNINGS
        else:
            status = JobStatus.COMPLETED
        self.runs.update(
            job_id,
            status=status,
            found_count=source_records_received,
            processed_count=persisted,
            discarded_count=max(0, source_records_received - persisted),
            finished=True,
        )
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.EXPORT_READY,
            "Search job completed",
        )
        return {
            "status": status,
            "found_count": source_records_received,
            "processed_count": persisted,
            "source_records_received": source_records_received,
            "source_records_classified": source_record_distribution["total_analyzed"],
            "accepted_candidates": len(raw_records),
            "normalized_candidates": len(normalized),
            "persisted_properties": persisted,
            "possible_candidates": source_record_distribution["possible"],
            "rejected_records": source_record_distribution["rejected"],
            "manually_reviewed": source_record_distribution["manual_reviewed"],
            "classifier_distribution": source_record_distribution["distribution"],
            "warning_count": warnings,
            "error_count": errors,
            "source_run_status": self.source_runs.list_for_job(job_id),
        }

    async def _cancel(self, job_id: str, events: EventStream) -> dict[str, Any]:
        self.runs.update(job_id, status=JobStatus.CANCELLED, finished=True)
        await _emit(events, job_id, PipelineEventType.WARNING, None, "Job cancelled")
        return {"status": JobStatus.CANCELLED}

    def _initialize_source_runs(
        self,
        *,
        job_id: str,
        query: SearchQuery,
        enabled_search_sources: set[str],
        enabled_enrichment_sources: set[str],
    ) -> None:
        for connector in self.connectors:
            if connector.source_id in enabled_search_sources:
                continue
            self.source_runs.upsert(
                job_id=job_id,
                source_id=connector.source_id,
                source_type=SourceRole.SEARCH.value,
                enabled=False,
                configured=connector.is_configured(),
                attempted=False,
                status=SourceRunStatus.SKIPPED_DISABLED.value,
                finished_at=utc_now(),
                queries=_query_terms(query),
            )
        for source_id in ("cmf_uf", "minvu"):
            if source_id in enabled_enrichment_sources:
                continue
            self.source_runs.upsert(
                job_id=job_id,
                source_id=source_id,
                source_type=SourceRole.ENRICHMENT.value,
                enabled=False,
                configured=source_id == "minvu" or bool(self.uf_service.api_key),
                attempted=False,
                status=SourceRunStatus.SKIPPED_DISABLED.value,
                finished_at=utc_now(),
                queries=["UF"] if source_id == "cmf_uf" else ["urban_limit", "risk", "prc"],
            )

    async def _run_minvu_enrichment(
        self,
        *,
        job_id: str,
        enabled: bool,
        property_ids: list[str],
        events: EventStream,
        cancellation: CancellationToken,
    ) -> dict[str, int]:
        if not enabled:
            return {"warnings": 0, "errors": 0}
        started_at = utc_now()
        attempted = 0
        accepted = 0
        rejected = 0
        skipped_without_coordinates = 0
        warning_count = 0
        warnings: list[str] = []
        errors: list[str] = []
        await _emit(
            events,
            job_id,
            PipelineEventType.STARTED,
            PipelineStage.GIS_ENRICHMENT,
            "MINVU enrichment",
            total=len(property_ids),
        )
        cache = GeospatialCacheRepository(self.database)
        minvu = MinvuArcGisConnector(cache=cache)
        analyzer = TerritorialAnalyzer(
            database=self.database,
            minvu=minvu,
            ipt_catalog=MinvuIptCatalog(minvu=minvu, cache=cache),
        )
        for index, property_id in enumerate(property_ids, start=1):
            if cancellation.is_cancelled:
                break
            property_record = self.properties.get(property_id)
            if not property_record or not _has_coordinates(property_record):
                skipped_without_coordinates += 1
                await _emit(
                    events,
                    job_id,
                    PipelineEventType.PROGRESS,
                    PipelineStage.GIS_ENRICHMENT,
                    "MINVU skipped property without coordinates",
                    processed=index,
                    total=len(property_ids),
                    property_id=property_id,
                )
                continue
            attempted += 1
            try:
                await analyzer.refresh_property(property_id, force_refresh=False)
                accepted += 1
            except Exception as exc:  # noqa: BLE001 - MINVU must not block persisted records.
                rejected += 1
                warning_count += 1
                message = f"{property_id}: {type(exc).__name__}: {_safe_message(exc)}"
                warnings.append(message)
                await _emit(
                    events,
                    job_id,
                    PipelineEventType.WARNING,
                    PipelineStage.GIS_ENRICHMENT,
                    message,
                    property_id=property_id,
                )
            await _emit(
                events,
                job_id,
                PipelineEventType.PROGRESS,
                PipelineStage.GIS_ENRICHMENT,
                "MINVU enrichment",
                processed=index,
                total=len(property_ids),
                property_id=property_id,
            )
        if skipped_without_coordinates:
            message = (
                f"MINVU skipped {skipped_without_coordinates} persisted property/properties "
                "without coordinates; no territorial analysis was executed for them."
            )
            warnings.append(message)
            warning_count += 1
        status = SourceRunStatus.SUCCESS
        if warnings:
            status = (
                SourceRunStatus.SUCCESS_WITH_WARNINGS
                if accepted or skipped_without_coordinates
                else SourceRunStatus.SERVICE_UNAVAILABLE
            )
        self.source_runs.upsert(
            job_id=job_id,
            source_id="minvu",
            source_type=SourceRole.ENRICHMENT.value,
            enabled=True,
            configured=True,
            attempted=attempted > 0,
            status=status.value,
            started_at=started_at,
            finished_at=utc_now(),
            records_received=len(property_ids),
            records_accepted=accepted,
            records_rejected=rejected + skipped_without_coordinates,
            warnings=warnings,
            errors=errors,
            queries=["urban_limit", "risk", "prc"],
        )
        await _emit(
            events,
            job_id,
            PipelineEventType.COMPLETED,
            PipelineStage.GIS_ENRICHMENT,
            "MINVU enrichment completed",
            processed=accepted,
            total=len(property_ids),
        )
        return {"warnings": warning_count, "errors": 0}


async def _emit(
    events: EventStream,
    job_id: str,
    event_type: PipelineEventType,
    stage: PipelineStage | None,
    message: str,
    *,
    processed: int = 0,
    total: int | None = None,
    source: str | None = None,
    property_id: str | None = None,
) -> None:
    await events.emit(
        PipelineEvent(
            job_id=job_id,
            type=event_type,
            stage=stage,
            message=message,
            processed=processed,
            total=total,
            source=source,
            property_id=property_id,
        )
    )


def _resolve_search_sources(query: SearchQuery, connectors: list[SourceConnector]) -> set[str]:
    if query.search_sources:
        return set(query.search_sources)
    if query.sources:
        return set(query.sources)
    return {connector.source_id for connector in connectors}


def _query_terms(query: SearchQuery) -> list[str]:
    terms = list(query.keywords)
    if query.regions:
        terms.extend(f"region:{item}" for item in query.regions)
    if query.communes:
        terms.extend(f"commune:{item}" for item in query.communes)
    return terms


def _audit_records_from_raw(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit_records: list[dict[str, Any]] = []
    for item in records:
        raw_payload = item.get("raw_payload") if isinstance(item.get("raw_payload"), dict) else {}
        landfinder = (
            raw_payload.get("landfinder") if isinstance(raw_payload.get("landfinder"), dict) else {}
        )
        audit_records.append(
            {
                "source": item.get("source_id"),
                "source_type": item.get("source_type"),
                "external_id": item.get("external_id"),
                "title": item.get("title"),
                "description": item.get("description"),
                "publication_date": item.get("publication_date"),
                "region": item.get("region_raw"),
                "commune": item.get("commune_raw"),
                "source_url": item.get("canonical_url"),
                "raw_payload": raw_payload or item,
                "automatic_classification": landfinder.get(
                    "procurement_classification",
                    "UNKNOWN",
                ),
                "automatic_confidence": landfinder.get("automatic_confidence", 0),
                "automatic_score": landfinder.get("automatic_score", 0),
                "classification_reason": landfinder.get(
                    "classification_reason",
                    "Source did not provide classifier metadata.",
                ),
                "positive_terms": landfinder.get("positive_terms", []),
                "negative_terms": landfinder.get("negative_terms", []),
                "rules_triggered": landfinder.get("rules_triggered", []),
                "manual_classification": "UNREVIEWED",
                "manual_review_status": "UNREVIEWED",
            }
        )
    return audit_records


def _source_status_for_unavailable(exc: SourceUnavailableError) -> SourceRunStatus:
    message = _safe_message(exc).lower()
    if "required" in message or "missing" in message or "not configured" in message:
        return SourceRunStatus.SKIPPED_NOT_CONFIGURED
    if "rejected" in message or "credential" in message or "401" in message or "403" in message:
        return SourceRunStatus.INVALID_CREDENTIAL
    if "429" in message or "rate" in message or "limite" in message:
        return SourceRunStatus.RATE_LIMITED
    if "unavailable" in message or "timeout" in message or "temporarily" in message:
        return SourceRunStatus.SERVICE_UNAVAILABLE
    return SourceRunStatus.FAILED


def _uf_unavailable_status(exc: UFUnavailableError) -> SourceRunStatus:
    message = _safe_message(exc).lower()
    if "api_key" in message or "required" in message or "not configured" in message:
        return SourceRunStatus.SKIPPED_NOT_CONFIGURED
    if "rate" in message or "429" in message:
        return SourceRunStatus.RATE_LIMITED
    return SourceRunStatus.SERVICE_UNAVAILABLE


def _safe_message(value: Any) -> str:
    text = str(value)
    return re.sub(
        r"(?i)(ticket|apikey|access_token|refresh_token)=([^&\s'\"}\]]+)",
        r"\1=REDACTED",
        text,
    )


def _has_coordinates(property_record: dict[str, Any]) -> bool:
    precision = str(property_record.get("location_precision") or "UNKNOWN").upper()
    if precision not in {
        "PARCEL_POLYGON",
        "EXACT_COORDINATES",
        "VERIFIED_ADDRESS",
        "STREET_ADDRESS",
        "EXACT",
        "APPROXIMATE_PROPERTY",
    }:
        return False
    try:
        latitude = float(property_record.get("latitude"))
        longitude = float(property_record.get("longitude"))
    except (TypeError, ValueError):
        return False
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


def _matches_query_filters(record: NormalizedPropertyRecord, query: SearchQuery) -> bool:
    area = record.gross_area_m2
    if query.gross_area_min_m2 is not None:
        if area is None:
            if "SURFACE_PENDING" not in record.observations:
                record.observations.append("SURFACE_PENDING")
        elif area < Decimal(str(query.gross_area_min_m2)):
            return False
    if query.gross_area_max_m2 is not None:
        if area is None:
            if "SURFACE_PENDING" not in record.observations:
                record.observations.append("SURFACE_PENDING")
        elif area > Decimal(str(query.gross_area_max_m2)):
            return False

    price = record.price_clp
    if query.price_min_clp is not None:
        if price is None or price < Decimal(query.price_min_clp):
            return False
    if query.price_max_clp is not None:
        if price is None or price > Decimal(query.price_max_clp):
            return False
    return True
