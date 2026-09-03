from __future__ import annotations

import os
from typing import Any

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

    def is_configured(self) -> bool:
        return bool(os.getenv("MERCADOLIBRE_ACCESS_TOKEN"))

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
        token = os.getenv("MERCADOLIBRE_ACCESS_TOKEN")
        return ConnectorHealth(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE if token else SourceHealthStatus.DEGRADED,
            recent_errors=[]
            if token
            else [
                (
                    "Missing MERCADOLIBRE_ACCESS_TOKEN; OAuth is required "
                    "for MVP MercadoLibre searches."
                )
            ],
            parser_version=self.parser_version,
        )

    async def discover(self, query: SearchQuery) -> ConnectorRunResult:
        token = os.getenv("MERCADOLIBRE_ACCESS_TOKEN")
        if not token:
            raise SourceUnavailableError(
                "MERCADOLIBRE_ACCESS_TOKEN is required for MercadoLibre official API searches"
            )

        category_id = query.extra_filters.get(
            "category_id"
        ) or await self._discover_real_estate_category(token)
        if not category_id:
            raise SourceUnavailableError(
                "MercadoLibre real-estate category_id could not be verified"
            )

        params: dict[str, Any] = {
            "category": category_id,
            "limit": min(int(query.extra_filters.get("limit", 50)), 100),
        }
        if query.keywords:
            params["q"] = " ".join(query.keywords)
        if query.price_min_clp is not None or query.price_max_clp is not None:
            min_price = "" if query.price_min_clp is None else str(query.price_min_clp)
            max_price = "" if query.price_max_clp is None else str(query.price_max_clp)
            params["price"] = f"{min_price}-{max_price}"

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=30,
        ) as client:
            response = await client.get(f"/sites/{self.site_id}/search", params=params)
            response.raise_for_status()
            payload = response.json()

        raw_records = [
            mercadolibre_item_to_raw(item).model_dump(mode="json")
            for item in payload.get("results", [])
        ]
        return ConnectorRunResult(
            source_id=self.source_id,
            status=SourceHealthStatus.ACTIVE,
            raw_records=raw_records,
            warnings=[
                "MercadoLibre real-estate search was executed through documented API endpoints.",
                "Geolocation precision must be checked per item.",
            ],
        )

    async def _discover_real_estate_category(self, token: str) -> str | None:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=20) as client:
            response = await client.get(f"/sites/{self.site_id}/categories")
            response.raise_for_status()
            categories = response.json()
        for category in categories:
            name = str(category.get("name", "")).lower()
            if "inmueble" in name:
                return str(category["id"])
        return None
