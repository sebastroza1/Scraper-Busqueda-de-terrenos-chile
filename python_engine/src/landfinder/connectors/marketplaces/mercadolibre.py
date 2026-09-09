from __future__ import annotations

import os
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from landfinder.connectors.base import (
    ConnectorHealth,
    ConnectorRunResult,
    SearchQuery,
    SearchSource,
    SourceAuditResult,
    SourceUnavailableError,
)
from landfinder.connectors.transforms import mercadolibre_item_to_raw
from landfinder.core.windows_secrets import write_windows_secret
from landfinder.models.enums import (
    ConnectorStrategy,
    SourceAuditStatus,
    SourceHealthStatus,
    SourceType,
)


class MercadoLibreRealEstateConnector(SearchSource):
    source_id = "mercadolibre_real_estate"
    source_name = "MercadoLibre / PortalInmobiliario Real Estate"
    source_type = SourceType.MARKETPLACE
    strategy = ConnectorStrategy.OFFICIAL_API
    parser_version = "0.1.0"

    base_url = "https://api.mercadolibre.com"
    site_id = "MLC"
    real_estate_root_category_id = "MLC1459"
    chile_item_location = "lat:-56.0_-17.5,lon:-76.0_-66.0"
    land_category_terms = (
        "terreno",
        "terrenos",
        "sitio",
        "sitios",
        "parcela",
        "parcelas",
        "lote",
        "lotes",
        "loteo",
        "loteos",
        "macrolote",
        "macrolotes",
        "agricola",
        "agricolas",
        "industrial",
        "rural",
        "suelo",
    )
    _category_cache: tuple[datetime, list[dict[str, str]]] | None = None

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def is_configured(self) -> bool:
        return bool(
            os.getenv("MERCADOLIBRE_ACCESS_TOKEN")
            or os.getenv("MERCADOLIBRE_REFRESH_TOKEN")
        )

    async def audit_source(self) -> SourceAuditResult:
        return SourceAuditResult(
            source_id=self.source_id,
            source_name=self.source_name,
            source_type=self.source_type,
            official_url="https://developers.mercadolibre.cl/",
            strategy=self.strategy,
            status=SourceAuditStatus.PARTIAL,
            api_available=True,
            authentication="OAuth access token required by MercadoLibre APIs.",
            rate_limits="Use MercadoLibre platform limits and backoff. Exact quota TO_VERIFY.",
            terms_notes="Use documented API only. Do not scrape or bypass protections.",
            obtainable_fields=[
                "id",
                "title",
                "price",
                "currency_id",
                "permalink",
                "seller",
                "location",
                "attributes",
                "pictures",
            ],
            geolocation="Location fields and bounding-box search documented; precision varies.",
            images="Pictures available in item payload where API permits.",
            references=[
                "https://developers.mercadolibre.cl/en_us/api-docs/items-and-searches",
                "https://developers.mercadolibre.cl/es_cl/localizar-inmuebles",
                "https://developers.mercadolibre.cl/publica-inmueble",
            ],
            notes=(
                "The Chilean real-estate category IDs and PortalInmobiliario search parity "
                "must be validated with a real OAuth token before production use."
            ),
        )

    async def health(self) -> ConnectorHealth:
        recent_errors: list[str] = []
        try:
            token = await self._access_token()
        except SourceUnavailableError as exc:
            token = None
            recent_errors.append(str(exc))
        return ConnectorHealth(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE if token else SourceHealthStatus.DEGRADED,
            recent_errors=recent_errors
            if recent_errors
            else (
                []
                if token
                else [
                    (
                        "Missing MERCADOLIBRE_ACCESS_TOKEN; OAuth is required "
                        "for MVP MercadoLibre searches."
                    )
                ]
            ),
            parser_version=self.parser_version,
        )

    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        token = await self._access_token()
        if not token:
            raise SourceUnavailableError(
                "MERCADOLIBRE_ACCESS_TOKEN is required, or MERCADOLIBRE_REFRESH_TOKEN "
                "with MERCADOLIBRE_CLIENT_ID for automatic refresh"
            )

        category_ids = await self._land_category_ids(token, query)
        if not category_ids:
            raise SourceUnavailableError(
                "MercadoLibre land category_id could not be verified for site MLC"
            )

        requested_limit = int(
            query.extra_filters.get("mercadolibre_limit")
            or query.extra_filters.get("limit")
            or 50
        )
        total_limit = max(1, min(requested_limit, 100))
        use_keywords = bool(query.extra_filters.get("mercadolibre_use_keywords", False))
        base_params: dict[str, Any] = {}
        if use_keywords and query.keywords:
            base_params["q"] = " ".join(query.keywords)
        if query.price_min_clp is not None or query.price_max_clp is not None:
            min_price = "" if query.price_min_clp is None else str(query.price_min_clp)
            max_price = "" if query.price_max_clp is None else str(query.price_max_clp)
            base_params["price"] = f"{min_price}-{max_price}"

        if not _marketplace_global_enabled(query):
            return await self._discover_partner_sellers(
                token=token,
                query=query,
                categories=category_ids,
                total_limit=total_limit,
            )

        preflight_error = await self._marketplace_search_preflight(token)
        if preflight_error is not None:
            return ConnectorRunResult(
                source_id=self.source_id,
                status=SourceHealthStatus.DEGRADED,
                raw_records=[],
                warnings=[
                    "MERCADO LIBRE DIAGNOSTICO",
                    "OAuth/User ............ OK",
                    "Root MLC1459 .......... HTTP 200",
                    f"Search root ........... HTTP {preflight_error.status_code}",
                    "MARKETPLACE_GLOBAL: UNAVAILABLE_FOR_APP",
                    "API_RESULTS: 0",
                    "RAW_RECORDS: 0",
                    "LAND_CANDIDATES: 0",
                    "ACCEPTED: 0",
                    preflight_error.sanitized_message,
                ],
            )

        raw_records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        warnings: list[str] = []
        api_results = 0
        non_land_rejected = 0
        category_diagnostics = [
            f"{category.get('name') or category['id']} -> {category['id']}"
            for category in category_ids
        ]
        paging: dict[str, Any] | None = None
        for category in category_ids:
            if len(raw_records) >= total_limit:
                break
            category_id = category["id"]
            limit = min(50, total_limit - len(raw_records))
            try:
                payload = await self._search_category(
                    token=token,
                    category_id=category_id,
                    category_name=category.get("name", ""),
                    params={**base_params, "limit": limit, "offset": 0},
                )
            except MercadoLibreSearchError as exc:
                warnings.append(exc.sanitized_message)
                if exc.status_code == 401:
                    raise SourceUnavailableError(exc.sanitized_message) from exc
                if exc.status_code == 403:
                    continue
                continue
            paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else paging
            results = payload.get("results", [])
            api_results += len(results)
            total = paging.get("total") if paging else len(results)
            warnings.append(
                f"MercadoLibre category search: {category.get('name') or category_id} "
                f"-> HTTP 200 -> {total} resultados"
            )
            for item in results:
                item_id = str(item.get("id") or "")
                if item_id and item_id not in seen_ids:
                    raw = mercadolibre_item_to_raw(
                        {
                            **item,
                            "landfinder_category": category,
                        }
                    )
                    landfinder = raw.raw_payload.get("landfinder", {})
                    if (
                        isinstance(landfinder, dict)
                        and landfinder.get("property_land_type") == "NON_LAND_PROPERTY"
                    ):
                        non_land_rejected += 1
                        continue
                    raw_records.append(raw.model_dump(mode="json"))
                    seen_ids.add(item_id)
                if len(raw_records) >= total_limit:
                    break

        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE
            if raw_records or not warnings
            else SourceHealthStatus.DEGRADED,
            raw_records=raw_records,
            warnings=[
                (
                    "MercadoLibre land search was executed through documented API endpoints "
                    f"for site {self.site_id}."
                ),
                "API_RESULTS: " + str(api_results),
                "RAW_RECORDS: " + str(len(raw_records)),
                "LAND_CANDIDATES: " + str(len(raw_records)),
                "NON_LAND_REJECTED: " + str(non_land_rejected),
                "ACCEPTED: " + str(len(raw_records)),
                "MercadoLibre category ids used: "
                f"{', '.join(category['id'] for category in category_ids)}.",
                "MercadoLibre categories resolved: " + "; ".join(category_diagnostics),
                f"MercadoLibre paging total: {paging.get('total') if paging else 'unknown'}.",
                "Geolocation precision must be checked per item.",
                *warnings,
            ],
        )

    async def _discover_partner_sellers(
        self,
        *,
        token: str,
        query: SearchQuery,
        categories: list[dict[str, str]],
        total_limit: int,
    ) -> ConnectorRunResult:
        sellers = _partner_seller_ids(query)
        category_ids = {category["id"] for category in categories}
        categories_by_id = {category["id"]: category for category in categories}
        warnings = [
            "MERCADO LIBRE DIAGNOSTICO",
            "MARKETPLACE_GLOBAL: UNAVAILABLE_FOR_APP",
            "MERCADOLIBRE_PARTNER_SELLERS: ENABLED",
            "MercadoLibre categories resolved: "
            + "; ".join(
                f"{category.get('name') or category['id']} -> {category['id']}"
                for category in categories
            ),
        ]
        if not sellers:
            warnings.extend(
                [
                    "Sellers conectados: 0",
                    "API_RESULTS: 0",
                    "RAW_RECORDS: 0",
                    "LAND_CANDIDATES: 0",
                    "ACCEPTED: 0",
                    "Configura MERCADOLIBRE_PARTNER_SELLER_IDS para usar seller mode.",
                ]
            )
            return ConnectorRunResult(
                source_id=self.source_id,
                status=SourceHealthStatus.DEGRADED,
                raw_records=[],
                warnings=warnings,
            )

        raw_records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        api_results = 0
        non_land_rejected = 0
        for seller_id in sellers:
            if len(raw_records) >= total_limit:
                break
            seller_response = await self._seller_items_search(
                token=token,
                seller_id=seller_id,
                limit=min(50, total_limit),
            )
            if seller_response.status_code >= 400:
                message = _seller_warning(seller_id, seller_response)
                warnings.append(message)
                if seller_response.status_code == 401:
                    raise SourceUnavailableError(message)
                continue
            payload = seller_response.json()
            ids = [str(item) for item in payload.get("results", []) if item]
            api_results += len(ids)
            warnings.append(
                f"Seller {seller_id} -> HTTP 200 -> {len(ids)} item ids"
            )
            for chunk in _chunks(ids, 20):
                if len(raw_records) >= total_limit:
                    break
                bulk_response = await self._bulk_items(token, chunk)
                if bulk_response.status_code >= 400:
                    warnings.append(_bulk_warning(chunk, bulk_response))
                    continue
                for entry in bulk_response.json():
                    body = entry.get("body") if isinstance(entry, dict) else None
                    if not isinstance(body, dict):
                        continue
                    category_id = str(body.get("category_id") or "")
                    if category_id not in category_ids:
                        continue
                    item_id = str(body.get("id") or "")
                    if item_id and item_id in seen_ids:
                        continue
                    raw = mercadolibre_item_to_raw(
                        {
                            **body,
                            "landfinder_category": categories_by_id.get(
                                category_id,
                                {"id": category_id, "name": category_id, "path": category_id},
                            ),
                        }
                    )
                    landfinder = raw.raw_payload.get("landfinder", {})
                    if (
                        isinstance(landfinder, dict)
                        and landfinder.get("property_land_type") == "NON_LAND_PROPERTY"
                    ):
                        non_land_rejected += 1
                        continue
                    raw_records.append(raw.model_dump(mode="json"))
                    seen_ids.add(item_id)
                    if len(raw_records) >= total_limit:
                        break

        warnings.extend(
            [
                f"Sellers conectados: {len(sellers)}",
                f"API_RESULTS: {api_results}",
                f"RAW_RECORDS: {len(raw_records)}",
                f"LAND_CANDIDATES: {len(raw_records)}",
                f"NON_LAND_REJECTED: {non_land_rejected}",
                f"ACCEPTED: {len(raw_records)}",
            ]
        )
        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE
            if raw_records
            else SourceHealthStatus.DEGRADED,
            raw_records=raw_records,
            warnings=warnings,
        )

    async def _seller_items_search(
        self,
        *,
        token: str,
        seller_id: str,
        limit: int,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"}
        params = {"status": "active", "limit": limit, "offset": 0}
        if self._client is not None:
            return await self._client.get(
                f"/users/{seller_id}/items/search",
                params=params,
                headers=headers,
            )
        async with httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30) as client:
            return await client.get(f"/users/{seller_id}/items/search", params=params)

    async def _bulk_items(self, token: str, item_ids: list[str]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "ids": ",".join(item_ids),
            "attributes": (
                "body.id,body.title,body.subtitle,body.category_id,body.price,"
                "body.currency_id,body.permalink,body.seller_id,body.seller,"
                "body.official_store_id,"
                "body.location,body.attributes,"
                "body.pictures,body.thumbnail,body.date_created,body.start_time,"
                "body.last_updated,body.site_id"
            ),
        }
        if self._client is not None:
            return await self._client.get("/items/bulk", params=params, headers=headers)
        async with httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30) as client:
            return await client.get("/items/bulk", params=params)

    async def _marketplace_search_preflight(
        self,
        token: str,
    ) -> MercadoLibreSearchError | None:
        try:
            await self._search_category(
                token=token,
                category_id=self.real_estate_root_category_id,
                category_name="Inmuebles",
                params={"limit": 1, "offset": 0},
            )
        except MercadoLibreSearchError as exc:
            if exc.status_code == 403:
                return MercadoLibreSearchError(
                    status_code=403,
                    sanitized_message=(
                        "MARKETPLACE_SEARCH_FORBIDDEN: "
                        f"{exc.sanitized_message}"
                    ),
                )
            raise
        return None

    async def _search_category(
        self,
        *,
        token: str,
        category_id: str,
        category_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        query_params = {**params, "category": category_id}
        attempted_params = query_params
        response = await self._search_request(token, attempted_params)
        if response.status_code == 403 and "item_location" not in query_params:
            attempted_params = {
                **query_params,
                "item_location": self.chile_item_location,
            }
            response = await self._search_request(token, attempted_params)
        if response.status_code >= 400:
            raise MercadoLibreSearchError(
                status_code=response.status_code,
                sanitized_message=(
                    "MercadoLibre search failed: "
                    f"status={response.status_code}; "
                    f"endpoint={self._sanitized_search_endpoint(attempted_params)}; "
                    f"category_id={category_id}; "
                    f"category_name={category_name}; "
                    f"message={_safe_response_message(response)}"
                ),
            )
        return response.json()

    async def _search_request(
        self,
        token: str,
        params: dict[str, Any],
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"}
        if self._client is not None:
            return await self._client.get(
                f"/sites/{self.site_id}/search",
                params=params,
                headers=headers,
            )
        async with httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30) as client:
            return await client.get(f"/sites/{self.site_id}/search", params=params)

    def _sanitized_search_endpoint(self, params: dict[str, Any]) -> str:
        return f"/sites/{self.site_id}/search?{urlencode(params)}"

    async def _land_category_ids(
        self,
        token: str,
        query: SearchQuery,
    ) -> list[dict[str, str]]:
        explicit = (
            query.extra_filters.get("mercadolibre_category_ids")
            or query.extra_filters.get("mercadolibre_category_id")
            or query.extra_filters.get("category_id")
        )
        if isinstance(explicit, str) and explicit.strip():
            return [
                {"id": item.strip(), "name": item.strip(), "path": item.strip()}
                for item in explicit.split(",")
                if item.strip()
            ]
        if isinstance(explicit, list):
            return [
                {"id": str(item).strip(), "name": str(item).strip(), "path": str(item).strip()}
                for item in explicit
                if str(item).strip()
            ]
        cached = self._category_cache
        if cached and cached[0] > datetime.now(UTC):
            return cached[1]
        root_id = await self._discover_real_estate_category(token)
        categories = await self._land_leaf_categories(token, root_id)
        self._category_cache = (datetime.now(UTC) + timedelta(minutes=15), categories)
        return categories

    async def _discover_real_estate_category(self, token: str) -> str | None:
        return self.real_estate_root_category_id

    async def _land_leaf_categories(self, token: str, root_id: str) -> list[dict[str, str]]:
        headers = {"Authorization": f"Bearer {token}"}
        matches: list[dict[str, str]] = []
        if self._client is not None:
            await self._collect_land_leaf_categories(
                self._client,
                root_id,
                [],
                matches,
                headers,
            )
            return matches
        async with httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=20) as client:
            await self._collect_land_leaf_categories(client, root_id, [], matches, None)
        return matches

    async def _collect_land_leaf_categories(
        self,
        client: httpx.AsyncClient,
        category_id: str,
        path: list[str],
        matches: list[dict[str, str]],
        headers: dict[str, str] | None,
    ) -> None:
        response = await client.get(f"/categories/{category_id}", headers=headers)
        response.raise_for_status()
        payload = response.json()
        name = str(payload.get("name") or "")
        current_path = [*path, name]
        haystack = _normalize_text(" ".join(current_path))
        if category_id != self.real_estate_root_category_id and any(
            term in haystack for term in self.land_category_terms
        ):
            matches.append({"id": category_id, "name": name, "path": " > ".join(current_path)})
            return
        children = payload.get("children_categories") or []
        if not children:
            return
        for child in children:
            child_id = str(child.get("id") or "")
            if child_id:
                await self._collect_land_leaf_categories(
                    client,
                    child_id,
                    current_path,
                    matches,
                    headers,
                )

    async def _access_token(self) -> str | None:
        token = os.getenv("MERCADOLIBRE_ACCESS_TOKEN")
        if token and not _token_needs_refresh():
            return token
        refresh_token = os.getenv("MERCADOLIBRE_REFRESH_TOKEN")
        client_id = os.getenv("MERCADOLIBRE_CLIENT_ID")
        if not refresh_token or not client_id:
            return token
        refreshed = await self._refresh_token(
            client_id=client_id,
            client_secret=os.getenv("MERCADOLIBRE_CLIENT_SECRET"),
            refresh_token=refresh_token,
        )
        return refreshed or token

    async def _refresh_token(
        self,
        *,
        client_id: str,
        refresh_token: str,
        client_secret: str | None,
    ) -> str | None:
        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }
        if client_secret:
            payload["client_secret"] = client_secret
        if self._client is not None:
            response = await self._client.post("/oauth/token", data=payload)
        else:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=20) as client:
                response = await client.post("/oauth/token", data=payload)
        if response.status_code >= 400:
            raise SourceUnavailableError(
                "MercadoLibre OAuth refresh failed; reconnect the account."
            )
        decoded = response.json()
        access_token = str(decoded.get("access_token") or "")
        new_refresh_token = str(decoded.get("refresh_token") or "")
        expires_in = int(decoded.get("expires_in") or 0)
        if not access_token:
            raise SourceUnavailableError("MercadoLibre OAuth refresh did not return access token.")
        os.environ["MERCADOLIBRE_ACCESS_TOKEN"] = access_token
        write_windows_secret("MERCADOLIBRE_ACCESS_TOKEN", access_token)
        if new_refresh_token:
            os.environ["MERCADOLIBRE_REFRESH_TOKEN"] = new_refresh_token
            write_windows_secret("MERCADOLIBRE_REFRESH_TOKEN", new_refresh_token)
        if expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
            os.environ["MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT"] = expires_at.isoformat()
            write_windows_secret(
                "MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT",
                expires_at.isoformat(),
            )
        return access_token


