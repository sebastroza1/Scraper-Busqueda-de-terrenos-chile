from __future__ import annotations

import os
import re
import unicodedata
from asyncio import sleep
from datetime import datetime
from enum import StrEnum
from time import perf_counter
from typing import Any

import httpx

from landfinder.catalog.chile import LAND_SEARCH_KEYWORDS
from landfinder.classification import ClassificationDecision, LandOpportunityClassifier
from landfinder.connectors.base import (
    ConnectorHealth,
    ConnectorRunResult,
    SearchQuery,
    SearchSource,
    SourceAuditResult,
    SourceUnavailableError,
)
from landfinder.connectors.transforms import mercado_publico_tender_to_raw
from landfinder.models.enums import (
    ConnectorStrategy,
    SourceAuditStatus,
    SourceHealthStatus,
    SourceType,
)
from landfinder.normalization.parsers import parse_area

DEFAULT_LAND_KEYWORDS = LAND_SEARCH_KEYWORDS


class PublicProcurementLandClassification(StrEnum):
    LAND_ACQUISITION = "LAND_ACQUISITION"
    LAND_SALE = "LAND_SALE"
    REAL_ESTATE = "REAL_ESTATE"
    POSSIBLE_LAND = "POSSIBLE_LAND"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    UNKNOWN = "UNKNOWN"


