from __future__ import annotations

import json
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from shapely.geometry import LineString, Point, shape

from landfinder import __version__
from landfinder.api.jobs import JobManager, ensure_data_dirs, job_to_dict
from landfinder.api.schemas import (
    GeocodeRequest,
    ManualClassificationUpdate,
    ManualPropertyCreate,
    MercadoLibreImportAnalyzeRequest,
    MercadoLibreImportRequest,
    PropertyLocationUpdate,
    SearchRequest,
    SettingsUpdate,
    SoilDiscoveryRequest,
)
from landfinder.catalog.chile import COMMUNES_BY_REGION, REGIONS, communes_catalog, keyword_presets
from landfinder.connectors.base import SearchQuery
from landfinder.connectors.cadastral.ciren import CirenRuralPropertiesProvider
from landfinder.connectors.marketplaces.mercadolibre import MercadoLibreRealEstateConnector
from landfinder.connectors.registry import default_connectors, default_enrichment_sources
from landfinder.connectors.transforms import mercadolibre_item_to_raw
from landfinder.geospatial.arcgis import ArcGisRestClient, query_evidence
from landfinder.geospatial.geometry import local_metric_epsg, reproject_geometry
from landfinder.core.credentials import diagnose_source_credentials
from landfinder.core.logging import configure_logging
from landfinder.core.settings import Settings, load_settings
from landfinder.core.windows_secrets import write_windows_secret
from landfinder.geocoding.providers import GeocodingRequest
from landfinder.geocoding.resolver import GeolocationResolver
from landfinder.geospatial.ipt_catalog import MinvuIptCatalog
from landfinder.geospatial.minvu import (
    RISK_AREA_LAYERS,
    URBAN_LIMIT_LAYERS,
    MinvuArcGisConnector,
)
from landfinder.geospatial.territorial import TerritorialAnalyzer
from landfinder.normalization.records import normalize_raw_record
from landfinder.reports.excel import export_properties_excel
from landfinder.storage.repositories import (
    Database,
    GeospatialCacheRepository,
    MinvuLayerRepository,
    PropertyRepository,
    ScrapingErrorRepository,
    SourceRecordAuditRepository,
    utc_now,
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
    geolocation = GeolocationResolver(database=database)
    minvu_layers = MinvuLayerRepository(database)
    jobs = JobManager(settings)
    ciren = CirenRuralPropertiesProvider()
    arcgis = ArcGisRestClient(timeout_seconds=25)

    app = FastAPI(
        title="Landfinder Local API",
        version=__version__,
        description="Local-only API for preliminary land intelligence workflows.",
    )
    app.state.settings = settings
    app.state.jobs = jobs
    app.state.territorial = territorial
    app.state.geolocation = geolocation
    app.state.minvu = minvu
    app.state.ipt_catalog = ipt_catalog
    app.state.ciren = ciren
    app.state.mercadolibre_oauth_states = {}
    app.state.mercadolibre_import_history = []

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

    @app.get("/map/providers")
    async def map_providers(_: Annotated[None, Depends(_require_token)]) -> dict:
        providers = [
            {
                "provider_id": "osm",
                "name": "OpenStreetMap",
                "status": "ACTIVE",
                "tile_url_template": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "attribution_url": "https://www.openstreetmap.org/copyright",
                "attribution": "(c) OpenStreetMap contributors",
                "requires_key": False,
            },
            {
                "provider_id": "visicom",
                "name": "Visicom Maps",
                "status": "NOT_CONFIGURED",
                "tile_url_template": None,
                "attribution_url": None,
                "attribution": None,
                "requires_key": True,
                "notes": "No concrete project reference/API contract was found in this repository.",
            },
        ]
        selected = settings.map_provider if settings.map_provider in {"osm", "visicom"} else "osm"
        if selected != "osm" and selected == "visicom":
            selected = "osm"
        return {"selected": selected, "fallback": "osm", "items": providers}

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
                "items": communes_catalog("ALL"),
            }
        aliases = {region["legacy_code"].upper(): region["code"] for region in REGIONS} | {
            region["code"].upper(): region["code"] for region in REGIONS
        }
        canonical_code = aliases.get(normalized)
        if not canonical_code:
            raise HTTPException(status_code=404, detail="region_not_found")
        return {
            "region_code": canonical_code,
            "items": communes_catalog(canonical_code),
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

    @app.post("/soil/discover")
    async def discover_soil(
        request: SoilDiscoveryRequest,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        try:
            bbox = tuple(float(value) for value in request.bbox)
            if len(bbox) != 4:
                raise ValueError("bbox must contain xmin,ymin,xmax,ymax")
            result = await ciren.discover(
                region=request.region,
                commune=request.commune,
                bbox=bbox,
                surface_min_m2=request.surface_min_m2,
                surface_max_m2=request.surface_max_m2,
                offset=request.offset,
                limit=request.limit,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "SOURCE_ERROR",
                "source": "ciren_rural_properties",
                "message": _safe_external_error(exc),
                "items": [],
            }
        job_id = f"soil-discovery-{uuid4()}"
        persisted = []
        for raw in result["items"]:
            normalized = normalize_raw_record(raw)
            internal_id = properties.upsert(normalized)
            _stamp_ciren_candidate(database, internal_id, raw)
            source_records.upsert(job_id, _source_record_audit(raw, normalized))
            item = properties.get(internal_id)
            if item:
                persisted.append(item)
        return {
            "status": "OK",
            "mode": "DESCUBRIR_SUELO",
            "candidate_type": "CADASTRAL_CANDIDATE",
            "job_id": job_id,
            "source": result["source"],
            "service_url": result["service_url"],
            "layers": result["layers"],
            "items": persisted,
            "count": len(persisted),
            "limit": request.limit,
            "offset": request.offset,
            "only_inside_urban_limit": request.only_inside_urban_limit,
        }

    @app.post("/properties")
    async def create_manual_property(
        request: ManualPropertyCreate,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        internal_id = properties.create_manual(request.model_dump())
        item = properties.get(internal_id)
        return {"status": "created", "property": item}

    @app.get("/properties/{property_id}")
    async def get_property(property_id: str, _: Annotated[None, Depends(_require_token)]) -> dict:
        item = properties.get(property_id)
        if not item:
            raise HTTPException(status_code=404, detail="property_not_found")
        return item

    @app.post("/geocode")
    async def geocode(
        request: GeocodeRequest,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        resolution = await geolocation.resolve_request(
            "preview",
            GeocodingRequest(**request.model_dump()),
            persist=False,
        )
        return resolution.as_dict()

    @app.post("/properties/{property_id}/location/resolve")
    async def resolve_property_location(
        property_id: str,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        try:
            return (await geolocation.resolve_property(property_id)).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="property_not_found") from exc

    @app.put("/properties/{property_id}/location")
    async def update_property_location(
        property_id: str,
        update: PropertyLocationUpdate,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        try:
            resolution = await geolocation.assign_manual(
                property_id,
                latitude=update.latitude,
                longitude=update.longitude,
                address=update.address,
                region=update.region,
                commune=update.commune,
                precision=update.location_precision,
            )
            return resolution.as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="property_not_found") from exc

    @app.get("/properties/{property_id}/diagnostics")
    async def property_diagnostics(
        property_id: str,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        item = properties.get(property_id)
        if not item:
            raise HTTPException(status_code=404, detail="property_not_found")
        territory = territorial.summary(property_id)
        return {
            "property_id": property_id,
            "datos_originales": item.get("source_records", []),
            "datos_normalizados": item,
            "ubicacion": {
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "location_source": item.get("location_source") or item.get("geocoding_source"),
                "location_method": item.get("location_method"),
                "location_confidence": item.get("geocoding_confidence"),
                "location_precision": item.get("location_precision"),
                "geocoded_at": item.get("geocoded_at"),
                "history": item.get("location_history", []),
            },
            "capas_minvu_consultadas": minvu_layers.list(limit=500),
            "respuestas_territoriales": {
                "evidence": territory.get("evidence", []),
                "data_provenance": territory.get("data_provenance", []),
                "geometry_metrics": territory.get("geometry_metrics"),
            },
            "criterios_evaluados": item.get("territorial_criteria", []),
            "clasificacion_final": item.get("territorial_status"),
            "errores_advertencias": errors.list_recent(),
        }

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

    @app.post("/properties/{property_id}/territory/evaluate")
    async def evaluate_property_territory(
        property_id: str,
        _: Annotated[None, Depends(_require_token)],
        force_refresh: bool = False,
    ) -> dict:
        try:
            minvu_result = await territorial.refresh_property(property_id, force_refresh=force_refresh)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="property_not_found") from exc
        property_record = properties.get(property_id)
        if not property_record:
            raise HTTPException(status_code=404, detail="property_not_found")
        environmental = await _evaluate_environmental_water_access(property_record, arcgis)
        status = _combined_territorial_status(minvu_result, environmental)
        summary = {
            **(minvu_result.get("preliminary_assessment") or {}),
            "status": status,
            "mma": environmental["mma"],
            "dga": environmental["dga"],
            "mop": environmental["mop"],
            "evidence": environmental["evidence"],
            "disclaimer": (
                "Esta evaluación es preliminar y no reemplaza certificados, "
                "permisos ni análisis normativo oficial."
            ),
        }
        properties.update_territorial_status(property_id, status=status, summary=summary)
        return {**territorial.summary(property_id), "preliminary_assessment": summary}

    @app.get("/gis/minvu/services")
    async def minvu_services(_: Annotated[None, Depends(_require_token)]) -> dict:
        try:
            services = await minvu.discover_services("IPT")
        except Exception as exc:  # noqa: BLE001
            return _minvu_unavailable(exc, services=[])
        return {"source": "IDE MINVU ArcGIS REST", "status": "OK", "services": services}

    @app.get("/gis/minvu/ipt/catalog")
    async def minvu_ipt_catalog(
        _: Annotated[None, Depends(_require_token)],
        region: str | None = None,
        force_refresh: bool = False,
    ) -> dict:
        try:
            payload = await ipt_catalog.build_catalog(
                region_hint=region,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # noqa: BLE001
            return _minvu_unavailable(exc, services=[])
        payload.setdefault("status", "OK")
        return payload

    @app.get("/gis/minvu/layer-audit")
    async def minvu_layer_audit(
        _: Annotated[None, Depends(_require_token)],
        region: str | None = None,
        include_feature_counts: bool = False,
        force_refresh: bool = False,
    ) -> dict:
        try:
            audit = await ipt_catalog.layer_audit(
                region_hint=region,
                include_feature_counts=include_feature_counts,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # noqa: BLE001
            return _minvu_unavailable(exc, layers=minvu_layers.list(limit=500))
        _register_minvu_layers(minvu_layers, audit)
        audit.setdefault("status", "OK")
        return audit

    @app.get("/gis/minvu/layers")
    async def minvu_registered_layers(
        _: Annotated[None, Depends(_require_token)],
        refresh: bool = False,
        region: str | None = None,
        discover_catalog: bool = False,
    ) -> dict:
        if refresh:
            try:
                await _refresh_core_minvu_layers(minvu_layers, minvu)
                if discover_catalog:
                    audit = await ipt_catalog.layer_audit(region_hint=region, force_refresh=True)
                    _register_minvu_layers(minvu_layers, audit)
            except Exception as exc:  # noqa: BLE001
                return _minvu_unavailable(exc, items=minvu_layers.list(limit=500))
        return {"status": "OK", "items": minvu_layers.list(limit=500)}

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
            "mercadolibre_client_id": settings.mercadolibre_client_id,
            "mercadolibre_redirect_uri": settings.mercadolibre_redirect_uri,
            "mercadolibre_partner_seller_ids": settings.mercadolibre_partner_seller_ids,
            "mercadolibre_partner_sellers_count": len(
                _split_csv(settings.mercadolibre_partner_seller_ids)
            ),
            "mercadolibre_marketplace_global_enabled": (
                settings.mercadolibre_marketplace_global_enabled
            ),
            "has_mercadolibre_client_id": bool(settings.mercadolibre_client_id),
            "has_mercadolibre_client_secret": bool(settings.mercadolibre_client_secret),
            "has_mercadolibre_redirect_uri": bool(settings.mercadolibre_redirect_uri),
            "has_mercadolibre_access_token": bool(settings.mercadolibre_access_token),
            "has_mercadolibre_refresh_token": bool(settings.mercadolibre_refresh_token),
            "mercadolibre_access_token_expires_at": (settings.mercadolibre_access_token_expires_at),
            "reference_property_id": settings.reference_property_id,
            "map_provider": settings.map_provider,
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
        if update.mercadolibre_client_id:
            settings.mercadolibre_client_id = update.mercadolibre_client_id
            write_windows_secret("MERCADOLIBRE_CLIENT_ID", update.mercadolibre_client_id)
        if update.mercadolibre_client_secret:
            settings.mercadolibre_client_secret = update.mercadolibre_client_secret
            write_windows_secret(
                "MERCADOLIBRE_CLIENT_SECRET",
                update.mercadolibre_client_secret,
            )
        if update.mercadolibre_redirect_uri:
            settings.mercadolibre_redirect_uri = update.mercadolibre_redirect_uri
            write_windows_secret(
                "MERCADOLIBRE_REDIRECT_URI",
                update.mercadolibre_redirect_uri,
            )
        if update.mercadolibre_partner_seller_ids is not None:
            settings.mercadolibre_partner_seller_ids = update.mercadolibre_partner_seller_ids
            write_windows_secret(
                "MERCADOLIBRE_PARTNER_SELLER_IDS",
                update.mercadolibre_partner_seller_ids,
            )
        if update.mercadolibre_marketplace_global_enabled is not None:
            settings.mercadolibre_marketplace_global_enabled = (
                update.mercadolibre_marketplace_global_enabled
            )
        if update.mercadolibre_access_token:
            settings.mercadolibre_access_token = update.mercadolibre_access_token
            write_windows_secret("MERCADOLIBRE_ACCESS_TOKEN", update.mercadolibre_access_token)
        if update.mercadolibre_refresh_token:
            settings.mercadolibre_refresh_token = update.mercadolibre_refresh_token
            write_windows_secret(
                "MERCADOLIBRE_REFRESH_TOKEN",
                update.mercadolibre_refresh_token,
            )
        if update.mercadolibre_access_token_expires_at:
            settings.mercadolibre_access_token_expires_at = (
                update.mercadolibre_access_token_expires_at
            )
            write_windows_secret(
                "MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT",
                update.mercadolibre_access_token_expires_at,
            )
        if update.reference_property_id:
            settings.reference_property_id = update.reference_property_id
        if update.map_provider is not None:
            settings.map_provider = update.map_provider.strip().lower() or "osm"
        _sync_environment(settings)
        return await get_settings(None)

    @app.get("/oauth/mercadolibre/authorize")
    async def mercadolibre_authorize(
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        client_id = (settings.mercadolibre_client_id or "").strip()
        redirect_uri = _normalize_mercadolibre_redirect_uri(
            (settings.mercadolibre_redirect_uri or "").strip()
        )
        if not client_id:
            raise HTTPException(status_code=400, detail="missing_mercadolibre_client_id")
        if not _is_valid_redirect_uri(redirect_uri):
            raise HTTPException(status_code=400, detail="missing_or_invalid_mercadolibre_redirect_uri")
        state = secrets.token_urlsafe(32)
        app.state.mercadolibre_oauth_states[state] = redirect_uri
        authorization_url = "https://auth.mercadolibre.cl/authorization?" + urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return {"authorization_url": authorization_url}

    @app.get("/oauth/mercadolibre/callback")
    async def mercadolibre_callback(code: str | None = None, state: str | None = None) -> HTMLResponse:
        redirect_uri = app.state.mercadolibre_oauth_states.pop(state or "", None)
        if not code or not state or not redirect_uri:
            return _oauth_html("No se pudo completar la autorizacion de Mercado Libre.", 400)
        client_id = (settings.mercadolibre_client_id or "").strip()
        client_secret = (settings.mercadolibre_client_secret or "").strip()
        if not client_id:
            return _oauth_html("Mercado Libre no esta configurado en Landfinder.", 400)
        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if client_secret:
            payload["client_secret"] = client_secret
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    "https://api.mercadolibre.com/oauth/token",
                    data=payload,
                )
            if response.status_code >= 400:
                return _oauth_html("Mercado Libre rechazo la autorizacion.", 400)
            decoded = response.json()
        except (httpx.HTTPError, ValueError):
            return _oauth_html("No se pudo contactar Mercado Libre para completar OAuth.", 502)
        access_token = str(decoded.get("access_token") or "")
        refresh_token = str(decoded.get("refresh_token") or "")
        expires_in = int(decoded.get("expires_in") or 0)
        if not access_token or not refresh_token or expires_in <= 0:
            return _oauth_html("Mercado Libre no entrego tokens completos.", 400)
        settings.mercadolibre_access_token = access_token
        settings.mercadolibre_refresh_token = refresh_token
        settings.mercadolibre_access_token_expires_at = (
            (utc_now() + timedelta(seconds=expires_in)).isoformat()
        )
        write_windows_secret("MERCADOLIBRE_ACCESS_TOKEN", access_token)
        write_windows_secret("MERCADOLIBRE_REFRESH_TOKEN", refresh_token)
        write_windows_secret(
            "MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT",
            settings.mercadolibre_access_token_expires_at,
        )
        _sync_environment(settings)
        return _oauth_html("Mercado Libre conectado correctamente. Puedes volver a Landfinder.")

    @app.get("/oauth/mercadolibre/diagnostics")
    async def mercadolibre_diagnostics(
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        token = (settings.mercadolibre_access_token or "").strip()
        app_id = (settings.mercadolibre_client_id or "").strip()
        if not token or not app_id:
            raise HTTPException(status_code=400, detail="mercadolibre_not_configured")
        async with httpx.AsyncClient(timeout=20) as client:
            user_status, user_body = await _mercadolibre_get(client, "/users/me", token)
            app_status, app_body = await _mercadolibre_get(
                client,
                f"/applications/{app_id}",
                token,
            )
            grants_status, grants_body = await _mercadolibre_get(
                client,
                f"/applications/{app_id}/grants",
                token,
            )
        app_scopes = _extract_scopes(app_body)
        grant_scopes = _extract_scopes(grants_body)
        return {
            "user": {
                "http_status": user_status,
                "user_id": user_body.get("id") if isinstance(user_body, dict) else None,
                "site_id": user_body.get("site_id") if isinstance(user_body, dict) else None,
                "status": user_body.get("status") if isinstance(user_body, dict) else None,
                "user_type": user_body.get("user_type") if isinstance(user_body, dict) else None,
                "tags": user_body.get("tags") if isinstance(user_body, dict) else None,
            },
            "application": {
                "http_status": app_status,
                "active": app_body.get("active") if isinstance(app_body, dict) else None,
                "site_id": app_body.get("site_id") if isinstance(app_body, dict) else None,
                "sandbox_mode": app_body.get("sandbox_mode") if isinstance(app_body, dict) else None,
                "certification_status": (
                    app_body.get("certification_status") if isinstance(app_body, dict) else None
                ),
                "scopes": app_scopes,
                "has_mercadopago_scope": any(
                    str(scope).startswith("urn:mp:") for scope in app_scopes
                ),
            },
            "grants": {
                "http_status": grants_status,
                "scopes": grant_scopes,
                "has_read": "read" in grant_scopes,
                "has_offline_access": "offline_access" in grant_scopes,
            },
            "marketplace_global": {
                "enabled": settings.mercadolibre_marketplace_global_enabled,
                "capability": (
                    "ENABLED"
                    if settings.mercadolibre_marketplace_global_enabled
                    else "UNAVAILABLE_FOR_APP"
                ),
            },
        }

    @app.post("/mercadolibre/import/analyze")
    async def analyze_mercadolibre_import(
        request: MercadoLibreImportAnalyzeRequest,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        return await _analyze_mercadolibre_items(settings, request.input_text)

    @app.post("/mercadolibre/import")
    async def import_mercadolibre_items(
        request: MercadoLibreImportRequest,
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        analysis = await _analyze_mercadolibre_items(settings, request.input_text)
        include_types = {item.upper() for item in request.include_types}
        job_id = f"manual-ml-{uuid4()}"
        imported = 0
        updated = 0
        existing_unchanged = 0
        discarded = 0
        imported_items = []
        imported_rows = []
        imported_at = utc_now().isoformat()
        for row in analysis["items"]:
            if row["type"] not in include_types or not row.get("raw_item"):
                discarded += 1
                continue
            raw = mercadolibre_item_to_raw(row["raw_item"])
            _stamp_mercadolibre_import(raw, row, imported_at)
            normalized = normalize_raw_record(raw)
            existed = _property_exists(database, raw.source_id, raw.external_id)
            internal_id = properties.upsert(normalized)
            source_records.upsert(job_id, _source_record_audit(raw, normalized))
            imported_items.append(
                {
                    "item_id": raw.external_id,
                    "internal_id": internal_id,
                    "updated": existed,
                }
            )
            imported_rows.append(row)
            if existed:
                updated += 1
            else:
                imported += 1
        seller_discovery = _mercadolibre_seller_discovery(settings, imported_rows, imported_at)
        _remember_mercadolibre_sellers(settings, imported_rows)
        summary = {
            "job_id": job_id,
            "entries": analysis["entries"],
            "ids_detected": analysis["ids_detected"],
            "new": imported,
            "updated": updated,
            "existing_unchanged": existing_unchanged,
            "discarded": discarded,
            "new_sellers": len([seller for seller in seller_discovery if seller["is_new"]]),
            "seller_discovery": seller_discovery,
            "items": imported_items,
        }
        app.state.mercadolibre_import_history.insert(0, {**summary, "imported_at": imported_at})
        app.state.mercadolibre_import_history = app.state.mercadolibre_import_history[:10]
        return summary

    @app.get("/mercadolibre/import/history")
    async def mercadolibre_import_history(
        _: Annotated[None, Depends(_require_token)],
    ) -> dict:
        return {"items": app.state.mercadolibre_import_history}

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


def _minvu_unavailable(exc: Exception, **payload: object) -> dict:
    return {
        "source": "IDE MINVU ArcGIS REST",
        "status": "UNAVAILABLE",
        "message": f"{type(exc).__name__}: {_safe_external_error(exc)}",
        **payload,
    }


def _safe_external_error(exc: Exception) -> str:
    text = str(exc)
    if len(text) > 240:
        text = f"{text[:237]}..."
    return text or "external service unavailable"


def _is_valid_redirect_uri(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://127.0.0.1")


def _normalize_mercadolibre_redirect_uri(value: str) -> str:
    if not value:
        return value
    if value.endswith("/"):
        value = value[:-1]
    if value.endswith("/oauth/mercadolibre/callback"):
        return value
    return f"{value}/oauth/mercadolibre/callback"


def _oauth_html(message: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<html><body><p>{message}</p></body></html>",
        status_code=status_code,
    )


async def _mercadolibre_get(
    client: httpx.AsyncClient,
    path: str,
    token: str,
) -> tuple[int, dict | list | str]:
    response = await client.get(
        f"https://api.mercadolibre.com{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text[:240]


def _extract_scopes(payload: object) -> list[str]:
    if isinstance(payload, dict):
        scopes = payload.get("scopes") or payload.get("site_scopes") or payload.get("scope")
        if isinstance(scopes, str):
            return [item for item in scopes.replace(",", " ").split() if item]
        if isinstance(scopes, list):
            return [str(item) for item in scopes]
        text = json.dumps(payload, ensure_ascii=False).lower()
        found = []
        for scope in ("read", "offline_access", "write"):
            if scope in text:
                found.append(scope)
        return found
    if isinstance(payload, list):
        text = json.dumps(payload, ensure_ascii=False).lower()
        return [scope for scope in ("read", "offline_access", "write") if scope in text]
    return []


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


async def _analyze_mercadolibre_items(settings: Settings, input_text: str) -> dict:
    ids = _extract_mercadolibre_item_ids(input_text)
    token = await MercadoLibreRealEstateConnector()._access_token()
    if not token:
        raise HTTPException(status_code=400, detail="mercadolibre_not_configured")
    connector = MercadoLibreRealEstateConnector()
    categories = await connector._land_category_ids(token, SearchQuery())
    category_ids = {category["id"] for category in categories}
    category_by_id = {category["id"]: category for category in categories}
    items, item_errors, item_diagnostics = await _fetch_mercadolibre_items(connector, token, ids)
    current_sellers = set(_split_csv(settings.mercadolibre_partner_seller_ids))
    rows = []
    seen_sellers = set()
    seller_profiles: dict[str, tuple[dict | None, str, int | None]] = {}
    seller_searches: dict[str, tuple[int | None, str]] = {}
    for item_id in ids:
        item = items.get(item_id)
        if not item:
            rows.append(
                _import_error_row(
                    item_id,
                    item_errors.get(item_id, "No encontrado/API error"),
                    item_diagnostics.get(item_id, {}).get("item_http"),
                )
            )
            continue
        category_id = str(item.get("category_id") or "")
        category = category_by_id.get(category_id, {"id": category_id, "name": category_id, "path": category_id})
        seller_id = str(item.get("seller_id") or "").strip()
        official_store_id = item.get("official_store_id")
        if seller_id and seller_id not in seller_profiles:
            seller_profiles[seller_id] = await _fetch_mercadolibre_seller(connector, token, seller_id)
        seller_profile, seller_error, user_http = seller_profiles.get(seller_id, ({}, "", None))
        if seller_id and seller_id not in seller_searches:
            seller_searches[seller_id] = await _fetch_mercadolibre_seller_search_status(
                connector,
                token,
                seller_id,
            )
        seller_search_http, seller_search_error = seller_searches.get(seller_id, (None, ""))
        seller_expansion_status = _seller_expansion_status(seller_search_http)
        enriched_item = {
            **item,
            "landfinder_category": category,
            "landfinder_seller": seller_profile or {},
            "landfinder_api_diagnostics": item_diagnostics.get(item_id, {}),
            "landfinder_seller_expansion": {
                "http": seller_search_http,
                "status": seller_expansion_status,
                "error": seller_search_error,
            },
        }
        raw = mercadolibre_item_to_raw(enriched_item)
        normalized = normalize_raw_record(raw)
        landfinder = raw.raw_payload.get("landfinder", {})
        land_type = (
            str(landfinder.get("property_land_type") or "UNKNOWN")
            if isinstance(landfinder, dict)
            else "UNKNOWN"
        )
        if seller_id:
            seen_sellers.add(seller_id)
        in_land_category = not category_ids or category_id in category_ids
        importable = in_land_category and land_type in {
            "VACANT_LAND",
            "LAND_WITH_STRUCTURE",
            "UNKNOWN",
        }
        rows.append(
            {
                "status": "ok" if importable else "discarded",
                "item_status": "OK",
                "item_http": item_diagnostics.get(item_id, {}).get("item_http"),
                "item_id": item_id,
                "title": raw.title,
                "type": land_type,
                "price": raw.price_raw,
                "surface": raw.area_raw,
                "surface_m2": str(normalized.gross_area_m2) if normalized.gross_area_m2 else None,
                "built_surface_m2": landfinder.get("built_surface_m2")
                if isinstance(landfinder, dict)
                else None,
                "region": normalized.region or raw.region_raw,
                "commune": normalized.commune or raw.commune_raw,
                "seller_id": seller_id or None,
                "official_store_id": official_store_id,
                "seller_nickname": (
                    seller_profile.get("nickname")
                    if isinstance(seller_profile, dict)
                    else item.get("seller_nickname")
                ),
                "seller_status": (
                    seller_profile.get("status")
                    if isinstance(seller_profile, dict)
                    else None
                ),
                "seller_site_id": (
                    seller_profile.get("site_id")
                    if isinstance(seller_profile, dict)
                    else None
                ),
                "user_http": user_http,
                "user_error": seller_error,
                "seller_search_http": seller_search_http,
                "seller_expansion_status": seller_expansion_status,
                "seller_search_error": seller_search_error,
                "bulk_http": item_diagnostics.get(item_id, {}).get("bulk_http"),
                "bulk_compare": item_diagnostics.get(item_id, {}).get("bulk_compare"),
                "category_id": category_id,
                "permalink": raw.canonical_url,
                "result": "Listo" if importable else "Descartado",
                "raw_item": enriched_item,
            }
        )
    return {
        "entries": _count_entries(input_text),
        "ids_detected": len(ids),
        "duplicates": max(0, _count_id_mentions(input_text) - len(ids)),
        "new_sellers": len(seen_sellers - current_sellers),
        "items": rows,
    }


def _extract_mercadolibre_item_ids(text: str) -> list[str]:
    seen = set()
    ids = []
    for match in re.finditer(r"MLC-?\d+", text, flags=re.IGNORECASE):
        item_id = match.group(0).upper().replace("-", "")
        if item_id not in seen:
            ids.append(item_id)
            seen.add(item_id)
    return ids


def _count_id_mentions(text: str) -> int:
    return len(re.findall(r"MLC-?\d+", text, flags=re.IGNORECASE))


def _count_entries(text: str) -> int:
    return len([item for item in re.split(r"[\n,]+", text) if item.strip()])


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def _fetch_mercadolibre_items(
    connector: MercadoLibreRealEstateConnector,
    token: str,
    item_ids: list[str],
) -> tuple[dict[str, dict], dict[str, str], dict[str, dict[str, object]]]:
    items: dict[str, dict] = {}
    errors: dict[str, str] = {}
    diagnostics: dict[str, dict[str, object]] = {}
    for item_id in item_ids:
        item, error, http_status = await _fetch_mercadolibre_item(connector, token, item_id)
        diagnostics[item_id] = {"item_http": http_status}
        if item:
            items[item_id] = item
        else:
            errors[item_id] = error
    valid_ids = [item_id for item_id in item_ids if item_id in items]
    if not valid_ids:
        return items, errors, diagnostics
    bulk_items, bulk_errors, bulk_statuses = await _fetch_mercadolibre_items_bulk(
        connector,
        token,
        valid_ids,
    )
    for item_id in valid_ids:
        diagnostics.setdefault(item_id, {})["bulk_http"] = bulk_statuses.get(item_id)
        if item_id in bulk_items:
            diagnostics[item_id]["bulk_compare"] = _compare_mercadolibre_item(
                items[item_id],
                bulk_items[item_id],
            )
        elif item_id in bulk_errors:
            diagnostics[item_id]["bulk_error"] = bulk_errors[item_id]
            diagnostics[item_id]["bulk_compare"] = "FALLBACK_INDIVIDUAL"
    return items, errors, diagnostics


async def _fetch_mercadolibre_items_bulk(
    connector: MercadoLibreRealEstateConnector,
    token: str,
    item_ids: list[str],
) -> tuple[dict[str, dict], dict[str, str], dict[str, int | None]]:
    items: dict[str, dict] = {}
    errors: dict[str, str] = {}
    statuses: dict[str, int | None] = {}
    for batch in _chunks(item_ids, 20):
        response = await connector._bulk_items(token, batch)
        if response.status_code >= 400:
            error = f"HTTP {response.status_code}: {_safe_external_response(response)}"
            for item_id in batch:
                statuses[item_id] = response.status_code
                errors[item_id] = error
            continue
        try:
            entries = response.json()
        except ValueError:
            entries = []
        if not isinstance(entries, list):
            entries = []
        handled = set()
        for item_id, entry in zip(batch, entries):
            code = int(entry.get("code") or 0) if isinstance(entry, dict) else 0
            body = entry.get("body") if isinstance(entry, dict) else None
            body_item_id = str(body.get("id") or item_id) if isinstance(body, dict) else item_id
            handled.add(item_id)
            statuses[item_id] = code or response.status_code
            if code == 200 and isinstance(body, dict) and body_item_id:
                items[body_item_id] = body
                continue
            errors[item_id] = f"HTTP {code or response.status_code}"
        for item_id in batch:
            if item_id in handled:
                continue
            statuses[item_id] = response.status_code
            errors[item_id] = "No encontrado/API error"
    return items, errors, statuses


async def _fetch_mercadolibre_item(
    connector: MercadoLibreRealEstateConnector,
    token: str,
    item_id: str,
) -> tuple[dict | None, str, int | None]:
    headers = {"Authorization": f"Bearer {token}"}
    params = {"include_attributes": "all"}
    if connector._client is not None:
        response = await connector._client.get(f"/items/{item_id}", params=params, headers=headers)
    else:
        async with httpx.AsyncClient(base_url=connector.base_url, headers=headers, timeout=20) as client:
            response = await client.get(f"/items/{item_id}", params=params)
    if response.status_code >= 400:
        return None, f"HTTP {response.status_code}: {_safe_external_response(response)}", response.status_code
    return response.json(), "", response.status_code


async def _fetch_mercadolibre_seller(
    connector: MercadoLibreRealEstateConnector,
    token: str,
    seller_id: str,
) -> tuple[dict | None, str, int | None]:
    headers = {"Authorization": f"Bearer {token}"}
    if connector._client is not None:
        response = await connector._client.get(f"/users/{seller_id}", headers=headers)
    else:
        async with httpx.AsyncClient(base_url=connector.base_url, headers=headers, timeout=20) as client:
            response = await client.get(f"/users/{seller_id}")
    if response.status_code >= 400:
        return None, f"HTTP {response.status_code}: {_safe_external_response(response)}", response.status_code
    return response.json(), "", response.status_code


async def _fetch_mercadolibre_seller_search_status(
    connector: MercadoLibreRealEstateConnector,
    token: str,
    seller_id: str,
) -> tuple[int | None, str]:
    response = await connector._seller_items_search(token=token, seller_id=seller_id, limit=5)
    if response.status_code >= 400:
        return response.status_code, _safe_external_response(response)
    return response.status_code, ""


def _import_error_row(item_id: str, message: str, item_http: object = None) -> dict:
    return {
        "status": "error",
        "item_status": "ERROR",
        "item_http": item_http,
        "item_id": item_id,
        "title": None,
        "type": None,
        "price": None,
        "surface": None,
        "surface_m2": None,
        "built_surface_m2": None,
        "region": None,
        "commune": None,
        "seller_id": None,
        "official_store_id": None,
        "seller_nickname": None,
        "seller_status": None,
        "seller_site_id": None,
        "user_http": None,
        "user_error": None,
        "seller_search_http": None,
        "seller_expansion_status": None,
        "seller_search_error": None,
        "bulk_http": None,
        "bulk_compare": None,
        "category_id": None,
        "permalink": None,
        "result": message,
    }


def _remember_mercadolibre_sellers(settings: Settings, rows: list[dict]) -> None:
    existing = _split_csv(settings.mercadolibre_partner_seller_ids)
    merged = list(existing)
    seen = set(existing)
    for row in rows:
        seller_id = str(row.get("seller_id") or "").strip()
        if seller_id and seller_id not in seen:
            merged.append(seller_id)
            seen.add(seller_id)
    value = ",".join(merged)
    settings.mercadolibre_partner_seller_ids = value
    os.environ["MERCADOLIBRE_PARTNER_SELLER_IDS"] = value
    write_windows_secret("MERCADOLIBRE_PARTNER_SELLER_IDS", value)


def _mercadolibre_seller_discovery(
    settings: Settings,
    rows: list[dict],
    timestamp: str,
) -> list[dict]:
    existing = set(_split_csv(settings.mercadolibre_partner_seller_ids))
    sellers = []
    seen = set()
    for row in rows:
        seller_id = str(row.get("seller_id") or "").strip()
        if not seller_id or seller_id in seen:
            continue
        seen.add(seller_id)
        sellers.append(
            {
                "seller_id": seller_id,
                "nickname": row.get("seller_nickname"),
                "status": row.get("seller_status"),
                "site_id": row.get("seller_site_id"),
                "official_store_id": row.get("official_store_id"),
                "source_item_id": row.get("item_id"),
                "added_at": timestamp if seller_id not in existing else None,
                "last_seen_at": timestamp,
                "is_new": seller_id not in existing,
            }
        )
    return sellers


def _stamp_mercadolibre_import(raw: object, row: dict, imported_at: str) -> None:
    landfinder = raw.raw_payload.setdefault("landfinder", {})
    if not isinstance(landfinder, dict):
        return
    seller_id = str(row.get("seller_id") or "").strip()
    landfinder.update(
        {
            "imported_at": imported_at,
            "item_id": row.get("item_id"),
            "source_item_id": row.get("item_id"),
            "seller_id": seller_id or None,
            "official_store_id": row.get("official_store_id"),
            "seller_nickname": row.get("seller_nickname"),
            "seller_status": row.get("seller_status"),
            "seller_site_id": row.get("seller_site_id"),
            "seller_last_seen_at": imported_at if seller_id else None,
            "seller_registry": {
                "seller_id": seller_id or None,
                "nickname": row.get("seller_nickname"),
                "status": row.get("seller_status"),
                "site_id": row.get("seller_site_id"),
            },
            "seller_expansion": {
                "http": row.get("seller_search_http"),
                "status": row.get("seller_expansion_status"),
                "error": row.get("seller_search_error"),
            },
        }
    )


def _seller_expansion_status(http_status: int | None) -> str:
    if http_status == 200:
        return "OK"
    if http_status == 403:
        return "FORBIDDEN"
    if http_status is None:
        return "UNKNOWN"
    return f"HTTP {http_status}"


def _compare_mercadolibre_item(individual: dict[str, Any], bulk: dict[str, Any]) -> str:
    for key in ("id", "seller_id", "official_store_id", "category_id"):
        if str(individual.get(key) or "") != str(bulk.get(key) or ""):
            return "DIFF"
    return "MATCH"


def _property_exists(database: Database, source_id: str, external_id: str | None) -> bool:
    if not external_id:
        return False
    with database.transaction() as connection:
        row = connection.execute(
            """
            SELECT 1 FROM property_source_records
            WHERE source = ? AND external_id = ?
            LIMIT 1
            """,
            (source_id, external_id),
        ).fetchone()
    return bool(row)


def _source_record_audit(raw: object, normalized: object) -> dict:
    landfinder = raw.raw_payload.get("landfinder", {})
    land_type = (
        str(landfinder.get("property_land_type") or "UNKNOWN")
        if isinstance(landfinder, dict)
        else "UNKNOWN"
    )
    candidate_type = (
        str(landfinder.get("candidate_type") or "")
        if isinstance(landfinder, dict)
        else ""
    )
    automatic_classification = candidate_type or land_type
    return {
        "source": raw.source_id,
        "source_type": raw.source_type,
        "external_id": raw.external_id,
        "title": raw.title,
        "description": raw.description,
        "publication_date": raw.publication_date.isoformat() if raw.publication_date else None,
        "region": normalized.region,
        "commune": normalized.commune,
        "property_region": normalized.region,
        "property_commune": normalized.commune,
        "property_address": normalized.address,
        "amount": normalized.price_amount,
        "currency": normalized.price_currency,
        "amount_raw": raw.price_raw,
        "surface_raw": raw.area_raw,
        "surface_m2": normalized.gross_area_m2,
        "surface_source": landfinder.get("surface_source")
        if isinstance(landfinder, dict)
        else None,
        "surface_confidence": 0.9
        if isinstance(landfinder, dict) and landfinder.get("surface_source") == "ATTRIBUTE"
        else 0.75
        if isinstance(landfinder, dict) and landfinder.get("surface_source") == "GEOMETRY_CALCULATED"
        else 0,
        "source_url": raw.canonical_url,
        "detail_fetched": True,
        "fields_extracted": ["title", "url", "price", "surface"],
        "fields_missing": [],
        "raw_payload": raw.raw_payload,
        "automatic_classification": automatic_classification,
        "automatic_confidence": 0.8 if automatic_classification != "UNKNOWN" else 0.4,
        "classification_reason": (
            "CIREN cadastral candidate; not a public sale offer."
            if candidate_type
            else "MercadoLibre manual import classification."
        ),
    }


def _safe_external_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    return str(payload).replace("\n", " ")[:180]


MMA_PROTECTED_AREAS_SERVICE = (
    "https://arcgis.mma.gob.cl/server/rest/services/SIMBIO/SIMBIO_AP/FeatureServer"
)
MMA_WETLANDS_SERVICE = (
    "https://arcgis.mma.gob.cl/server/rest/services/SIMBIO/SIMBIO_HUMEDALES/FeatureServer"
)
DGA_RESTRICTIONS_SERVICE = (
    "https://rest-sit.mop.gob.cl/arcgis/rest/services/SNIA/SNIA_Prohibiciones/MapServer"
)
DGA_WATER_RIGHTS_SERVICE = (
    "https://rest-sit.mop.gob.cl/arcgis/rest/services/SNIA/SNIA_DerechoAprovechamiento/MapServer"
)
MOP_ROADS_SERVICE = (
    "https://rest-sit.mop.gob.cl/arcgis/rest/services/VIALIDAD/Red_Vial_Chile/MapServer"
)


def _stamp_ciren_candidate(database: Database, internal_id: str, raw: object) -> None:
    landfinder = raw.raw_payload.get("landfinder", {}) if isinstance(raw.raw_payload, dict) else {}
    if not isinstance(landfinder, dict):
        return
    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE property_candidates
            SET listing_status = 'unknown',
                seller_type = 'unknown',
                source_epsg = ?,
                normalized_epsg = ?,
                source_region = COALESCE(?, source_region),
                source_commune = COALESCE(?, source_commune),
                manual_notes = COALESCE(manual_notes, ?),
                updated_at = ?
            WHERE internal_id = ?
            """,
            (
                landfinder.get("source_epsg") or 4326,
                landfinder.get("normalized_epsg") or 4326,
                raw.region_raw,
                raw.commune_raw,
                "CANDIDATO TERRITORIAL; CIREN no implica oferta en venta.",
                utc_now().isoformat(),
                internal_id,
            ),
        )


async def _evaluate_environmental_water_access(
    property_record: dict[str, Any],
    arcgis: ArcGisRestClient,
) -> dict[str, Any]:
    geometry = _property_geojson(property_record)
    bbox = _property_bbox(geometry, property_record)
    if not bbox:
        evidence = [
            query_evidence(
                criterion="geometry",
                source="Landfinder",
                endpoint="property_candidates.parcel_geometry",
                layer_id=None,
                query_status="NO_GEOMETRY",
                result="SIN_INFORMACION",
                feature_ids=[],
                notes="No hay geometría de predio ni punto representativo.",
            )
        ]
        return {
            "mma": {"protected_area": "SIN INFORMACION", "wetland": "SIN INFORMACION"},
            "dga": {"restriction": "SIN INFORMACION", "water_rights_nearby": "SIN INFORMACION"},
            "mop": {"distance_to_mop_road_m": None, "status": "SIN INFORMACION"},
            "evidence": evidence,
        }
    protected = await _arcgis_intersection_check(
        arcgis,
        source="MMA SIMBIO",
        service_url=MMA_PROTECTED_AREAS_SERVICE,
        criterion="protected_area",
        bbox=bbox,
        max_layers=3,
    )
    wetland = await _arcgis_intersection_check(
        arcgis,
        source="MMA SIMBIO",
        service_url=MMA_WETLANDS_SERVICE,
        criterion="wetland",
        bbox=bbox,
        max_layers=3,
    )
    restriction = await _arcgis_intersection_check(
        arcgis,
        source="DGA SNIA",
        service_url=DGA_RESTRICTIONS_SERVICE,
        criterion="dga_restriction",
        bbox=bbox,
        max_layers=5,
    )
    water_rights = await _arcgis_intersection_check(
        arcgis,
        source="DGA SNIA",
        service_url=DGA_WATER_RIGHTS_SERVICE,
        criterion="dga_water_rights_nearby",
        bbox=_expanded_bbox(bbox, 0.02),
        max_layers=5,
    )
    road = await _nearest_mop_road(arcgis, property_record, bbox)
    evidence = [
        *protected["evidence"],
        *wetland["evidence"],
        *restriction["evidence"],
        *water_rights["evidence"],
        *road["evidence"],
    ]
    return {
        "mma": {
            "protected_area": protected["status"],
            "wetland": wetland["status"],
        },
        "dga": {
            "restriction": restriction["status"],
            "water_rights_nearby": water_rights["status"],
        },
        "mop": {
            "distance_to_mop_road_m": road.get("distance_to_mop_road_m"),
            "status": road.get("status"),
            "disclaimer": "Distancia territorial; no acredita acceso jurídico o servidumbre.",
        },
        "evidence": evidence,
    }


async def _arcgis_intersection_check(
    arcgis: ArcGisRestClient,
    *,
    source: str,
    service_url: str,
    criterion: str,
    bbox: tuple[float, float, float, float],
    max_layers: int,
) -> dict[str, Any]:
    evidence = []
    try:
        metadata = await arcgis.service_metadata(service_url)
        layers = [layer for layer in metadata.get("layers") or [] if isinstance(layer, dict)]
        layers = layers[:max_layers]
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "SIN INFORMACION",
            "evidence": [
                query_evidence(
                    criterion=criterion,
                    source=source,
                    endpoint=service_url,
                    layer_id=None,
                    query_status="SOURCE_ERROR",
                    result="SIN_INFORMACION",
                    feature_ids=[],
                    notes=_safe_external_error(exc),
                )
            ],
        }
    total = 0
    for layer in layers:
        layer_id = int(layer.get("id") or 0)
        endpoint = f"{service_url.rstrip('/')}/{layer_id}/query"
        try:
            payload = await arcgis.query_layer(
                service_url=service_url,
                layer_id=layer_id,
                bbox=bbox,
                out_fields="OBJECTID,objectid,FID,id,nombre,NOMBRE",
                return_geometry=False,
                limit=25,
            )
            features = payload.get("features") or []
            feature_ids = [_feature_id(feature) for feature in features if isinstance(feature, dict)]
            total += len(features)
            evidence.append(
                query_evidence(
                    criterion=criterion,
                    source=source,
                    endpoint=endpoint,
                    layer_id=layer_id,
                    query_status="OK",
                    result="INTERSECTA" if features else "SIN_COINCIDENCIA",
                    feature_ids=feature_ids,
                    notes=str(layer.get("name") or ""),
                )
            )
        except Exception as exc:  # noqa: BLE001
            evidence.append(
                query_evidence(
                    criterion=criterion,
                    source=source,
                    endpoint=endpoint,
                    layer_id=layer_id,
                    query_status="SOURCE_ERROR",
                    result="SIN_INFORMACION",
                    feature_ids=[],
                    notes=_safe_external_error(exc),
                )
            )
    if total:
        status = "INTERSECTA"
    elif evidence and all(item["query_status"] == "OK" for item in evidence):
        status = "SIN COINCIDENCIA"
    else:
        status = "SIN INFORMACION"
    return {"status": status, "evidence": evidence}


async def _nearest_mop_road(
    arcgis: ArcGisRestClient,
    property_record: dict[str, Any],
    bbox: tuple[float, float, float, float],
) -> dict[str, Any]:
    try:
        metadata = await arcgis.service_metadata(MOP_ROADS_SERVICE)
        layers = [layer for layer in metadata.get("layers") or [] if isinstance(layer, dict)]
        layers = layers[:4]
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "SIN INFORMACION",
            "distance_to_mop_road_m": None,
            "evidence": [
                query_evidence(
                    criterion="mop_road_distance",
                    source="MOP Vialidad",
                    endpoint=MOP_ROADS_SERVICE,
                    layer_id=None,
                    query_status="SOURCE_ERROR",
                    result="SIN_INFORMACION",
                    feature_ids=[],
                    notes=_safe_external_error(exc),
                )
            ],
        }
    point = _representative_point(property_record)
    if point is None:
        return {
            "status": "SIN INFORMACION",
            "distance_to_mop_road_m": None,
            "evidence": [],
        }
    distances = []
    evidence = []
    for layer in layers:
        layer_id = int(layer.get("id") or 0)
        endpoint = f"{MOP_ROADS_SERVICE.rstrip('/')}/{layer_id}/query"
        try:
            payload = await arcgis.query_layer(
                service_url=MOP_ROADS_SERVICE,
                layer_id=layer_id,
                bbox=_expanded_bbox(bbox, 0.03),
                out_fields="OBJECTID,objectid,FID,id",
                return_geometry=True,
                limit=25,
            )
            features = payload.get("features") or []
            for feature in features:
                geometry = _arcgis_feature_to_shape(feature.get("geometry") if isinstance(feature, dict) else None)
                if geometry is not None:
                    distances.append(_distance_m(point, geometry))
            evidence.append(
                query_evidence(
                    criterion="mop_road_distance",
                    source="MOP Vialidad",
                    endpoint=endpoint,
                    layer_id=layer_id,
                    query_status="OK",
                    result="INTERSECTA" if features else "SIN_COINCIDENCIA",
                    feature_ids=[_feature_id(feature) for feature in features if isinstance(feature, dict)],
                    notes=str(layer.get("name") or ""),
                )
            )
        except Exception as exc:  # noqa: BLE001
            evidence.append(
                query_evidence(
                    criterion="mop_road_distance",
                    source="MOP Vialidad",
                    endpoint=endpoint,
                    layer_id=layer_id,
                    query_status="SOURCE_ERROR",
                    result="SIN_INFORMACION",
                    feature_ids=[],
                    notes=_safe_external_error(exc),
                )
            )
    if distances:
        return {
            "status": "OK",
            "distance_to_mop_road_m": round(min(distances), 1),
            "evidence": evidence,
        }
    if evidence and all(item["query_status"] == "OK" for item in evidence):
        return {"status": "SIN COINCIDENCIA", "distance_to_mop_road_m": None, "evidence": evidence}
    return {"status": "SIN INFORMACION", "distance_to_mop_road_m": None, "evidence": evidence}


def _combined_territorial_status(minvu_result: dict[str, Any], external: dict[str, Any]) -> str:
    if any(
        value == "INTERSECTA"
        for value in (
            external["mma"]["protected_area"],
            external["mma"]["wetland"],
        )
    ):
        return "POTENCIALMENTE_NO_APTO"
    if external["dga"]["restriction"] == "INTERSECTA":
        return "REQUIERE_REVISION"
    base = str((minvu_result.get("preliminary_assessment") or {}).get("status") or "")
    if base in {
        "POTENCIALMENTE_APTO",
        "REQUIERE_REVISION",
        "POTENCIALMENTE_NO_APTO",
        "SIN_INFORMACION_SUFICIENTE",
    }:
        return base
    return "SIN_INFORMACION_SUFICIENTE"


def _property_geojson(property_record: dict[str, Any]) -> dict[str, Any] | None:
    value = property_record.get("parcel_geometry")
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None
    return value if isinstance(value, dict) else None


def _property_bbox(
    geometry: dict[str, Any] | None,
    property_record: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    if geometry:
        try:
            return tuple(float(value) for value in shape(geometry).bounds)
        except Exception:
            return None
    lat = _safe_float(property_record.get("latitude"))
    lon = _safe_float(property_record.get("longitude"))
    if lat is None or lon is None:
        return None
    return lon - 0.005, lat - 0.005, lon + 0.005, lat + 0.005


def _expanded_bbox(
    bbox: tuple[float, float, float, float],
    degrees: float,
) -> tuple[float, float, float, float]:
    xmin, ymin, xmax, ymax = bbox
    return xmin - degrees, ymin - degrees, xmax + degrees, ymax + degrees


def _representative_point(property_record: dict[str, Any]) -> Point | None:
    geometry = _property_geojson(property_record)
    if geometry:
        try:
            return shape(geometry).representative_point()
        except Exception:
            pass
    lat = _safe_float(property_record.get("latitude"))
    lon = _safe_float(property_record.get("longitude"))
    if lat is None or lon is None:
        return None
    return Point(lon, lat)


def _arcgis_feature_to_shape(geometry: Any) -> Any | None:
    if not isinstance(geometry, dict):
        return None
    if "paths" in geometry and isinstance(geometry["paths"], list) and geometry["paths"]:
        return LineString(geometry["paths"][0])
    if "rings" in geometry and isinstance(geometry["rings"], list):
        return shape({"type": "Polygon", "coordinates": geometry["rings"]})
    if "x" in geometry and "y" in geometry:
        return Point(float(geometry["x"]), float(geometry["y"]))
    return None


def _distance_m(point_wgs84: Point, other_wgs84: Any) -> float:
    epsg = local_metric_epsg(point_wgs84.x, point_wgs84.y)
    metric_point = reproject_geometry(point_wgs84, input_epsg=4326, output_epsg=epsg)
    metric_other = reproject_geometry(other_wgs84, input_epsg=4326, output_epsg=epsg)
    return float(metric_point.distance(metric_other))


def _feature_id(feature: dict[str, Any]) -> str:
    attributes = feature.get("attributes") if isinstance(feature, dict) else {}
    if not isinstance(attributes, dict):
        return ""
    for key in ("OBJECTID", "objectid", "FID", "fid", "id", "ID"):
        value = attributes.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _refresh_core_minvu_layers(
    repository: MinvuLayerRepository,
    minvu: MinvuArcGisConnector,
) -> None:
    rows = []
    for layer in [*URBAN_LIMIT_LAYERS, *RISK_AREA_LAYERS]:
        service_name = layer.service_url.rstrip("/").split("/")[-2]
        try:
            metadata = await minvu.layer_metadata(layer.service_url, layer.layer_id)
            rows.append(
                {
                    "provider": "IDE MINVU",
                    "service_name": service_name,
                    "layer_name": metadata.get("name") or layer.layer_name,
                    "layer_id": layer.layer_id,
                    "endpoint": layer.service_url,
                    "geometry_type": metadata.get("geometryType"),
                    "spatial_reference": metadata.get("extent", {}).get("spatialReference")
                    or metadata.get("sourceSpatialReference")
                    or {},
                    "fields": metadata.get("fields") or [],
                    "status": "QUERYABLE"
                    if "Query" in str(metadata.get("capabilities"))
                    else "DISCOVERED",
                    "last_checked": utc_now().isoformat(),
                    "raw_metadata": metadata,
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "provider": "IDE MINVU",
                    "service_name": service_name,
                    "layer_name": layer.layer_name,
                    "layer_id": layer.layer_id,
                    "endpoint": layer.service_url,
                    "status": "UNAVAILABLE",
                    "last_checked": utc_now().isoformat(),
                    "raw_metadata": {"error": f"{type(exc).__name__}: {_safe_external_error(exc)}"},
                }
            )
    repository.upsert_many(rows)


def _register_minvu_layers(repository: MinvuLayerRepository, audit: dict) -> None:
    rows = []
    for layer in audit.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        rows.append(
            {
                "provider": "IDE MINVU",
                "service_name": layer.get("service_name"),
                "layer_name": layer.get("layer_name"),
                "layer_id": layer.get("layer_id"),
                "endpoint": layer.get("service_url"),
                "geometry_type": layer.get("geometry_type"),
                "spatial_reference": layer.get("spatial_reference"),
                "fields": layer.get("fields") or [],
                "status": "QUERYABLE" if layer.get("is_queryable") else "DISCOVERED",
                "last_checked": layer.get("last_checked") or audit.get("retrieved_at"),
                "raw_metadata": layer,
            }
        )
    if rows:
        repository.upsert_many(rows)


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
    if settings.mercadolibre_client_id:
        os.environ["MERCADOLIBRE_CLIENT_ID"] = settings.mercadolibre_client_id
    if settings.mercadolibre_client_secret:
        os.environ["MERCADOLIBRE_CLIENT_SECRET"] = settings.mercadolibre_client_secret
    if settings.mercadolibre_redirect_uri:
        os.environ["MERCADOLIBRE_REDIRECT_URI"] = settings.mercadolibre_redirect_uri
    if settings.mercadolibre_partner_seller_ids:
        os.environ["MERCADOLIBRE_PARTNER_SELLER_IDS"] = (
            settings.mercadolibre_partner_seller_ids
        )
    os.environ["MERCADOLIBRE_MARKETPLACE_GLOBAL_ENABLED"] = (
        "true" if settings.mercadolibre_marketplace_global_enabled else "false"
    )
    if settings.mercadolibre_access_token:
        os.environ["MERCADOLIBRE_ACCESS_TOKEN"] = settings.mercadolibre_access_token
    if settings.mercadolibre_refresh_token:
        os.environ["MERCADOLIBRE_REFRESH_TOKEN"] = settings.mercadolibre_refresh_token
    if settings.mercadolibre_access_token_expires_at:
        os.environ["MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT"] = (
            settings.mercadolibre_access_token_expires_at
        )


app = create_app()
