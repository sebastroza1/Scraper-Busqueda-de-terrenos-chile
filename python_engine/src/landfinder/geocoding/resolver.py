from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from landfinder.geocoding.providers import (
    GeocodingProvider,
    GeocodingRequest,
    GeocodingResult,
    ManualCoordinatesProvider,
    NominatimProvider,
    SourceCoordinatesProvider,
)
from landfinder.storage.repositories import Database, GeocodingCacheRepository, PropertyRepository


@dataclass(frozen=True)
class LocationResolution:
    property_id: str
    result: GeocodingResult | None
    candidates: list[GeocodingResult]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "property_id": self.property_id,
            "result": self.result.as_dict() if self.result else None,
            "candidates": [item.as_dict() for item in self.candidates],
            "warnings": self.warnings,
        }


class GeolocationResolver:
    def __init__(
        self,
        *,
        database: Database,
        providers: list[GeocodingProvider] | None = None,
    ) -> None:
        self.database = database
        self.properties = PropertyRepository(database)
        cache = GeocodingCacheRepository(database)
        self.providers = providers or [
            SourceCoordinatesProvider(),
            NominatimProvider(cache=cache),
        ]

    async def resolve_property(
        self,
        property_id: str,
        *,
        persist: bool = True,
    ) -> LocationResolution:
        property_record = self.properties.get(property_id)
        if property_record is None:
            raise KeyError(property_id)
        request = _request_from_property(property_record)
        return await self.resolve_request(property_id, request, persist=persist)

    async def resolve_request(
        self,
        property_id: str,
        request: GeocodingRequest,
        *,
        persist: bool = True,
        assigned_by: str = "system",
    ) -> LocationResolution:
        warnings: list[str] = []
        candidates: list[GeocodingResult] = []
        for provider in self.providers:
            try:
                candidates = await provider.geocode(request)
            except NotImplementedError as exc:
                warnings.append(f"{provider.provider_id}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - one geocoder should not break the app.
                warnings.append(f"{provider.provider_id}: {type(exc).__name__}: {exc}")
                continue
            if candidates:
                break
        result = candidates[0] if candidates else None
        if result and persist:
            self.properties.update_location(
                property_id,
                latitude=result.latitude,
                longitude=result.longitude,
                location_source=result.provider,
                location_method=result.location_method,
                location_precision=result.location_precision,
                location_confidence=result.confidence,
                address=result.display_name,
                raw_result=result.raw_result,
                assigned_by=assigned_by,
            )
        return LocationResolution(
            property_id=property_id,
            result=result,
            candidates=candidates,
            warnings=warnings,
        )

    async def assign_manual(
        self,
        property_id: str,
        *,
        latitude: float,
        longitude: float,
        address: str | None = None,
        region: str | None = None,
        commune: str | None = None,
        precision: str = "EXACT",
    ) -> LocationResolution:
        request = GeocodingRequest(
            query=address,
            address=address,
            commune=commune,
            region=region,
            latitude=latitude,
            longitude=longitude,
        )
        provider = ManualCoordinatesProvider()
        candidates = await provider.geocode(request)
        result = candidates[0] if candidates else None
        if result is None:
            return LocationResolution(property_id, None, [], ["manual: invalid coordinates"])
        result = GeocodingResult(
            provider=result.provider,
            latitude=result.latitude,
            longitude=result.longitude,
            display_name=address or result.display_name,
            location_method="manual",
            location_precision=precision,
            confidence=result.confidence,
            source_url=result.source_url,
            raw_result={"level": request.level, "manual": True},
        )
        self.properties.update_location(
            property_id,
            latitude=result.latitude,
            longitude=result.longitude,
            location_source="manual",
            location_method="manual",
            location_precision=result.location_precision,
            location_confidence=result.confidence,
            address=address,
            region=region,
            commune=commune,
            raw_result=result.raw_result,
            assigned_by="user",
        )
        return LocationResolution(property_id, result, [result], [])


def _request_from_property(property_record: dict[str, Any]) -> GeocodingRequest:
    return GeocodingRequest(
        address=property_record.get("normalized_address")
        or property_record.get("original_address"),
        commune=property_record.get("commune"),
        region=property_record.get("region"),
        latitude=property_record.get("latitude"),
        longitude=property_record.get("longitude"),
    )
