from __future__ import annotations

import re
from datetime import date
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx

from landfinder.classification import ClassificationDecision, LandOpportunityClassifier
from landfinder.connectors.base import (
    ConnectorHealth,
    ConnectorRunResult,
    SearchQuery,
    SearchSource,
    SourceAuditResult,
)
from landfinder.connectors.transforms import mercado_publico_tender_to_raw
from landfinder.models.enums import (
    ConnectorStrategy,
    SourceAuditStatus,
    SourceHealthStatus,
    SourceType,
)


class ChileCompraOCDSProvider(SearchSource):
    source_id = "chilecompra_ocds"
    source_name = "ChileCompra Datos Abiertos OCDS"
    source_type = SourceType.PUBLIC_PROCUREMENT
    strategy = ConnectorStrategy.OPEN_DATA
    parser_version = "0.1.0"

    endpoint_template = (
        "https://api.mercadopublico.cl/APISOCDS/OCDS/"
        "listaOCDSAgnoMes/{year}/{month}/{start}/{end}"
    )

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def audit_source(self) -> SourceAuditResult:
        return SourceAuditResult(
            source_id=self.source_id,
            source_name=self.source_name,
            source_type=self.source_type,
            official_url="https://datos-abiertos.chilecompra.cl/descargas/procesos-ocds",
            strategy=self.strategy,
            status=SourceAuditStatus.ACTIVE,
            api_available=True,
            authentication="No ticket is documented for the public OCDS monthly endpoint.",
            rate_limits="Official documentation caps each range query at 1,000 records.",
            obtainable_fields=[
                "ocid",
                "id",
                "date",
                "buyer",
                "tender.title",
                "tender.description",
                "tender.items",
                "tender.value",
                "documents",
                "awards",
                "contracts",
            ],
            geolocation=(
                "OCDS does not provide parcel geometry; locations are semantic targets only."
            ),
            references=["https://datos-abiertos.chilecompra.cl/descargas/procesos-ocds"],
            notes=(
                "Used for opportunity discovery. Land demand is never persisted as a PropertyAsset."
            ),
        )

    async def health(self) -> ConnectorHealth:
        now = date.today()
        start = perf_counter()
        try:
            payload = await self._fetch(now.year, f"{now.month:02d}", 0, 1)
        except Exception as exc:  # noqa: BLE001
            return ConnectorHealth(
                source_id=self.source_id,
                status=SourceHealthStatus.DEGRADED,
                recent_errors=[f"{type(exc).__name__}: {exc}"],
                parser_version=self.parser_version,
                latency_ms=int((perf_counter() - start) * 1000),
            )
        return ConnectorHealth(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            found_count=len(_records_from_payload(payload)),
            parser_version=self.parser_version,
            latency_ms=int((perf_counter() - start) * 1000),
        )

    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        today = date.today()
        year = int(query.extra_filters.get("ocds_year") or today.year)
        month = f"{int(query.extra_filters.get('ocds_month') or today.month):02d}"
        start = int(query.extra_filters.get("ocds_start") or 0)
        end = int(query.extra_filters.get("ocds_end") or min(start + 250, start + 1000))
        payload = await self._fetch(year, month, start, end)
        records = _records_from_payload(payload)
        classifier = LandOpportunityClassifier()
        raw_records: list[dict[str, Any]] = []
        audit_records: list[dict[str, Any]] = []
        related = 0
        discarded = 0

        for index_record in records:
            for record in await self._expanded_records(index_record):
                tender = _tender_like_payload(record)
                if not _matches_keywords(tender, query):
                    continue
                decision = classifier.classify(tender)
                if decision.classification.value == "UNKNOWN":
                    discarded += 1
                    continue
                related += 1
                enriched = _with_landfinder_metadata(record, tender, decision)
                audit_records.append(_source_record_audit(enriched, decision))
                if decision.classification.value in {
                    "PROPERTY_FOR_SALE",
                    "PROPERTY_FOR_LEASE",
                    "PROPERTY_FOR_CONCESSION",
                    "LAND_SALE_PROCESS",
                }:
                    raw_records.append(mercado_publico_tender_to_raw(enriched).model_dump(mode="json"))

        warnings = [
            (
                "ChileCompra OCDS records are SourceRecords/Opportunities first; "
                "LAND_DEMAND and related services are not mapped to PropertyAssets."
            )
        ]
        if discarded:
            warnings.append(f"Discarded {discarded} unrelated/unknown OCDS record(s).")
        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            raw_records=raw_records,
            audit_records=audit_records,
            warnings=warnings,
        )

    async def _expanded_records(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        detail_url = _detail_url(record)
        if detail_url is None:
            return [record]
        try:
            payload = await self._fetch_url(detail_url)
        except httpx.HTTPError:
            return [record]
        releases = _records_from_payload(payload)
        if releases:
            return [_latest_tender_release(releases)]
        return [record]

    async def _fetch(
        self, year: int, month: str, start: int, end: int
    ) -> dict[str, Any] | list[Any]:
        url = self.endpoint_template.format(year=year, month=month, start=start, end=end)
        return await self._fetch_url(url)

    async def _fetch_url(self, url: str) -> dict[str, Any] | list[Any]:
        url = _prefer_https(url)
        if self._client is not None:
            response = await self._client.get(url)
        else:
            async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
                response = await client.get(url)
        response.raise_for_status()
        return response.json()


def _records_from_payload(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    for key in ("records", "releases", "Listado", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return [item for item in value if isinstance(item, dict)]
    return []


def _latest_tender_release(records: list[dict[str, Any]]) -> dict[str, Any]:
    tender_records = [
        record for record in records if isinstance(record.get("tender"), dict)
    ]
    candidates = tender_records or records
    return max(candidates, key=lambda record: str(record.get("date") or ""))


def _tender_like_payload(record: dict[str, Any]) -> dict[str, Any]:
    release = (
        record.get("compiledRelease")
        if isinstance(record.get("compiledRelease"), dict)
        else record
    )
    tender = release.get("tender") if isinstance(release.get("tender"), dict) else {}
    buyer = (
        release.get("buyer")
        if isinstance(release.get("buyer"), dict)
        else _buyer_from_parties(release)
    )
    items = tender.get("items") if isinstance(tender.get("items"), list) else []
    value = tender.get("value") if isinstance(tender.get("value"), dict) else {}
    documents = tender.get("documents") if isinstance(tender.get("documents"), list) else []
    code = (
        tender.get("id")
        or release.get("id")
        or release.get("ocid")
        or record.get("ocid")
        or record.get("id")
    )
    return {
        "CodigoExterno": code,
        "Nombre": tender.get("title") or release.get("title"),
        "Descripcion": tender.get("description"),
        "Estado": tender.get("status"),
        "MontoEstimado": value.get("amount"),
        "TipoMoneda": value.get("currency"),
        "Comprador": {
            "NombreOrganismo": buyer.get("name"),
            "ID": buyer.get("id"),
        },
        "Items": {
            "Listado": [
                {
                    "NombreProducto": item.get("description") or item.get("title"),
                    "Descripcion": item.get("description") or item.get("title"),
                    "Categoria": ((item.get("classification") or {}).get("description")),
                }
                for item in items
                if isinstance(item, dict)
            ]
        },
        "Documentos": documents,
        "Url": _canonical_url(code),
        "raw_ocds": record,
    }


def _with_landfinder_metadata(
    record: dict[str, Any],
    tender: dict[str, Any],
    decision: ClassificationDecision,
) -> dict[str, Any]:
    enriched = dict(tender)
    enriched["landfinder"] = {
        "procurement_classification": decision.classification.value,
        "automatic_confidence": decision.confidence,
        "automatic_score": decision.score,
        "positive_terms": decision.positive_terms,
        "negative_terms": decision.negative_terms,
        "rules_triggered": decision.rules_triggered,
        "classification_reason": decision.explanation,
        "requires_manual_review": decision.requires_manual_review,
        "surface_context": "UNKNOWN_AREA",
        "amount_type": "PROCUREMENT_BUDGET"
        if decision.classification.value in {"LAND_DEMAND", "PROPERTY_DEMAND"}
        else "UNKNOWN_AMOUNT",
        "raw_ocds": record,
    }
    return enriched


def _source_record_audit(item: dict[str, Any], decision: ClassificationDecision) -> dict[str, Any]:
    raw = mercado_publico_tender_to_raw(item)
    landfinder = raw.raw_payload.get("landfinder", {})
    return {
        "source": "chilecompra_ocds",
        "source_type": SourceType.PUBLIC_PROCUREMENT.value,
        "external_id": raw.external_id,
        "title": raw.title,
        "description": raw.description,
        "organization": landfinder.get("organization_name"),
        "amount_raw": landfinder.get("amount_raw") or raw.price_raw,
        "amount_type": landfinder.get("amount_type"),
        "amount_confidence": landfinder.get("amount_confidence") or 0,
        "surface_raw": landfinder.get("surface_raw") or raw.area_raw,
        "surface_m2": None,
        "surface_confidence": 0,
        "source_url": raw.canonical_url,
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


def _matches_keywords(item: dict[str, Any], query: SearchQuery) -> bool:
    text = _flatten_text(item).lower()
    if not query.keywords:
        return True
    matches = [keyword.lower() in text for keyword in query.keywords]
    if query.keyword_mode.upper() == "ALL":
        return all(matches)
    return any(matches)


def _detail_url(record: dict[str, Any]) -> str | None:
    value = record.get("urlTender")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _prefer_https(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "http" and parsed.netloc.endswith("mercadopublico.cl"):
        return "https://" + url.removeprefix("http://")
    return url


def _buyer_from_parties(release: dict[str, Any]) -> dict[str, Any]:
    parties = release.get("parties") if isinstance(release.get("parties"), list) else []
    for party in parties:
        if not isinstance(party, dict):
            continue
        roles = party.get("roles") if isinstance(party.get("roles"), list) else []
        if "buyer" in roles or "procuringEntity" in roles:
            return {
                "name": party.get("name") or (party.get("identifier") or {}).get("legalName"),
                "id": party.get("id") or (party.get("identifier") or {}).get("id"),
            }
    return {}


def _canonical_url(code: Any) -> str | None:
    if not code:
        return None
    code_text = str(code)
    tender_code = re.search(r"\d+-\d+-[A-Z0-9]+", code_text)
    if tender_code:
        return (
            "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx"
            f"?idlicitacion={tender_code.group(0)}"
        )
    return "https://datos-abiertos.chilecompra.cl/descargas/procesos-ocds"


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return "" if value is None else str(value)
