from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from landfinder.connectors.base import (
    ConnectorHealth,
    ConnectorRunResult,
    SearchQuery,
    SourceAuditResult,
    SourceConnector,
)
from landfinder.core.uf import UFService, UFValue
from landfinder.models.enums import (
    ConnectorStrategy,
    JobStatus,
    SourceAuditStatus,
    SourceHealthStatus,
    SourceRunStatus,
    SourceType,
)
from landfinder.models.records import RawSourceRecord
from landfinder.pipeline.events import CancellationToken, EventStream
from landfinder.pipeline.mvp import SearchPipeline
from landfinder.storage.repositories import (
    Database,
    DataProvenanceRepository,
    PropertyRepository,
    SourceRecordAuditRepository,
    SourceRunStatusRepository,
)


class FixtureConnector(SourceConnector):
    source_id = "fixture"
    source_name = "Fixture"
    source_type = SourceType.MARKETPLACE
    strategy = ConnectorStrategy.OPEN_DATA
    parser_version = "test"

    async def audit_source(self) -> SourceAuditResult:
        return SourceAuditResult(
            source_id=self.source_id,
            source_name=self.source_name,
            source_type=self.source_type,
            official_url="https://example.test",
            strategy=self.strategy,
            status=SourceAuditStatus.ACTIVE,
        )

    async def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            parser_version=self.parser_version,
        )

    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        record = RawSourceRecord(
            source_id=self.source_id,
            source_type=self.source_type,
            external_id="fixture-1",
            canonical_url="https://example.test/fixture-1",
            title="Terreno urbano",
            price_raw="UF 2.000",
            area_raw="10.000 m2",
            commune_raw="Maipu",
        )
        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            raw_records=[record.model_dump(mode="json")],
        )


class ConfigurableConnector(SourceConnector):
    source_name = "Configurable"
    strategy = ConnectorStrategy.OFFICIAL_API
    parser_version = "test"

    def __init__(
        self,
        source_id: str,
        *,
        source_type: SourceType = SourceType.MARKETPLACE,
        configured: bool = True,
        records: list[RawSourceRecord] | None = None,
        audit_records: list[dict] | None = None,
        warnings: list[str] | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.source_id = source_id
        self.source_type = source_type
        self._configured = configured
        self._records = records or [_raw_record(source_id, source_type)]
        self._audit_records = audit_records or []
        self._warnings = warnings or []
        self._fail = fail

    def is_configured(self) -> bool:
        return self._configured

    async def audit_source(self) -> SourceAuditResult:
        return SourceAuditResult(
            source_id=self.source_id,
            source_name=self.source_name,
            source_type=self.source_type,
            official_url="https://example.test",
            strategy=self.strategy,
            status=SourceAuditStatus.ACTIVE,
        )

    async def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            parser_version=self.parser_version,
        )

    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        if self._fail:
            raise self._fail
        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            raw_records=[record.model_dump(mode="json") for record in self._records],
            audit_records=self._audit_records,
            warnings=self._warnings,
        )


def _raw_record(
    source_id: str,
    source_type: SourceType = SourceType.MARKETPLACE,
    *,
    external_id: str | None = None,
    price_raw: str = "$ 120.000.000",
) -> RawSourceRecord:
    return RawSourceRecord(
        source_id=source_id,
        source_type=source_type,
        external_id=external_id or f"{source_id}-1",
        canonical_url=f"https://example.test/{source_id}",
        title="Terreno urbano",
        price_raw=price_raw,
        area_raw="10.000 m2",
        commune_raw="Maipu",
    )