class MercadoPublicoConnector(SearchSource):
    source_id = "mercado_publico"
    source_name = "Mercado Publico / ChileCompra"
    source_type = SourceType.PUBLIC_PROCUREMENT
    strategy = ConnectorStrategy.OFFICIAL_API
    parser_version = "0.2.0"

    endpoint = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"

    def is_configured(self) -> bool:
        return bool(os.getenv("MERCADO_PUBLICO_TICKET"))

    async def audit_source(self) -> SourceAuditResult:
        return SourceAuditResult(
            source_id=self.source_id,
            source_name=self.source_name,
            source_type=self.source_type,
            official_url="https://www.chilecompra.cl/api/",
            strategy=self.strategy,
            status=SourceAuditStatus.ACTIVE,
            api_available=True,
            authentication="Ticket oficial requerido.",
            rate_limits="ChileCompra documents a 10,000 daily request limit per ticket.",
            terms_notes="Use API under published conditions. Do not exceed limits.",
            obtainable_fields=[
                "codigo",
                "nombre",
                "descripcion",
                "estado",
                "fecha publicacion",
                "fecha cierre",
                "organismo comprador",
                "monto estimado when exposed",
                "comuna/region when buyer metadata exposes them",
            ],
            geolocation="No parcel geolocation in core API; infer only from tender text manually.",
            images="Documents/bases may require separate retrieval from Mercado Publico.",
            references=["https://www.chilecompra.cl/api/"],
            notes=(
                "Uses official listing/detail endpoints and stores deterministic "
                "preliminary land classification."
            ),
        )

    async def health(self) -> ConnectorHealth:
        ticket = os.getenv("MERCADO_PUBLICO_TICKET")
        if not ticket:
            return ConnectorHealth(
                source_id=self.source_id,
                status=SourceHealthStatus.DEGRADED,
                recent_errors=["Missing MERCADO_PUBLICO_TICKET"],
                parser_version=self.parser_version,
            )
        start = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    self.endpoint,
                    params={"ticket": ticket, "fecha": datetime.now().strftime("%d%m%Y")},
                )
                if response.status_code in {401, 403}:
                    return ConnectorHealth(
                        source_id=self.source_id,
                        status=SourceHealthStatus.BROKEN,
                        recent_errors=["Mercado Publico rejected the configured ticket"],
                        parser_version=self.parser_version,
                        latency_ms=int((perf_counter() - start) * 1000),
                    )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001 - health should report degraded, not crash.
            return ConnectorHealth(
                source_id=self.source_id,
                status=SourceHealthStatus.DEGRADED,
                recent_errors=[f"{type(exc).__name__}: {exc}"],
                parser_version=self.parser_version,
                latency_ms=int((perf_counter() - start) * 1000),
            )
        payload_error = _payload_error(payload)
        return ConnectorHealth(
            source_id=self.source_id,
            status=SourceHealthStatus.BROKEN if payload_error else SourceHealthStatus.ACTIVE,
            recent_errors=[payload_error] if payload_error else [],
            found_count=_safe_int(payload.get("Cantidad")) or len(payload.get("Listado") or []),
            parser_version=self.parser_version,
            latency_ms=int((perf_counter() - start) * 1000),
        )

    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        ticket = os.getenv("MERCADO_PUBLICO_TICKET")
        if not ticket:
            raise SourceUnavailableError("MERCADO_PUBLICO_TICKET is required")

        params: dict[str, Any] = {"ticket": ticket}
        if "fecha" in query.extra_filters:
            params["fecha"] = query.extra_filters["fecha"]
        if "estado" in query.extra_filters:
            params["estado"] = query.extra_filters["estado"]
        if "fecha" not in params and "estado" not in params:
            params["estado"] = "activas"

        keywords = _merge_terms(query.keywords)
        max_detail_records = (
            _safe_int(query.extra_filters.get("mercado_publico_max_detail_records")) or 50
        )
        fetch_possible_details = bool(
            query.extra_filters.get("mercado_publico_fetch_possible_details", False)
        )
        warnings: list[str] = []
        false_positives = 0
        possible_records = 0
        detail_fetches = 0

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.endpoint, params=params)
            _raise_safe_http_error(response)
            payload = response.json()
            payload_error = _payload_error(payload)
            if payload_error:
                raise SourceUnavailableError(payload_error)

            listings = payload.get("Listado") or []
            matched: list[dict[str, Any]] = []
            audit_records: list[dict[str, Any]] = []
            for item in listings:
                if not isinstance(item, dict):
                    continue
                if not _matches_keywords(item, keywords, mode=query.keyword_mode):
                    continue
                detail_item = item
                code = _extract_code(item)
                decision = explain_public_procurement_land_tender(item)
                detail_requested = False
                detail_fetched = False
                detail_attempts = 0
                detail_error: str | None = None
                if (
                    code
                    and detail_fetches < max_detail_records
                    and _should_fetch_detail(
                        decision,
                        fetch_possible=fetch_possible_details,
                    )
                ):
                    detail_requested = True
                    detail_attempts = 1
                    try:
                        detail_item = await self._fetch_detail_with_retry(client, ticket, code)
                        detail_fetches += 1
                        detail_fetched = True
                        await sleep(0.75)
                    except Exception as exc:  # noqa: BLE001 - keep list result if detail fails.
                        detail_error = _safe_detail_error(exc)
                        warnings.append(
                            f"{code}: detail unavailable ({detail_error})"
                        )
                    else:
                        decision = explain_public_procurement_land_tender(detail_item)
                classification = PublicProcurementLandClassification(decision.classification.value)
                enriched = _with_landfinder_metadata(
                    list_item=item,
                    detail_item=detail_item,
                    decision=decision,
                    keywords=keywords,
                    keyword_mode=query.keyword_mode,
                    detail_requested=detail_requested,
                    detail_fetched=detail_fetched,
                    detail_attempts=detail_attempts,
                    detail_error=detail_error,
                )
                audit_records.append(_source_record_audit(enriched, decision))
                if classification == PublicProcurementLandClassification.FALSE_POSITIVE:
                    false_positives += 1
                    continue
                if classification not in {
                    PublicProcurementLandClassification.LAND_ACQUISITION,
                    PublicProcurementLandClassification.LAND_SALE,
                }:
                    possible_records += 1
                    continue
                matched.append(mercado_publico_tender_to_raw(enriched).model_dump(mode="json"))

        if false_positives:
            warnings.append(f"Filtered {false_positives} deterministic false positive tender(s).")
        if possible_records:
            warnings.append(
                f"Kept {possible_records} possible tender(s) for audit/manual review only."
            )
        warnings.append(
            "Mercado Publico matches are public procurement records; classification is "
            "preliminary and preserves original tender text."
        )

        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            raw_records=matched,
            audit_records=audit_records,
            warnings=warnings,
        )

    async def fetch_detail(self, external_id: str) -> dict[str, Any]:
        ticket = os.getenv("MERCADO_PUBLICO_TICKET")
        if not ticket:
            raise SourceUnavailableError("MERCADO_PUBLICO_TICKET is required")
        async with httpx.AsyncClient(timeout=30) as client:
            return await self._fetch_detail_with_client(client, ticket, external_id)

    async def _fetch_detail_with_client(
        self,
        client: httpx.AsyncClient,
        ticket: str,
        code: str,
    ) -> dict[str, Any]:
        response = await client.get(self.endpoint, params={"ticket": ticket, "codigo": code})
        _raise_safe_http_error(response)
        payload = response.json()
        payload_error = _payload_error(payload)
        if payload_error:
            raise SourceUnavailableError(payload_error)
        listings = payload.get("Listado")
        if isinstance(listings, list) and listings:
            first = listings[0]
            if isinstance(first, dict):
                return first
        if isinstance(payload, dict):
            return payload
        return {}

    async def _fetch_detail_with_retry(
        self,
        client: httpx.AsyncClient,
        ticket: str,
        code: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for delay in (0.0, 1.5, 4.0):
            if delay:
                await sleep(delay)
            try:
                return await self._fetch_detail_with_client(client, ticket, code)
            except Exception as exc:  # noqa: BLE001 - classify retryable detail failures.
                last_error = exc
                if not _is_retryable_detail_error(exc):
                    raise
        if last_error is not None:
            raise last_error
        return {}


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return "" if value is None else str(value)


def classify_public_procurement_land_tender(
    item: dict[str, Any],
) -> PublicProcurementLandClassification:
    decision = explain_public_procurement_land_tender(item)
    return PublicProcurementLandClassification(decision.classification.value)


def explain_public_procurement_land_tender(item: dict[str, Any]) -> ClassificationDecision:
    return LandOpportunityClassifier().classify(item)


def _merge_terms(query_keywords: list[str]) -> list[str]:
    terms = [*DEFAULT_LAND_KEYWORDS, *query_keywords]
    normalized: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = _normalize_text(term)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _contains_any_term(text: str, terms: list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    escaped = re.escape(term).replace(r"\ ", r"\s+")
    return re.search(rf"(?<!\w){escaped}(?!\w)", text) is not None


def _matches_keywords(item: dict[str, Any], keywords: list[str], *, mode: str = "ANY") -> bool:
    text = _normalize_text(_flatten_text(item))
    return _keyword_match(text, keywords, mode=mode)


def _keyword_match(text: str, keywords: list[str], *, mode: str) -> bool:
    if not keywords:
        return True
    matched = [_contains_term(text, keyword) for keyword in keywords]
    if mode.upper() == "ALL":
        return all(matched)
    return any(matched)


def _with_landfinder_metadata(
    *,
    list_item: dict[str, Any],
    detail_item: dict[str, Any],
    decision: ClassificationDecision,
    keywords: list[str],
    keyword_mode: str,
    detail_requested: bool,
    detail_fetched: bool,
    detail_attempts: int,
    detail_error: str | None,
) -> dict[str, Any]:
    enriched = dict(detail_item or list_item)
    code = _extract_code(enriched) or _extract_code(list_item)
    enriched.setdefault("CodigoExterno", code)
    normalized_text = _normalize_text(_flatten_text(enriched))
    enriched["landfinder"] = {
        "procurement_classification": decision.classification.value,
        "automatic_confidence": decision.confidence,
        "automatic_score": decision.score,
        "positive_terms": decision.positive_terms,
        "negative_terms": decision.negative_terms,
        "rules_triggered": decision.rules_triggered,
        "classification_reason": decision.explanation,
        "requires_manual_review": decision.requires_manual_review,
        "original_text": _flatten_text(enriched),
        "matched_terms": [term for term in keywords if _contains_term(normalized_text, term)],
        "keyword_mode": keyword_mode.upper(),
        "detail_requested": detail_requested,
        "detail_fetched": detail_fetched,
        "detail_attempts": detail_attempts,
        "detail_http_status": 200 if detail_fetched else None,
        "detail_error": detail_error,
        "list_record": list_item,
        "official_api_detail_url": _official_api_detail_url(code),
        "official_web_link_status": "UNAVAILABLE_FROM_PUBLIC_API_WITHOUT_ENCRYPTED_QS",
    }
    return enriched


def _should_fetch_detail(
    decision: ClassificationDecision,
    *,
    fetch_possible: bool,
) -> bool:
    if decision.classification.value in {"LAND_ACQUISITION", "LAND_SALE"}:
        return True
    return fetch_possible and decision.classification.value != "FALSE_POSITIVE"


def _source_record_audit(
    item: dict[str, Any],
    decision: ClassificationDecision,
) -> dict[str, Any]:
    raw = mercado_publico_tender_to_raw(item)
    landfinder = raw.raw_payload.get("landfinder", {})
    dates = item.get("Fechas") if isinstance(item.get("Fechas"), dict) else {}
    code = _extract_code(item)
    amount, currency = _amount_and_currency(item)
    area = parse_area(raw.area_raw)
    return {
        "source": "mercado_publico",
        "source_type": SourceType.PUBLIC_PROCUREMENT.value,
        "external_id": code,
        "title": raw.title,
        "description": item.get("Descripcion") or item.get("description"),
        "organization": landfinder.get("organization_name"),
        "organization_region": landfinder.get("organization_region"),
        "organization_commune": landfinder.get("organization_commune"),
        "organization_address": landfinder.get("organization_address"),
        "publication_date": _first_text(dates, "FechaPublicacion", "FechaCreacion"),
        "closing_date": _first_text(dates, "FechaCierre", "FechaFinal"),
        "status": item.get("Estado") or item.get("status"),
        "region": raw.region_raw,
        "commune": raw.commune_raw,
        "property_region": landfinder.get("property_region"),
        "property_commune": landfinder.get("property_commune"),
        "property_address": landfinder.get("property_address"),
        "amount": amount,
        "currency": currency,
        "amount_raw": landfinder.get("amount_raw") or raw.price_raw,
        "amount_type": landfinder.get("amount_type")
        or ("ESTIMATED_AMOUNT" if amount else "UNKNOWN"),
        "amount_source": landfinder.get("amount_source"),
        "amount_confidence": landfinder.get("amount_confidence") or 0,
        "surface_raw": landfinder.get("surface_raw") or raw.area_raw,
        "surface_m2": float(area.value_m2) if area else None,
        "surface_source": landfinder.get("surface_source"),
        "surface_confidence": landfinder.get("surface_confidence")
        or (area.confidence if area else 0),
        "source_url": _official_api_detail_url(code),
        "detail_fetched": landfinder.get("detail_fetched") or False,
        "detail_attempts": landfinder.get("detail_attempts") or 0,
        "detail_http_status": landfinder.get("detail_http_status"),
        "fields_extracted": landfinder.get("fields_extracted") or [],
        "fields_missing": landfinder.get("fields_missing") or [],
        "extraction_reasons": landfinder.get("extraction_reasons") or {},
        "data_completeness_score": landfinder.get("data_completeness_score") or 0,
        "raw_payload": raw.raw_payload,
        "automatic_classification": decision.classification.value,
        "automatic_confidence": decision.confidence,
        "automatic_score": decision.score,
        "classification_reason": decision.explanation,
        "positive_terms": decision.positive_terms,
        "negative_terms": decision.negative_terms,
        "rules_triggered": decision.rules_triggered,
        "manual_classification": "UNREVIEWED",
        "manual_review_status": "UNREVIEWED",
    }


def _extract_code(item: dict[str, Any]) -> str | None:
    for key in ("CodigoExterno", "Codigo", "code", "id"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _first_text(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _amount_and_currency(item: dict[str, Any]) -> tuple[float | None, str | None]:
    for key in ("MontoEstimado", "Monto", "Estimacion"):
        value = item.get(key)
        if value in (None, "", 0):
            continue
        amount = _safe_float(value)
        if amount is None or amount <= 1000:
            continue
        currency = str(item.get("TipoMoneda") or item.get("Moneda") or "CLP")
        return amount, currency
    return None, None


def _official_api_detail_url(code: str | None) -> str | None:
    if not code:
        return None
    return f"https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo={code}"


def _payload_error(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("Error", "error", "MensajeError", "mensajeError"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _raise_safe_http_error(response: httpx.Response) -> None:
    if response.status_code in {401, 403}:
        raise SourceUnavailableError("Mercado Publico rejected the configured ticket")
    if response.status_code == 429:
        raise SourceUnavailableError("Mercado Publico rate limited the request (429)")
    response.raise_for_status()


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(without_accents.lower().split())


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_detail_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(
        r"(?i)(ticket|apikey|access_token|refresh_token)=([^&\s'\"}\]]+)",
        r"\1=REDACTED",
        message,
    )
    return f"{type(exc).__name__}: {message[:180]}"


def _is_retryable_detail_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    message = str(exc).lower()
    return "429" in message or "rate limited" in message
