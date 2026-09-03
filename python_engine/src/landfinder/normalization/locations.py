from __future__ import annotations

from dataclasses import dataclass

from landfinder.catalog.chile import COMMUNES_BY_REGION
from landfinder.catalog.chile import REGIONS as CATALOG_REGIONS
from landfinder.normalization.parsers import normalize_key

REGIONS = {region["legacy_code"]: region["name"] for region in CATALOG_REGIONS}

COMMUNE_TO_REGION = {
    normalize_key(commune): region["name"]
    for region in CATALOG_REGIONS
    for commune in COMMUNES_BY_REGION.get(region["code"], [])
}


@dataclass(frozen=True)
class NormalizedLocation:
    region: str | None
    province: str | None
    commune: str | None
    confidence: float


def normalize_region(value: str | None) -> str | None:
    if not value:
        return None
    key = normalize_key(value)
    for region in REGIONS.values():
        if normalize_key(region) == key:
            return region
    for code, region in REGIONS.items():
        if normalize_key(code) == key:
            return region
    return None


def normalize_commune(value: str | None) -> tuple[str | None, str | None, float]:
    if not value:
        return None, None, 0.0
    key = normalize_key(value)
    region = COMMUNE_TO_REGION.get(key)
    if not region:
        return value.strip(), None, 0.35
    canonical = " ".join(part.capitalize() for part in key.split())
    replacements = {"Nunoa": "Nunoa", "Vina Del Mar": "Vina del Mar"}
    return replacements.get(canonical, canonical), region, 0.9


def normalize_location(
    *,
    region: str | None = None,
    province: str | None = None,
    commune: str | None = None,
) -> NormalizedLocation:
    normalized_region = normalize_region(region)
    normalized_commune, commune_region, commune_confidence = normalize_commune(commune)
    return NormalizedLocation(
        region=normalized_region or commune_region,
        province=province.strip() if province else None,
        commune=normalized_commune,
        confidence=max(0.5 if normalized_region else 0.0, commune_confidence),
    )
