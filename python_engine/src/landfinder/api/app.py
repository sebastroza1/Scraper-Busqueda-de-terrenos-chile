from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from landfinder import __version__
from landfinder.api.jobs import JobManager, ensure_data_dirs, job_to_dict
from landfinder.api.schemas import ManualClassificationUpdate, SearchRequest, SettingsUpdate
from landfinder.catalog.chile import COMMUNES_BY_REGION, REGIONS, keyword_presets
from landfinder.connectors.base import SearchQuery
from landfinder.connectors.registry import default_connectors, default_enrichment_sources
from landfinder.core.credentials import diagnose_source_credentials
from landfinder.core.logging import configure_logging
from landfinder.core.settings import Settings, load_settings
from landfinder.geospatial.ipt_catalog import MinvuIptCatalog
from landfinder.geospatial.minvu import MinvuArcGisConnector
from landfinder.geospatial.territorial import TerritorialAnalyzer
from landfinder.reports.excel import export_properties_excel
from landfinder.storage.repositories import (
    Database,
    GeospatialCacheRepository,
    PropertyRepository,
    ScrapingErrorRepository,
    SourceRecordAuditRepository,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    _sync_environment(settings)
    ensure_data_dirs(settings.data_dir)
    configure_logging(settings.data_dir)
    database = Database(settings.database_path)
    properties = PropertyRepository(database)
    errors = ScrapingErrorRepository(database)
    source_records = SourceRecordAuditRepository(database)
    geospatial_cache = GeospatialCacheRepository(database)
    minvu = MinvuArcGisConnector(cache=geospatial_cache)
    ipt_catalog = MinvuIptCatalog(minvu=minvu, cache=geospatial_cache)
    territorial = TerritorialAnalyzer(database=database, minvu=minvu, ipt_catalog=ipt_catalog)
    jobs = JobManager(settings)

    app = FastAPI(
        title="Landfinder Local API",
        version=__version__,
        description="Local-only API for preliminary land intelligence workflows.",
    )
    app.state.settings = settings
    app.state.jobs = jobs
    app.state.territorial = territorial
    app.state.minvu = minvu
    app.state.ipt_catalog = ipt_catalog

    @app.get("/health")
    async def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "version": __version__,
            "host": settings.host,
            "port": settings.port,
        }

    @app.get("/session")
    async def session() -> dict[str, str]:
        return {"token": settings.session_token}

    @app.get("/sources")
    async def sources(_: Annotated[None, Depends(_require_token)]) -> list[dict[str, str]]:
        connectors = default_connectors()
        return [
            {
                "source_id": connector.source_id,
                "source_name": connector.source_name,
                "source_role": connector.source_role,
                "source_type": connector.source_type,
                "strategy": connector.strategy,
                "parser_version": connector.parser_version,
            }
            for connector in connectors
        ]

    @app.get("/enrichment-sources")
    async def enrichment_sources(
        _: Annotated[None, Depends(_require_token)],
    ) -> list[dict[str, str]]:
        return default_enrichment_sources()

    @app.get("/sources/health")
    async def sources_health(_: Annotated[None, Depends(_require_token)]) -> list[dict]:
        return [
            (await connector.health()).model_dump(mode="json") for connector in default_connectors()
        ]

    @app.get("/catalog/regions")
    async def catalog_regions(_: Annotated[None, Depends(_require_token)]) -> dict:
        return {
            "items": [
                {
                    **region,
                    "commune_count": len(COMMUNES_BY_REGION.get(region["code"], [])),
                }
                for region in REGIONS
            ]
        }

    @app.get("/catalog/regions/{region_code}/communes")
    async def catalog_communes(
        region_code: str,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        normalized = region_code.strip().upper()
        if normalized in {"ALL", "TODAS", "TODOS", "*"}:
            return {
                "region_code": "ALL",
                "items": [
                    {
                        "code": f"{region['code']}-{index:03d}",
                        "name": commune,
                        "region_code": region["code"],
                        "region_name": region["name"],
                        "region_legacy_code": region["legacy_code"],
                    }
                    for region in REGIONS
                    for index, commune in enumerate(
                        COMMUNES_BY_REGION.get(region["code"], []), start=1
                    )
                ],
            }
        aliases = {
            region["legacy_code"].upper(): region["code"]
            for region in REGIONS
        } | {
            region["code"].upper(): region["code"]
            for region in REGIONS
        }
        canonical_code = aliases.get(normalized)
        if not canonical_code:
            raise HTTPException(status_code=404, detail="region_not_found")
        selected_region = next(region for region in REGIONS if region["code"] == canonical_code)
        return {
            "region_code": canonical_code,
            "items": [
                {
                    "code": f"{canonical_code}-{index:03d}",
                    "name": commune,
                    "region_code": canonical_code,
                    "region_name": selected_region["name"],
                    "region_legacy_code": selected_region["legacy_code"],
                }
                for index, commune in enumerate(COMMUNES_BY_REGION.get(canonical_code, []), start=1)
            ],
        }

    @app.get("/catalog/search-keyword-presets")
    async def catalog_search_keyword_presets(
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        return {"items": keyword_presets()}

    @app.get("/sources/{source_id}/audit")
    async def source_audit(source_id: str, _: Annotated[None, Depends(_require_token)]) -> dict:
        for connector in default_connectors():
            if connector.source_id == source_id:
                return (await connector.audit_source()).model_dump(mode="json")
        return {"error": "source_not_found", "source_id": source_id}

    @app.post("/searches")
    async def create_search(
        request: SearchRequest,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        query = SearchQuery(**request.model_dump())
        job = jobs.create_search(query)
        return {
            "search_id": job.job_id,
            "status": job.status,
            "created_at": job.created_at.isoformat(),
        }

    @app.get("/searches/{job_id}")
    async def get_search(job_id: str, _: Annotated[None, Depends(_require_token)]) -> dict:
        job = jobs.get(job_id)
        if not job:
            persisted = jobs.runs.get(job_id)
            if persisted:
                persisted["source_run_status"] = jobs.source_runs.list_for_job(job_id)
                return persisted
            raise HTTPException(status_code=404, detail="search_not_found")
        return job_to_dict(job)

    @app.get("/searches/{job_id}/events")
    async def search_events(
        job_id: str, _: Annotated[None, Depends(_require_token)]
    ) -> StreamingResponse:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="search_not_found")

        async def stream():
            for event in job.events.events:
                yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
            while job.status in {"QUEUED", "RUNNING", "CANCELLING"}:
                event = await job.events.next_event()
                yield f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/searches/{job_id}/source-records")
    async def list_search_source_records(
        job_id: str,
        _: Annotated[None, Depends(_require_token)],
        bucket: str | None = None,
        classification: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        safe_limit = min(max(limit, 1), 500)
        safe_offset = max(offset, 0)
        return {
            "items": source_records.list(
                job_id=job_id,
                bucket=bucket,
                classification=classification,
                q=q,
                limit=safe_limit,
                offset=safe_offset,
            ),
            "total": source_records.count(
                job_id=job_id,
                bucket=bucket,
                classification=classification,
                q=q,
            ),
            "limit": safe_limit,
            "offset": safe_offset,
            "classifier_distribution": source_records.distribution(job_id),
        }

    @app.get("/searches/{job_id}/classifier-diagnostics")
    async def classifier_diagnostics(
        job_id: str,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        return {
            "job_id": job_id,
            "classifier_distribution": source_records.distribution(job_id),
            "source_run_status": jobs.source_runs.list_for_job(job_id),
        }

    @app.get("/source-records/{source_record_id}")
    async def get_source_record(
        source_record_id: str,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        item = source_records.get(source_record_id)
        if not item:
            raise HTTPException(status_code=404, detail="source_record_not_found")
        return item

    @app.put("/source-records/{source_record_id}/manual-classification")
    async def update_source_record_manual_classification(
        source_record_id: str,
        update: ManualClassificationUpdate,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        try:
            return source_records.update_manual_classification(
                source_record_id,
                update.manual_classification,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="source_record_not_found") from exc

    @app.post("/searches/{job_id}/cancel")
    async def cancel_search(job_id: str, _: Annotated[None, Depends(_require_token)]) -> dict:
        return {"cancelled": jobs.cancel(job_id)}

    @app.get("/properties")
    async def list_properties(
        _: Annotated[None, Depends(_require_token)],
        limit: int = 50,
        offset: int = 0,
        commune: str | None = None,
        source: str | None = None,
    ) -> dict:
        return {
            "items": properties.list(limit=limit, offset=offset, commune=commune, source=source),
            "limit": limit,
            "offset": offset,
            "total": properties.count(),
        }

    @app.get("/properties/{property_id}")
    async def get_property(property_id: str, _: Annotated[None, Depends(_require_token)]) -> dict:
        item = properties.get(property_id)
        if not item:
            raise HTTPException(status_code=404, detail="property_not_found")
        return item

    @app.get("/properties/{property_id}/territory")
    async def get_property_territory(
        property_id: str,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        try:
            return territorial.summary(property_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="property_not_found") from exc

    @app.post("/properties/{property_id}/territory/refresh")
    async def refresh_property_territory(
        property_id: str,
        _: Annotated[None, Depends(_require_token)],
        force_refresh: bool = False,
    ) -> dict:
        try:
            return await territorial.refresh_property(property_id, force_refresh=force_refresh)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="property_not_found") from exc

    @app.get("/gis/minvu/services")
    async def minvu_services(_: Annotated[None, Depends(_require_token)]) -> dict:
        services = await minvu.discover_services("IPT")
        return {"source": "IDE MINVU ArcGIS REST", "services": services}

    @app.get("/gis/minvu/ipt/catalog")
    async def minvu_ipt_catalog(
        _: Annotated[None, Depends(_require_token)],
        region: str | None = None,
        force_refresh: bool = False,
    ) -> dict:
        return await ipt_catalog.build_catalog(
            region_hint=region,
            force_refresh=force_refresh,
        )

    @app.get("/gis/minvu/layer-audit")
    async def minvu_layer_audit(
        _: Annotated[None, Depends(_require_token)],
        region: str | None = None,
        include_feature_counts: bool = False,
        force_refresh: bool = False,
    ) -> dict:
        return await ipt_catalog.layer_audit(
            region_hint=region,
            include_feature_counts=include_feature_counts,
            force_refresh=force_refresh,
        )

    @app.post("/exports/excel")
    async def export_excel(_: Annotated[None, Depends(_require_token)]) -> dict:
        output = Path(settings.data_dir) / "exports" / "landfinder_export.xlsx"
        export_properties_excel(settings.database_path, output)
        return {"path": str(output), "status": "created"}

    @app.get("/settings")
    async def get_settings(_: Annotated[None, Depends(_require_token)]) -> dict:
        return {
            "data_dir": str(settings.data_dir),
            "database_path": str(settings.database_path),
            "has_cmf_api_key": bool(settings.cmf_api_key),
            "has_mercado_publico_ticket": bool(settings.mercado_publico_ticket),
            "has_mercadolibre_access_token": bool(settings.mercadolibre_access_token),
            "has_mercadolibre_refresh_token": bool(settings.mercadolibre_refresh_token),
            "mercadolibre_access_token_expires_at": (
                settings.mercadolibre_access_token_expires_at
            ),
            "reference_property_id": settings.reference_property_id,
            "progress_transport": "SSE",
            "progress_transport_reason": (
                "SSE is sufficient for one-way local job progress and simpler "
                "for desktop clients than a bidirectional WebSocket."
            ),
        }

    @app.put("/settings")
    async def put_settings(
        update: SettingsUpdate,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        if update.cmf_api_key:
            settings.cmf_api_key = update.cmf_api_key
        if update.mercado_publico_ticket:
            settings.mercado_publico_ticket = update.mercado_publico_ticket
        if update.mercadolibre_access_token:
            settings.mercadolibre_access_token = update.mercadolibre_access_token
        if update.mercadolibre_refresh_token:
            settings.mercadolibre_refresh_token = update.mercadolibre_refresh_token
        if update.mercadolibre_access_token_expires_at:
            settings.mercadolibre_access_token_expires_at = (
                update.mercadolibre_access_token_expires_at
            )
        if update.reference_property_id:
            settings.reference_property_id = update.reference_property_id
        _sync_environment(settings)
        return await get_settings(None)

    @app.post("/credentials/diagnostics/{source_id}")
    async def credential_diagnostic(
        source_id: str,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        diagnostic = await diagnose_source_credentials(settings, source_id)
        return diagnostic.as_dict()

    @app.post("/credentials/diagnostics")
    async def credential_diagnostics(_: Annotated[None, Depends(_require_token)]) -> dict:
        source_ids = ["mercado_publico", "mercadolibre_real_estate", "cmf"]
        diagnostics = [
            (await diagnose_source_credentials(settings, source_id)).as_dict()
            for source_id in source_ids
        ]
        return {"items": diagnostics}

    @app.get("/errors")
    async def list_errors(_: Annotated[None, Depends(_require_token)]) -> dict:
        return {"items": errors.list_recent()}

    return app


async def _require_token(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    expected = request.app.state.settings.session_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status_code=403, detail="invalid_token")


def _sync_environment(settings: Settings) -> None:
    if settings.cmf_api_key:
        os.environ["CMF_API_KEY"] = settings.cmf_api_key
    if settings.mercado_publico_ticket:
        os.environ["MERCADO_PUBLICO_TICKET"] = settings.mercado_publico_ticket
    if settings.mercadolibre_access_token:
        os.environ["MERCADOLIBRE_ACCESS_TOKEN"] = settings.mercadolibre_access_token
    if settings.mercadolibre_refresh_token:
        os.environ["MERCADOLIBRE_REFRESH_TOKEN"] = settings.mercadolibre_refresh_token
    if settings.mercadolibre_access_token_expires_at:
        os.environ["MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT"] = (
            settings.mercadolibre_access_token_expires_at
        )


app = create_app()
