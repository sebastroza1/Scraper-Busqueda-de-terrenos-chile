from __future__ import annotations

import json

import httpx
import pytest
from pyproj import Transformer

from landfinder.geospatial.admin_validator import AdministrativeLocationValidator


@pytest.mark.asyncio
async def test_admin_validator_matches_chanaral_atacama_geometry() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_boundary_payload("Atacama", "Chañaral"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AdministrativeLocationValidator(client=client).validate_property(
            {
                "region": "Atacama",
                "commune": "Chanaral",
                "latitude": -26.37,
                "longitude": -70.50,
            }
        )

    assert result.admin_validation_status == "MATCH"
    assert result.calculated_region == "Atacama"
    assert result.calculated_commune == "Chañaral"
    assert not result.blocks_territorial_analysis


@pytest.mark.asyncio
async def test_admin_validator_flags_chanaral_geometry_outside_atacama() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_boundary_payload("Antofagasta", "San Pedro de Atacama"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AdministrativeLocationValidator(client=client).validate_property(
            {
                "region": "Atacama",
                "commune": "Chanaral",
                "latitude": -22.475818,
                "longitude": -68.899098,
            }
        )

    assert result.admin_validation_status == "COMMUNE_AND_REGION_MISMATCH"
    assert result.calculated_region == "Antofagasta"
    assert result.calculated_commune == "San Pedro de Atacama"
    assert result.blocks_territorial_analysis


@pytest.mark.asyncio
async def test_admin_validator_transforms_non_4326_crs_before_lookup() -> None:
    lon, lat = -70.50, -26.37
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32719", always_xy=True)
    x, y = transformer.transform(lon, lat)
    seen_points: list[dict[str, float]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_points.append(json.loads(request.url.params["geometry"]))
        return httpx.Response(200, json=_boundary_payload("Atacama", "Chañaral"))

    geometry = {
        "type": "Point",
        "coordinates": [x, y],
        "crs": {"type": "name", "properties": {"name": "EPSG:32719"}},
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AdministrativeLocationValidator(client=client).validate_property(
            {
                "region": "Atacama",
                "commune": "Chanaral",
                "parcel_geometry": json.dumps(geometry),
            }
        )

    assert result.admin_validation_status == "MATCH"
    assert result.source_epsg == 32719
    assert result.normalized_epsg == 4326
    assert seen_points[0]["x"] == pytest.approx(lon, abs=0.000001)
    assert seen_points[0]["y"] == pytest.approx(lat, abs=0.000001)


@pytest.mark.asyncio
async def test_admin_validator_uses_cached_boundary_fallback_when_spatial_query_is_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("returnIdsOnly") == "true":
            return httpx.Response(200, json={"objectIds": [1]})
        if params.get("objectIds") == "1":
            return httpx.Response(
                200,
                json={
                    "features": [
                        {
                            "attributes": {
                                "REGION": "Atacama",
                                "COMUNA": "Chañaral",
                                "CUT_REG": "03",
                                "CUT_COM": "03201",
                            },
                            "geometry": {
                                "rings": [
                                    [
                                        [-70.6, -26.5],
                                        [-70.4, -26.5],
                                        [-70.4, -26.2],
                                        [-70.6, -26.2],
                                        [-70.6, -26.5],
                                    ]
                                ]
                            },
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"features": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AdministrativeLocationValidator(client=client).validate_property(
            {
                "region": "Atacama",
                "commune": "Chanaral",
                "latitude": -26.37,
                "longitude": -70.50,
            }
        )

    assert result.admin_validation_status == "MATCH"
    assert result.calculated_region == "Atacama"
    assert result.calculated_commune == "Chañaral"


def _boundary_payload(region: str, commune: str) -> dict[str, object]:
    return {
        "features": [
            {
                "attributes": {
                    "REGION": region,
                    "COMUNA": commune,
                    "CUT_REG": "03",
                    "CUT_COM": "03201",
                }
            }
        ]
    }
