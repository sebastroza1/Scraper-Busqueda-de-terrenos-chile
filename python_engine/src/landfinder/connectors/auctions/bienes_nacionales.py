from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from time import perf_counter
from typing import Any
from urllib.parse import urlencode, urljoin
from xml.etree import ElementTree

import httpx

from landfinder.connectors.base import (
    ConnectorHealth,
    ConnectorRunResult,
    SearchQuery,
    SearchSource,
    SourceAuditResult,
)
from landfinder.models.enums import (
    ConnectorStrategy,
    SourceAuditStatus,
    SourceHealthStatus,
    SourceType,
)
from landfinder.models.records import RawSourceRecord
from landfinder.normalization.parsers import parse_area


@dataclass(frozen=True)
class BienesNacionalesDocument:
    url: str
    filename: str
    document_type: str


class BienesNacionalesProvider(SearchSource):
    source_id = "bienes_nacionales"
    source_name = "Ministerio de Bienes Nacionales - Portal de Licitaciones"
    source_type = SourceType.PUBLIC_LAND
    strategy = ConnectorStrategy.HTML
    parser_version = "0.1.0"

    base_url = "https://licitaciones.mbienes.gob.cl"

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def audit_source(self) -> SourceAuditResult:
        return SourceAuditResult(
            source_id=self.source_id,
            source_name=self.source_name,
            source_type=self.source_type,
            official_url=self.base_url,
            strategy=self.strategy,
            status=SourceAuditStatus.ACTIVE,
            api_available=False,
            authentication="No credentials required for public listing/detail pages.",
            rate_limits=(
                "Conservative HTML extraction; one listing page and limited details per run."
            ),
            obtainable_fields=[
                "source_id",
                "canonical_url",
                "title",
                "status",
                "modality",
                "use_category",
                "region",
                "province",
                "commune",
                "surface_m2",
                "minimum_price",
                "cadastral_id",
                "bienes_id",
                "planning_instrument",
                "allowed_uses",
                "prohibited_uses",
                "documents",
                "photos",
                "geonodo_url",
                "KMZ/KML geometry when linked",
            ],
            geolocation="Official KML/KMZ geometry is preferred over text geocoding.",
            images="Photo URLs are preserved, but not downloaded by this connector.",
            references=[
                self.base_url,
                f"{self.base_url}/licitaciones?estado=actuales&estado=futuras",
            ],
            notes=(
                "No public documented API was found in the portal review. The connector "
                "therefore extracts only visible official HTML and linked KMZ/KML files."
            ),
        )

    async def health(self) -> ConnectorHealth:
        start = perf_counter()
        try:
            html_text = await self._get_text("/licitaciones?estado=actuales&estado=futuras")
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
            found_count=len(_listing_links(html_text, self.base_url)),
            parser_version=self.parser_version,
            latency_ms=int((perf_counter() - start) * 1000),
        )

    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        statuses = query.extra_filters.get("bienes_nacionales_estados") or [
            "actuales",
            "futuras",
        ]
        if isinstance(statuses, str):
            statuses = [statuses]
        max_records = int(query.extra_filters.get("bienes_nacionales_max_records") or 50)
        max_pages = int(query.extra_filters.get("bienes_nacionales_max_pages") or 15)
        fetch_geometry = bool(query.extra_filters.get("bienes_nacionales_fetch_geometry", True))
        params: list[tuple[str, str]] = [
            ("estado", str(status).lower()) for status in statuses
        ]
        query_text = _search_text(query.keywords)
        if query_text:
            params.append(("q", query_text))
        status_query = urlencode(params)
        links: list[str] = []
        for page in range(1, max_pages + 1):
            page_query = status_query if page == 1 else f"{status_query}&pagina={page}"
            html_text = await self._get_text(f"/licitaciones?{page_query}")
            page_links = _listing_links(html_text, self.base_url)
            if not page_links:
                break
            links.extend(page_links)
            links = list(dict.fromkeys(links))
            if len(links) >= max_records:
                break
        raw_records: list[dict[str, Any]] = []
        audit_records: list[dict[str, Any]] = []
        warnings: list[str] = []

        for detail_url in links[:max_records]:
            detail_html = await self._get_text(detail_url)
            parsed = await self._parse_detail(detail_url, detail_html, fetch_geometry)
            if not _matches_query(parsed, query):
                continue
            raw = _parsed_to_raw(parsed)
            raw_records.append(raw.model_dump(mode="json"))
            audit_records.append(_parsed_to_audit(parsed))

        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            raw_records=raw_records,
            audit_records=audit_records,
            warnings=warnings,
        )

    async def _parse_detail(
        self,
        detail_url: str,
        detail_html: str,
        fetch_geometry: bool,
    ) -> dict[str, Any]:
        parser = _TextAndLinkParser()
        parser.feed(detail_html)
        text = "\n".join(parser.text_parts)
        compact_text = " ".join(parser.text_parts)
        documents = _documents_from_links(parser.links, detail_url)
        geometry_documents = [
            document for document in documents if document.document_type in {"KML", "KMZ"}
        ]
        geometry_documents.sort(key=lambda document: 0 if document.document_type == "KMZ" else 1)
        geometry: dict[str, Any] | None = None
        geometry_source: str | None = None
        if fetch_geometry and geometry_documents:
            try:
                selected_document = geometry_documents[0]
                geometry = await self._fetch_geometry(selected_document.url)
                geometry_source = f"BIENES_NACIONALES_{selected_document.document_type}"
            except Exception:  # noqa: BLE001 - geometry absence must not drop the asset.
                geometry = None

        code = _first_match(r"\bL-\d{4}-S\d+-\d+\b", compact_text)
        title = _title_from_html(detail_html) or _line_after_code(parser.text_parts, code)
        modality = _label(text, "Modalidad")
        surface_raw = _label(text, "Superficie")
        surface = parse_area(surface_raw)
        price_raw = _minimum_price(compact_text)
        classification = _classification_for_modality(modality)
        return {
            "source_id": code,
            "external_id": code,
            "canonical_url": detail_url,
            "title": title,
            "status": _status_from_text(parser.text_parts),
            "modality": modality,
            "use_category": _use_category(parser.text_parts),
            "region": _label(text, "Región"),
            "province": _label(text, "Provincia"),
            "commune": _label(text, "Comuna"),
            "location_description": _description(compact_text),
            "surface_raw": surface_raw,
            "surface_m2": float(surface.value_m2) if surface else None,
            "price_raw": price_raw,
            "minimum_price": _price_amount(price_raw),
            "currency": _price_currency(price_raw),
            "cadastral_id": _label(text, "ID Catastral"),
            "bienes_id": _label(text, "ID Bienes"),
            "planning_instrument": _planning_instrument(parser.text_parts),
            "allowed_uses": _section_after(parser.text_parts, "Uso permitido"),
            "prohibited_uses": _section_after(parser.text_parts, "Uso prohibido"),
            "description": _description(compact_text),
            "documents": [document.__dict__ for document in documents],
            "photos": _photos_from_links(parser.links, detail_url),
            "geonodo_url": _geonodo_url(parser.links, detail_url),
            "geometry": geometry,
            "geometry_source": geometry_source,
            "classification": classification,
            "raw_source": {
                "text": compact_text,
                "links": parser.links,
            },
        }

    async def _fetch_geometry(self, url: str) -> dict[str, Any] | None:
        content = await self._get_bytes(url)
        if url.lower().endswith(".kmz"):
            with zipfile.ZipFile(BytesIO(content)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
                if not names:
                    return None
                content = archive.read(names[0])
        return _kml_to_geojson(content)

    async def _get_text(self, url_or_path: str) -> str:
        response = await self._request(url_or_path)
        return response.text

    async def _get_bytes(self, url_or_path: str) -> bytes:
        response = await self._request(url_or_path)
        return response.content

    async def _request(self, url_or_path: str) -> httpx.Response:
        url = urljoin(self.base_url, url_or_path)
        if self._client is not None:
            response = await self._client.get(url)
        else:
            async with httpx.AsyncClient(
                timeout=30,
                headers={"User-Agent": "LandfinderChile/0.1 local prototype"},
            ) as client:
                response = await client.get(url)
        response.raise_for_status()
        return response


class _TextAndLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            self._current_href = attrs_dict.get("href")
        if tag.lower() in {"br", "p", "div", "section", "li", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self._current_href = None
        if tag.lower() in {"p", "div", "section", "li", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = " ".join(html.unescape(data).split())
        if not text:
            return
        self.text_parts.append(text)
        if self._current_href:
            self.links.append({"href": self._current_href, "text": text})


def _listing_links(html_text: str, base_url: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r'href=["\']([^"\']*/licitacion/[^"\']+)["\']', html_text):
        links.append(urljoin(base_url, html.unescape(match.group(1))))
    return list(dict.fromkeys(links))


def _parsed_to_raw(parsed: dict[str, Any]) -> RawSourceRecord:
    landfinder = {
        "procurement_classification": parsed["classification"],
        "automatic_confidence": 0.96,
        "automatic_score": 120,
        "positive_terms": [parsed.get("modality"), parsed.get("title"), "inmueble fiscal"],
        "negative_terms": [],
        "rules_triggered": ["BIENES_NACIONALES_OFFICIAL_ASSET"],
        "classification_reason": (
            "Official Bienes Nacionales listing; asset page exposes modality, "
            "surface and public documents."
        ),
        "requires_manual_review": False,
        "surface_context": "PARCEL_AREA",
        "official_area_m2": parsed.get("surface_m2"),
        "amount_type": _amount_type_for_classification(parsed["classification"]),
        "price_type": _amount_type_for_classification(parsed["classification"]),
        "geometry": parsed.get("geometry"),
        "parcel_geometry": parsed.get("geometry"),
        "geometry_source": parsed.get("geometry_source"),
        "documents": parsed.get("documents") or [],
        "photos": parsed.get("photos") or [],
        "geonodo_url": parsed.get("geonodo_url"),
        "cadastral_id": parsed.get("cadastral_id"),
        "bienes_id": parsed.get("bienes_id"),
        "planning_instrument": parsed.get("planning_instrument"),
        "allowed_uses": parsed.get("allowed_uses"),
        "prohibited_uses": parsed.get("prohibited_uses"),
    }
    return RawSourceRecord(
        source_id="bienes_nacionales",
        source_type=SourceType.PUBLIC_LAND,
        external_id=parsed.get("external_id"),
        canonical_url=parsed.get("canonical_url"),
        title=parsed.get("title"),
        description=parsed.get("description"),
        price_raw=parsed.get("price_raw"),
        area_raw=parsed.get("surface_raw"),
        region_raw=parsed.get("region"),
        province_raw=parsed.get("province"),
        commune_raw=parsed.get("commune"),
        address_raw=parsed.get("location_description"),
        image_urls=parsed.get("photos") or [],
        raw_payload={**parsed, "landfinder": landfinder},
    )


def _parsed_to_audit(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "bienes_nacionales",
        "source_type": SourceType.PUBLIC_LAND.value,
        "external_id": parsed.get("external_id"),
        "title": parsed.get("title"),
        "description": parsed.get("description"),
        "status": parsed.get("status"),
        "region": parsed.get("region"),
        "commune": parsed.get("commune"),
        "property_region": parsed.get("region"),
        "property_commune": parsed.get("commune"),
        "property_address": parsed.get("location_description"),
        "amount": parsed.get("minimum_price"),
        "currency": parsed.get("currency"),
        "amount_raw": parsed.get("price_raw"),
        "amount_type": _amount_type_for_classification(parsed["classification"]),
        "amount_source": "official_detail_html",
        "amount_confidence": 0.9 if parsed.get("minimum_price") else 0,
        "surface_raw": parsed.get("surface_raw"),
        "surface_m2": parsed.get("surface_m2"),
        "surface_source": "official_detail_html",
        "surface_confidence": 0.95 if parsed.get("surface_m2") else 0,
        "source_url": parsed.get("canonical_url"),
        "detail_fetched": True,
        "detail_attempts": 1,
        "detail_http_status": 200,
        "fields_extracted": [
            field
            for field in (
                "title",
                "modality",
                "surface",
                "price",
                "region",
                "commune",
                "documents",
                "geometry",
            )
            if parsed.get(field) or (field == "geometry" and parsed.get("geometry"))
        ],
        "raw_payload": parsed,
        "automatic_classification": parsed["classification"],
        "automatic_confidence": 0.96,
        "automatic_score": 120,
        "classification_reason": "Official public land asset from Bienes Nacionales.",
        "positive_terms": [parsed.get("modality") or "", "inmueble fiscal"],
        "negative_terms": [],
        "rules_triggered": ["BIENES_NACIONALES_OFFICIAL_ASSET"],
        "manual_classification": "UNREVIEWED",
        "manual_review_status": "UNREVIEWED",
    }


def _matches_query(parsed: dict[str, Any], query: SearchQuery) -> bool:
    if query.regions and parsed.get("region") not in query.regions:
        return False
    if query.communes and parsed.get("commune") not in query.communes:
        return False
    text = " ".join(
        str(parsed.get(key) or "") for key in ("title", "description", "region", "commune")
    ).lower()
    if query.keywords:
        matches = [keyword.lower() in text for keyword in query.keywords]
        if query.keyword_mode.upper() == "ALL" and not all(matches):
            return False
        if query.keyword_mode.upper() != "ALL" and not any(matches):
            return False
    if query.gross_area_min_m2 is not None:
        surface = parsed.get("surface_m2")
        if surface is None or float(surface) < query.gross_area_min_m2:
            return False
    if query.gross_area_max_m2 is not None:
        surface = parsed.get("surface_m2")
        if surface is None or float(surface) > query.gross_area_max_m2:
            return False
    return True


def _search_text(keywords: list[str]) -> str | None:
    meaningful = [
        keyword.strip()
        for keyword in keywords
        if keyword.strip().lower()
        not in {"terreno", "terrenos", "inmueble", "inmuebles", "predio", "lote"}
    ]
    if not meaningful:
        return None
    return " ".join(meaningful[:4])


def _documents_from_links(
    links: list[dict[str, str]],
    detail_url: str,
) -> list[BienesNacionalesDocument]:
    documents: list[BienesNacionalesDocument] = []
    for link in links:
        href = link.get("href") or ""
        text = link.get("text") or href.rsplit("/", 1)[-1]
        lower = text.lower()
        if not lower.endswith((".pdf", ".kmz", ".kml", ".gpkg")):
            continue
        if lower.endswith(".kmz"):
            kind = "KMZ"
        elif lower.endswith(".kml"):
            kind = "KML"
        elif lower.endswith(".gpkg"):
            kind = "GPKG"
        elif "_99" in lower or "plano" in lower:
            kind = "PLANO"
        elif lower.endswith(".pdf"):
            kind = "BASES"
        else:
            kind = "DOCUMENT"
        documents.append(
            BienesNacionalesDocument(
                url=urljoin(detail_url, href),
                filename=text,
                document_type=kind,
            )
        )
    return documents


def _photos_from_links(links: list[dict[str, str]], detail_url: str) -> list[str]:
    urls = []
    for link in links:
        href = link.get("href") or ""
        if href.lower().endswith((".webp", ".jpg", ".jpeg", ".png")):
            urls.append(urljoin(detail_url, href))
    return list(dict.fromkeys(urls))


def _geonodo_url(links: list[dict[str, str]], detail_url: str) -> str | None:
    for link in links:
        text = link.get("text", "").lower()
        href = link.get("href") or ""
        if "geonodo" in text or "geoportal" in href:
            return urljoin(detail_url, href)
    return None


def _kml_to_geojson(content: bytes) -> dict[str, Any] | None:
    root = ElementTree.fromstring(content)
    coordinates = [
        item.text or ""
        for item in root.findall(".//{http://www.opengis.net/kml/2.2}coordinates")
    ]
    if not coordinates:
        coordinates = [item.text or "" for item in root.findall(".//coordinates")]
    rings = []
    for coordinate_text in coordinates:
        points = []
        for token in coordinate_text.split():
            parts = token.split(",")
            if len(parts) < 2:
                continue
            lon = _safe_float(parts[0])
            lat = _safe_float(parts[1])
            if lon is not None and lat is not None:
                points.append([lon, lat])
        if len(points) >= 3:
            if points[0] != points[-1]:
                points.append(points[0])
            rings.append(points)
    if not rings:
        return None
    return {"type": "Polygon", "coordinates": [rings[0]]}


def _label(text: str, label: str) -> str | None:
    pattern = rf"{re.escape(label)}:\s*([^\n]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return " ".join(match.group(1).split()) if match else None


def _title_from_html(html_text: str) -> str | None:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"<[^>]+>", "", html.unescape(match.group(1))).strip()


def _line_after_code(lines: list[str], code: str | None) -> str | None:
    if not code:
        return None
    compact = [line.strip() for line in lines if line.strip()]
    try:
        index = compact.index(code)
    except ValueError:
        return None
    return compact[index + 1] if index + 1 < len(compact) else None


def _status_from_text(lines: list[str]) -> str | None:
    compact = [line.strip() for line in lines if line.strip()]
    for line in compact[:12]:
        if line.lower() in {"abierta", "proximamente", "próximamente", "desierta", "adjudicada"}:
            return line
    return None


def _use_category(lines: list[str]) -> str | None:
    categories = {"industrial", "energia", "energía", "turismo", "agricola", "agrícola"}
    for line in [item.strip() for item in lines if item.strip()][:20]:
        first = line.split()[0].lower() if line.split() else ""
        if first in categories or "habitacional" in line.lower():
            return line.replace("Actuales", "").replace("Futuras", "").strip()
    return None


def _planning_instrument(lines: list[str]) -> str | None:
    compact = [line.strip() for line in lines if line.strip()]
    for index, line in enumerate(compact):
        if "Instrumento de Planificación Territorial" in line and index + 1 < len(compact):
            return compact[index + 1]
    return None


def _section_after(lines: list[str], heading: str) -> str | None:
    compact = [line.strip() for line in lines if line.strip()]
    for index, line in enumerate(compact):
        if line.lower() == heading.lower() and index + 1 < len(compact):
            return compact[index + 1]
    return None


def _description(text: str) -> str | None:
    match = re.search(
        r"Descripción\s+(.+?)(?:Uso permitido|Uso prohibido|Documentos|Ubicación en mapa|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return " ".join(match.group(1).split())


def _minimum_price(text: str) -> str | None:
    match = re.search(
        r"Valor comercial mínimo:\s*([\d.,]+)\s*(UF|CLP|\$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return f"{match.group(2).upper()} {match.group(1)}"


def _price_amount(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"([\d.,]+)", value)
    if not match:
        return None
    return _safe_float(match.group(1).replace(".", "").replace(",", "."))


def _price_currency(value: str | None) -> str | None:
    if not value:
        return None
    if value.upper().startswith("UF"):
        return "UF"
    if value.upper().startswith("CLP") or value.startswith("$"):
        return "CLP"
    return None


def _classification_for_modality(modality: str | None) -> str:
    normalized = (modality or "").lower()
    if "arriendo" in normalized:
        return "PROPERTY_FOR_LEASE"
    if "conces" in normalized:
        return "PROPERTY_FOR_CONCESSION"
    return "PROPERTY_FOR_SALE"


def _amount_type_for_classification(classification: str) -> str:
    return {
        "PROPERTY_FOR_SALE": "MINIMUM_SALE_PRICE",
        "PROPERTY_FOR_LEASE": "LEASE_PRICE",
        "PROPERTY_FOR_CONCESSION": "CONCESSION_FEE",
    }.get(classification, "UNKNOWN_AMOUNT")


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(0) if match else None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
