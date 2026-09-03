import pytest

from landfinder.connectors.base import SearchQuery, SourceUnavailableError
from landfinder.connectors.marketplaces.mercadolibre import MercadoLibreRealEstateConnector


@pytest.mark.asyncio
async def test_mercadolibre_requires_oauth_token(monkeypatch) -> None:
    monkeypatch.delenv("MERCADOLIBRE_ACCESS_TOKEN", raising=False)

    with pytest.raises(SourceUnavailableError, match="MERCADOLIBRE_ACCESS_TOKEN"):
        await MercadoLibreRealEstateConnector().discover(SearchQuery(keywords=["terreno"]))
