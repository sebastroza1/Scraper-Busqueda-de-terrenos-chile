import pytest

from landfinder.geocoding.providers import GeocodingRequest, NominatimProvider


class NullCache:
    def get(self, cache_key: str):
        return None

    def set(self, **kwargs) -> None:
        raise AssertionError("generic geocoding should not write a cache entry")


@pytest.mark.asyncio
async def test_nominatim_rejects_country_only_property_geocoding() -> None:
    provider = NominatimProvider(cache=NullCache())

    results = await provider.geocode(GeocodingRequest(query="Chile"))

    assert results == []


@pytest.mark.asyncio
async def test_nominatim_rejects_commune_only_property_geocoding() -> None:
    provider = NominatimProvider(cache=NullCache())

    results = await provider.geocode(GeocodingRequest(commune="Los Andes"))

    assert results == []