class MercadoLibreSearchError(RuntimeError):
    def __init__(self, *, status_code: int, sanitized_message: str) -> None:
        super().__init__(sanitized_message)
        self.status_code = status_code
        self.sanitized_message = sanitized_message


def _token_needs_refresh() -> bool:
    expires_raw = os.getenv("MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT")
    if not expires_raw:
        return False
    try:
        expires_at = datetime.fromisoformat(expires_raw)
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC) + timedelta(minutes=10)


def _safe_response_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    text = str(payload).replace("\n", " ").replace("\r", " ")
    return text[:240]


def _marketplace_global_enabled(query: SearchQuery) -> bool:
    explicit = query.extra_filters.get("mercadolibre_marketplace_global_enabled")
    if explicit is not None:
        return _truthy(explicit)
    return _truthy(os.getenv("MERCADOLIBRE_MARKETPLACE_GLOBAL_ENABLED"))


def _partner_seller_ids(query: SearchQuery) -> list[str]:
    explicit = query.extra_filters.get("mercadolibre_partner_seller_ids")
    if explicit is None:
        explicit = os.getenv("MERCADOLIBRE_PARTNER_SELLER_IDS")
    if isinstance(explicit, list):
        return [str(item).strip() for item in explicit if str(item).strip()]
    return [item.strip() for item in str(explicit or "").split(",") if item.strip()]


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _seller_warning(seller_id: str, response: httpx.Response) -> str:
    return (
        f"Seller {seller_id} -> HTTP {response.status_code} -> "
        f"{_safe_response_message(response)}"
    )


def _bulk_warning(item_ids: list[str], response: httpx.Response) -> str:
    return (
        f"/items/bulk ids={len(item_ids)} -> HTTP {response.status_code} -> "
        f"{_safe_response_message(response)}"
    )


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.replace("\ufffd", " ").lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(without_accents.split())
