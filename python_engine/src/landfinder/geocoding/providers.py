from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx

from landfinder.storage.repositories import GeocodingCacheRepository, utc_now


@dataclass(frozen=True)
class GeocodingRequest:
    query: str | None = None
    address: str | None = None
    commune: str | None = None
    region: str | None = None
    country: str = "Chile"
    latitude: float | None = None
    longitude: float | None = None

    @property
    def search_text(self) -> str:
        parts = [self.address, self.commune, self.region, self.country]
        if self.query:
            parts = [self.query, self.country]
        return ", ".join(str(part).strip() for part in parts if str(part or "").strip())

    @property
    def level(self) -> int:
        if self.latitude is not None and self.longitude is not None:
            return 1
        if self.address and self.commune:
            return 3
        if self.address:
            return 2
        if self.commune and self.region:
            return 6
        if self.commune:
            return 6
        if self.region:
            return 7
        return 5


@dataclass(frozen=True)
class GeocodingResult:
    provider: str
    latitude: float
    longitude: float
    display_name: str
    location_method: str
    location_precision: str
    confidence: float
    source_url: str | None = None
    raw_result: dict[str, Any] = field(default_factory=dict)
    cached: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "display_name": self.display_name,
            "location_method": self.location_method,
            "location_precision": self.location_precision,
            "confidence": self.confidence,
            "source_url": self.source_url,
            "raw_result": self.raw_result,
            "cached": self.cached,
        }


class GeocodingProvider:
    provider_id = "base"

    async def geocode(self, request: GeocodingRequest) -> list[GeocodingResult]:
        raise NotImplementedError


class SourceCoordinatesProvider(GeocodingProvider):
    provider_id = "source_coordinates"

    async def geocode(self, request: GeocodingRequest) -> list[GeocodingResult]:
        if request.latitude is None or request.longitude is None:
            return []
        if not _valid_lat_lon(request.latitude, request.longitude):
            return []
        return [
            GeocodingResult(
                provider=self.provider_id,
                latitude=request.latitude,
                longitude=request.longitude,
                display_name=request.search_text or "Coordenadas de fuente",
                location_method="source_coordinates",
                location_precision="EXACT_COORDINATES",
                confidence=0.7,
                raw_result={"level": request.level},
            )
        ]


class ManualCoordinatesProvider(GeocodingProvider):
    provider_id = "manual"

    async def geocode(self, request: GeocodingRequest) -> list[GeocodingResult]:
        if request.latitude is None or request.longitude is None:
            return []
        if not _valid_lat_lon(request.latitude, request.longitude):
            return []
        return [
            GeocodingResult(
                provider=self.provider_id,
                latitude=request.latitude,
                longitude=request.longitude,
                display_name=request.search_text or "Ubicacion manual",
                location_method="manual",
                location_precision="EXACT",
                confidence=0.98,
                raw_result={"level": request.level},
            )
        ]


class VisicomGeocoderProvider(GeocodingProvider):
    provider_id = "visicom"

    async def geocode(self, request: GeocodingRequest) -> list[GeocodingResult]:
        api_key = os.getenv("VISICOM_API_KEY")
        if not api_key:
            return []
        raise NotImplementedError(
            "Visicom geocoding is reserved for a verified project reference/API contract."
        )


class NominatimProvider(GeocodingProvider):
    provider_id = "nominatim"
    endpoint = "https://nominatim.openstreetmap.org/search"

    _lock = asyncio.Lock()
    _last_request_at = 0.0

    def __init__(
        self,
        *,
        cache: GeocodingCacheRepository,
        user_agent: str = "LandfinderChile/0.1 local prototype contact=local",
        min_interval_seconds: float = 1.1,
    ) -> None:
        self.cache = cache
        self.user_agent = user_agent
        self.min_interval_seconds = min_interval_seconds

    async def geocode(self, request: GeocodingRequest) -> list[GeocodingResult]:
        query_text = request.search_text
        if not query_text:
            return []
        if _is_too_generic_for_property_geocoding(request):
            return []
        normalized = normalize_query(query_text)
        cache_key = cache_key_for(self.provider_id, normalized)
        cached = self.cache.get(cache_key)
        if cached and cached.get("latitude") is not None and cached.get("longitude") is not None:
            return [
                GeocodingResult(
                    provider=self.provider_id,
                    latitude=float(cached["latitude"]),
                    longitude=float(cached["longitude"]),
                    display_name=str(cached.get("display_name") or query_text),
                    location_method=str(cached.get("location_method") or "geocoded"),
                    location_precision=str(cached.get("location_precision") or "APPROXIMATE"),
                    confidence=float(cached.get("confidence") or 0),
                    source_url=cached.get("source_url"),
                    raw_result=cached.get("response") or {},
                    cached=True,
                )
            ]

        params = {
            "q": query_text,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": "5",
            "countrycodes": "cl",
        }
        payload = await self._request(params)
        results = [
            _result_from_nominatim(item, request) for item in payload if isinstance(item, dict)
        ]
        results = [item for item in results if item is not None]
        first = results[0] if results else None
        self.cache.set(
            cache_key=cache_key,
            provider=self.provider_id,
            query_text=query_text,
            normalized_query=normalized,
            request=params,
            response={"items": payload},
            latitude=first.latitude if first else None,
            longitude=first.longitude if first else None,
            display_name=first.display_name if first else None,
            location_precision=first.location_precision if first else "UNKNOWN",
            location_method=first.location_method if first else "geocoded",
            confidence=first.confidence if first else 0,
            source_url=first.source_url if first else self.endpoint,
            expires_at=utc_now() + timedelta(days=180),
        )
        return results

    async def _request(self, params: dict[str, str]) -> list[Any]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            elapsed = loop.time() - self._last_request_at
            if elapsed < self.min_interval_seconds:
                await asyncio.sleep(self.min_interval_seconds - elapsed)
            async with httpx.AsyncClient(
                timeout=20, headers={"User-Agent": self.user_agent}
            ) as client:
                response = await client.get(self.endpoint, params=params)
                response.raise_for_status()
                self.__class__._last_request_at = loop.time()
                payload = response.json()
        return payload if isinstance(payload, list) else []


