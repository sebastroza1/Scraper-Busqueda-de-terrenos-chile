import httpx
import pytest

from landfinder.connectors.base import SearchQuery, SourceUnavailableError
from landfinder.connectors.marketplaces.mercadolibre import MercadoLibreRealEstateConnector


@pytest.mark.asyncio
async def test_mercadolibre_requires_oauth_token(monkeypatch) -> None:
    monkeypatch.delenv("MERCADOLIBRE_ACCESS_TOKEN", raising=False)

    with pytest.raises(SourceUnavailableError, match="MERCADOLIBRE_ACCESS_TOKEN"):
        await MercadoLibreRealEstateConnector().discover(SearchQuery(keywords=["terreno"]))


@pytest.mark.asyncio
async def test_mercadolibre_searches_mlc_land_categories_without_generic_keywords(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MERCADOLIBRE_ACCESS_TOKEN", "token")
    seen_search_params = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sites/MLC/categories":
            return httpx.Response(200, json=[{"id": "MLC1459", "name": "Inmuebles"}])
        if request.url.path == "/categories/MLC1459":
            return httpx.Response(
                200,
                json={
                    "id": "MLC1459",
                    "name": "Inmuebles",
                    "children_categories": [{"id": "MLC1496", "name": "Terrenos"}],
                },
            )
        if request.url.path == "/categories/MLC1496":
            return httpx.Response(
                200,
                json={"id": "MLC1496", "name": "Terrenos", "children_categories": []},
            )
        if request.url.path == "/sites/MLC/search":
            seen_search_params.append(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    "site_id": "MLC",
                    "paging": {"total": 1, "limit": 20, "offset": 0},
                    "results": [
                        {
                            "id": "MLC123",
                            "site_id": "MLC",
                            "title": "Terreno urbano en Maipu",
                            "price": 2500,
                            "currency_id": "CLF",
                            "permalink": "https://articulo.mercadolibre.cl/MLC-123",
                            "date_created": "2026-01-15T12:00:00.000Z",
                            "location": {
                                "address_line": "Av. Ejemplo 123",
                                "city": {"name": "Maipu"},
                                "state": {"name": "Metropolitana de Santiago"},
                                "geo_information": {
                                    "location": {
                                        "latitude": -33.5,
                                        "longitude": -70.7,
                                    }
                                },
                            },
                            "attributes": [
                                {
                                    "id": "LAND_AREA",
                                    "name": "Superficie de terreno",
                                    "value_struct": {"number": 10000, "unit": "m²"},
                                },
                                {
                                    "id": "COVERED_AREA",
                                    "name": "Superficie construida",
                                    "value_struct": {"number": 100, "unit": "m²"},
                                },
                            ],
                        }
                    ],
                },
            )
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.mercadolibre.com",
    ) as client:
        result = await MercadoLibreRealEstateConnector(client=client).discover(
            SearchQuery(
                keywords=["terreno", "predio"],
                extra_filters={"mercadolibre_limit": 20},
            )
        )

    assert seen_search_params == [{"limit": "20", "offset": "0", "category": "MLC1496"}]
    record = result.raw_records[0]
    assert record["external_id"] == "MLC123"
    assert record["canonical_url"] == "https://articulo.mercadolibre.cl/MLC-123"
    assert record["price_raw"] == "UF 2500"
    assert record["area_raw"] == "10000 m²"
    assert record["region_raw"] == "Metropolitana de Santiago"
    assert record["commune_raw"] == "Maipu"
    assert record["latitude"] == -33.5
    assert record["longitude"] == -70.7
    assert record["raw_payload"]["landfinder"]["location_precision"] == "APPROXIMATE_PROPERTY"


@pytest.mark.asyncio
async def test_mercadolibre_refreshes_expired_access_token(monkeypatch) -> None:
    monkeypatch.setenv("MERCADOLIBRE_ACCESS_TOKEN", "expired-token")
    monkeypatch.setenv("MERCADOLIBRE_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("MERCADOLIBRE_CLIENT_ID", "client-id")
    monkeypatch.setenv("MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT", "2020-01-01T00:00:00+00:00")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "fresh-token",
                    "refresh_token": "fresh-refresh",
                    "expires_in": 3600,
                },
            )
        if request.url.path == "/sites/MLC/categories":
            assert request.headers["authorization"] == "Bearer fresh-token"
            return httpx.Response(200, json=[{"id": "MLC1459", "name": "Inmuebles"}])
        if request.url.path == "/categories/MLC1459":
            return httpx.Response(
                200,
                json={"id": "MLC1459", "name": "Inmuebles", "children_categories": []},
            )
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.mercadolibre.com",
    ) as client:
        with pytest.raises(SourceUnavailableError, match="land category_id"):
            await MercadoLibreRealEstateConnector(client=client).discover(
                SearchQuery(extra_filters={"mercadolibre_limit": 1})
            )

    assert "fresh-token" == __import__("os").environ["MERCADOLIBRE_ACCESS_TOKEN"]
    assert "fresh-refresh" == __import__("os").environ["MERCADOLIBRE_REFRESH_TOKEN"]
