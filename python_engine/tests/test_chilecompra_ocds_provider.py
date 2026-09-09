from __future__ import annotations

import httpx
import pytest

from landfinder.connectors.base import SearchQuery
from landfinder.connectors.public_procurement.chilecompra_ocds import ChileCompraOCDSProvider


@pytest.mark.asyncio
async def test_chilecompra_ocds_keeps_land_demand_out_of_property_assets() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "records": [
                    {
                        "ocid": "ocds-123-4328-33-B226",
                        "compiledRelease": {
                            "ocid": "ocds-123-4328-33-B226",
                            "id": "4328-33-B226",
                            "buyer": {"name": "Institucion publica"},
                            "tender": {
                                "id": "4328-33-B226",
                                "title": "ADQUISICION TERRENO TIUQUILEMU",
                                "description": (
                                    "Institucion requiere adquirir terreno en sector "
                                    "Tiuquilemu, comuna de Niquen."
                                ),
                                "items": [
                                    {
                                        "description": "Adquisicion de terreno",
                                        "classification": {"description": "Inmuebles"},
                                    }
                                ],
                                "value": {"amount": 100000000, "currency": "CLP"},
                            },
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ChileCompraOCDSProvider(client=client).discover(
            SearchQuery(search_sources=["chilecompra_ocds"], keywords=["terreno"])
        )

    assert result.raw_records == []
    assert len(result.audit_records) == 1
    assert result.audit_records[0]["automatic_classification"] == "LAND_DEMAND"
    assert result.audit_records[0]["amount_type"] == "PROCUREMENT_BUDGET"


@pytest.mark.asyncio
async def test_chilecompra_ocds_emits_land_sale_process_as_candidate() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "records": [
                    {
                        "ocid": "ocds-123-4295-54-LR26",
                        "compiledRelease": {
                            "ocid": "ocds-123-4295-54-LR26",
                            "id": "4295-54-LR26",
                            "buyer": {"name": "Municipalidad"},
                            "tender": {
                                "id": "4295-54-LR26",
                                "title": "VENTA DE TERRENOS DE PROPIEDAD MUNICIPAL LA SERENA",
                                "description": "Proceso de venta de terrenos municipales.",
                                "items": [
                                    {
                                        "description": "Venta de terrenos comerciales",
                                        "classification": {
                                            "description": "Venta de propiedades"
                                        },
                                    }
                                ],
                            },
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ChileCompraOCDSProvider(client=client).discover(
            SearchQuery(search_sources=["chilecompra_ocds"], keywords=["terrenos"])
        )

    assert len(result.raw_records) == 1
    assert len(result.audit_records) == 1
    assert result.audit_records[0]["automatic_classification"] == "LAND_SALE_PROCESS"


@pytest.mark.asyncio
async def test_chilecompra_ocds_expands_monthly_index_records_before_classifying() -> None:
    seen_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if "listaOCDSAgnoMes" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "ocid": "ocds-70d2nz-4328-33-B226",
                            "urlTender": "http://api.mercadopublico.cl/APISOCDS/OCDS/tender/4328-33-B226",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "ocid": "ocds-70d2nz-4328-33-B226",
                        "id": "release-draft-4328-33-B226",
                        "date": "2026-01-01T09:00:00Z",
                        "tender": {
                            "id": "4328-33-B226",
                            "title": "BORRADOR DE SERVICIO MUNICIPAL",
                            "description": "Version preliminar reemplazada.",
                        },
                    },
                    {
                        "ocid": "ocds-70d2nz-4328-33-B226",
                        "id": "release-4328-33-B226",
                        "date": "2026-01-02T09:00:00Z",
                        "parties": [
                            {
                                "name": "Municipalidad de Niquen",
                                "id": "CL-MP-4328",
                                "roles": ["buyer", "procuringEntity"],
                            }
                        ],
                        "tender": {
                            "id": "4328-33-B226",
                            "title": "ADQUISICION TERRENO TIUQUILEMU",
                            "description": "Compra de terreno para equipamiento municipal.",
                            "items": [{"description": "Adquisicion de terreno"}],
                            "value": {"amount": 50000000, "currency": "CLP"},
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ChileCompraOCDSProvider(client=client).discover(
            SearchQuery(
                search_sources=["chilecompra_ocds"],
                keywords=["terreno"],
                extra_filters={"ocds_year": 2020, "ocds_month": 1, "ocds_start": 0, "ocds_end": 1},
            )
        )

    assert result.raw_records == []
    assert len(result.audit_records) == 1
    assert result.audit_records[0]["automatic_classification"] == "LAND_DEMAND"
    assert result.audit_records[0]["organization"] == "Municipalidad de Niquen"
    assert any(
        url.startswith("https://api.mercadopublico.cl/APISOCDS/OCDS/tender/")
        for url in seen_urls
    )