@pytest.mark.asyncio
async def test_pipeline_persists_fixture_record(tmp_path) -> None:
    db = tmp_path / "landfinder.sqlite"
    UFService(db, None)._cache(UFValue(date=date.today(), value=Decimal("40000")))
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[FixtureConnector()],
        uf_api_key=None,
    )
    result = await pipeline.run(
        job_id="job-1",
        query=SearchQuery(sources=["fixture"]),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    assert result["status"] == JobStatus.COMPLETED
    assert PropertyRepository(Database(db)).count() == 1


@pytest.mark.asyncio
async def test_pipeline_discards_records_outside_area_filter(tmp_path) -> None:
    db = tmp_path / "landfinder.sqlite"
    UFService(db, None)._cache(UFValue(date=date.today(), value=Decimal("40000")))
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[FixtureConnector()],
        uf_api_key=None,
    )

    result = await pipeline.run(
        job_id="job-2",
        query=SearchQuery(sources=["fixture"], gross_area_min_m2=20000),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    assert result["status"] == JobStatus.COMPLETED
    assert result["found_count"] == 1
    assert result["processed_count"] == 0
    assert PropertyRepository(Database(db)).count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "search_sources",
    [
        ["mercado_publico"],
        ["mercadolibre_real_estate"],
        ["mercado_publico", "mercadolibre_real_estate"],
    ],
)
async def test_pipeline_runs_selected_search_sources_independently(
    tmp_path,
    search_sources,
) -> None:
    db = tmp_path / "landfinder.sqlite"
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[
            ConfigurableConnector(
                "mercado_publico",
                source_type=SourceType.PUBLIC_PROCUREMENT,
            ),
            ConfigurableConnector("mercadolibre_real_estate"),
        ],
        uf_api_key=None,
    )

    result = await pipeline.run(
        job_id=f"job-{'-'.join(search_sources)}",
        query=SearchQuery(search_sources=search_sources, enrichment_sources=[]),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    assert result["status"] == JobStatus.COMPLETED
    assert result["processed_count"] == len(search_sources)
    status_rows = SourceRunStatusRepository(Database(db)).list_for_job(
        result["source_run_status"][0]["job_id"]
    )
    statuses = {row["source_id"]: row["status"] for row in status_rows}
    for source_id in search_sources:
        assert statuses[source_id] == SourceRunStatus.SUCCESS


@pytest.mark.asyncio
async def test_pipeline_preserves_original_price_without_cmf(tmp_path) -> None:
    db = tmp_path / "landfinder.sqlite"
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[ConfigurableConnector("fixture")],
        uf_api_key=None,
    )

    result = await pipeline.run(
        job_id="job-no-cmf",
        query=SearchQuery(search_sources=["fixture"], enrichment_sources=[]),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    property_record = PropertyRepository(Database(db)).list()[0]
    source_status = {
        row["source_id"]: row["status"]
        for row in SourceRunStatusRepository(Database(db)).list_for_job("job-no-cmf")
    }
    assert result["status"] == JobStatus.COMPLETED
    assert property_record["asking_price_clp"] == 120000000
    assert property_record["asking_price_uf"] is None
    assert property_record["price_uf_m2_gross"] is None
    assert source_status["cmf_uf"] == SourceRunStatus.SKIPPED_DISABLED


@pytest.mark.asyncio
async def test_pipeline_records_cmf_rate_and_provenance(tmp_path) -> None:
    db = tmp_path / "landfinder.sqlite"
    UFService(db, None)._cache(UFValue(date=date.today(), value=Decimal("40000")))
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[ConfigurableConnector("fixture")],
        uf_api_key=None,
    )

    result = await pipeline.run(
        job_id="job-cmf",
        query=SearchQuery(search_sources=["fixture"], enrichment_sources=["cmf_uf"]),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    property_record = PropertyRepository(Database(db)).list()[0]
    provenance = DataProvenanceRepository(Database(db)).list_for_property(
        property_record["internal_id"]
    )
    source_status = {
        row["source_id"]: row["status"]
        for row in SourceRunStatusRepository(Database(db)).list_for_job("job-cmf")
    }
    assert result["status"] == JobStatus.COMPLETED
    assert property_record["uf_rate"] == 40000
    assert property_record["uf_cache_hit"] == 1
    assert source_status["cmf_uf"] == SourceRunStatus.SUCCESS
    assert any(
        row["source_id"] == "cmf_uf" and row["field_name"] == "uf_rate"
        for row in provenance
    )


@pytest.mark.asyncio
async def test_pipeline_completes_when_mercadolibre_not_configured_and_cmf_connected(
    tmp_path,
) -> None:
    db = tmp_path / "landfinder.sqlite"
    UFService(db, None)._cache(UFValue(date=date.today(), value=Decimal("40000")))
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[
            ConfigurableConnector(
                "mercado_publico",
                source_type=SourceType.PUBLIC_PROCUREMENT,
            ),
            ConfigurableConnector("mercadolibre_real_estate", configured=False),
        ],
        uf_api_key="configured",
    )

    result = await pipeline.run(
        job_id="job-mp-cmf-ml-skipped",
        query=SearchQuery(
            search_sources=["mercado_publico", "mercadolibre_real_estate"],
            enrichment_sources=["cmf_uf"],
        ),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    statuses = {
        row["source_id"]: row["status"]
        for row in SourceRunStatusRepository(Database(db)).list_for_job("job-mp-cmf-ml-skipped")
    }
    assert result["status"] == JobStatus.COMPLETED_WITH_WARNINGS
    assert result["processed_count"] == 1
    assert statuses["mercado_publico"] == SourceRunStatus.SUCCESS
    assert statuses["cmf_uf"] == SourceRunStatus.SUCCESS
    assert statuses["mercadolibre_real_estate"] == SourceRunStatus.SKIPPED_NOT_CONFIGURED


@pytest.mark.asyncio
async def test_pipeline_records_failed_source_without_global_failure(tmp_path) -> None:
    db = tmp_path / "landfinder.sqlite"
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[
            ConfigurableConnector("mercado_publico", source_type=SourceType.PUBLIC_PROCUREMENT),
            ConfigurableConnector("mercadolibre_real_estate", fail=RuntimeError("boom")),
        ],
        uf_api_key=None,
    )

    result = await pipeline.run(
        job_id="job-source-failed",
        query=SearchQuery(
            search_sources=["mercado_publico", "mercadolibre_real_estate"],
            enrichment_sources=[],
        ),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    statuses = {
        row["source_id"]: row["status"]
        for row in SourceRunStatusRepository(Database(db)).list_for_job("job-source-failed")
    }
    assert result["status"] == JobStatus.COMPLETED_WITH_ERRORS
    assert result["processed_count"] == 1
    assert statuses["mercadolibre_real_estate"] == SourceRunStatus.FAILED
    assert statuses["mercado_publico"] == SourceRunStatus.SUCCESS


@pytest.mark.asyncio
async def test_pipeline_reuses_existing_source_record_id_in_canonical_matches(tmp_path) -> None:
    db = tmp_path / "landfinder.sqlite"
    UFService(db, None)._cache(UFValue(date=date.today(), value=Decimal("40000")))
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[
            ConfigurableConnector(
                "mercado_publico",
                source_type=SourceType.PUBLIC_PROCUREMENT,
            )
        ],
        uf_api_key=None,
    )
    query = SearchQuery(search_sources=["mercado_publico"], enrichment_sources=["cmf_uf"])

    first = await pipeline.run(
        job_id="job-existing-first",
        query=query,
        events=EventStream(),
        cancellation=CancellationToken(),
    )
    second = await pipeline.run(
        job_id="job-existing-second",
        query=query,
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    assert first["status"] == JobStatus.COMPLETED
    assert second["status"] == JobStatus.COMPLETED
    assert PropertyRepository(Database(db)).count() == 1


@pytest.mark.asyncio
async def test_pipeline_persists_source_record_classifier_audit(tmp_path) -> None:
    db = tmp_path / "landfinder.sqlite"
    audit_records = [
        {
            "source": "mercado_publico",
            "source_type": SourceType.PUBLIC_PROCUREMENT.value,
            "external_id": "accepted-1",
            "title": "Compra terreno",
            "automatic_classification": "LAND_ACQUISITION",
            "automatic_confidence": 0.91,
            "automatic_score": 110,
            "positive_terms": ["compra", "terreno"],
            "rules_triggered": ["TITLE_LAND_ACQUISITION"],
        },
        {
            "source": "mercado_publico",
            "source_type": SourceType.PUBLIC_PROCUREMENT.value,
            "external_id": "possible-1",
            "title": "Servicio SERVIU inmueble",
            "automatic_classification": "POSSIBLE_LAND",
            "automatic_confidence": 0.55,
            "automatic_score": 20,
            "positive_terms": ["inmueble"],
        },
        {
            "source": "mercado_publico",
            "source_type": SourceType.PUBLIC_PROCUREMENT.value,
            "external_id": "rejected-1",
            "title": "Estudio de mecanica de suelo",
            "automatic_classification": "FALSE_POSITIVE",
            "automatic_confidence": 0.7,
            "automatic_score": -50,
            "negative_terms": ["estudio de suelo"],
        },
    ]
    pipeline = SearchPipeline(
        database_path=db,
        data_dir=tmp_path,
        connectors=[
            ConfigurableConnector(
                "mercado_publico",
                source_type=SourceType.PUBLIC_PROCUREMENT,
                records=[
                    _raw_record(
                        "mercado_publico",
                        SourceType.PUBLIC_PROCUREMENT,
                        external_id="accepted-1",
                    )
                ],
                audit_records=audit_records,
            )
        ],
        uf_api_key=None,
    )

    result = await pipeline.run(
        job_id="job-classifier-audit",
        query=SearchQuery(search_sources=["mercado_publico"], enrichment_sources=[]),
        events=EventStream(),
        cancellation=CancellationToken(),
    )

    source_records = SourceRecordAuditRepository(Database(db))
    distribution = source_records.distribution("job-classifier-audit")
    assert result["source_records_received"] == 3
    assert result["accepted_candidates"] == 1
    assert result["possible_candidates"] == 1
    assert result["rejected_records"] == 1
    assert distribution["distribution"] == {
        "FALSE_POSITIVE": 1,
        "LAND_ACQUISITION": 1,
        "POSSIBLE_LAND": 1,
    }
    assert source_records.list(job_id="job-classifier-audit", bucket="accepted")[0][
        "property_id"
    ]