def cache_key_for(provider: str, normalized_query: str) -> str:
    return hashlib.sha256(f"{provider}:{normalized_query}".encode()).hexdigest()


def normalize_query(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"\s+", " ", ascii_text.lower()).strip()
    return ascii_text


def result_from_cache(row: dict[str, Any]) -> GeocodingResult | None:
    if row.get("latitude") is None or row.get("longitude") is None:
        return None
    return GeocodingResult(
        provider=str(row.get("provider") or "cache"),
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        display_name=str(row.get("display_name") or row.get("query_text") or ""),
        location_method=str(row.get("location_method") or "geocoded"),
        location_precision=str(row.get("location_precision") or "UNKNOWN"),
        confidence=float(row.get("confidence") or 0),
        source_url=row.get("source_url"),
        raw_result=row.get("response") or {},
        cached=True,
    )


def _result_from_nominatim(
    item: dict[str, Any],
    request: GeocodingRequest,
) -> GeocodingResult | None:
    lat = _safe_float(item.get("lat"))
    lon = _safe_float(item.get("lon"))
    if lat is None or lon is None or not _valid_lat_lon(lat, lon):
        return None
    precision = _precision_from_request_and_result(request, item)
    return GeocodingResult(
        provider="nominatim",
        latitude=lat,
        longitude=lon,
        display_name=str(item.get("display_name") or request.search_text),
        location_method="geocoded",
        location_precision=precision,
        confidence=_confidence_for_precision(precision, item),
        source_url="https://www.openstreetmap.org",
        raw_result={"level": request.level, "nominatim": _compact_json(item)},
    )


def _precision_from_request_and_result(request: GeocodingRequest, item: dict[str, Any]) -> str:
    osm_type = str(item.get("type") or item.get("class") or "").lower()
    if request.level <= 3 and any(
        token in osm_type for token in ("house", "building", "residential")
    ):
        return "VERIFIED_ADDRESS"
    if request.level <= 3:
        return "STREET_ADDRESS"
    if request.level == 6:
        return "COMMUNE_ONLY"
    if request.level == 7:
        return "REGION_ONLY"
    return "COUNTRY_ONLY"


def _confidence_for_precision(precision: str, item: dict[str, Any]) -> float:
    importance = _safe_float(item.get("importance")) or 0
    if precision in {"VERIFIED_ADDRESS", "EXACT_COORDINATES"}:
        return min(0.85, 0.62 + importance / 3)
    if precision in {"STREET_ADDRESS", "SECTOR"}:
        return min(0.72, 0.55 + importance / 4)
    if precision in {"COMMUNE_ONLY", "REGION_ONLY", "COUNTRY_ONLY"}:
        return min(0.62, 0.45 + importance / 4)
    return min(0.7, 0.5 + importance / 4)


def _is_too_generic_for_property_geocoding(request: GeocodingRequest) -> bool:
    normalized = normalize_query(request.search_text)
    generic = {
        "",
        "chile",
        "region de chile",
        "region chile",
    }
    if normalized in generic:
        return True
    if request.level >= 5:
        return True
    address = normalize_query(request.address or "")
    if address in generic:
        return True
    if not address:
        return True
    return False


def _compact_json(value: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=True, default=str)
    if len(text) <= 6000:
        return value
    return {
        "place_id": value.get("place_id"),
        "display_name": value.get("display_name"),
        "lat": value.get("lat"),
        "lon": value.get("lon"),
        "class": value.get("class"),
        "type": value.get("type"),
        "importance": value.get("importance"),
    }


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_lat_lon(latitude: float, longitude: float) -> bool:
    return -90 <= latitude <= 90 and -180 <= longitude <= 180
