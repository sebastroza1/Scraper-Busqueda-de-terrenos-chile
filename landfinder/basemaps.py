from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BasemapConfig:
    key: str
    label: str
    provider: str
    tiles: str
    attribution: str
    max_zoom: int
    max_native_zoom: int
    fallback_tiles: str
    fallback_attribution: str
    fallback_max_native_zoom: int
    css_filter: str | None = None


OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = "&copy; OpenStreetMap contributors"

BASEMAPS = {
    "Claro": BasemapConfig(
        key="Claro",
        label="Claro",
        provider="OpenStreetMap Standard",
        tiles=OSM_TILES,
        attribution=OSM_ATTRIBUTION,
        max_zoom=19,
        max_native_zoom=19,
        fallback_tiles=OSM_TILES,
        fallback_attribution=OSM_ATTRIBUTION,
        fallback_max_native_zoom=19,
    ),
    "Oscuro": BasemapConfig(
        key="Oscuro",
        label="Oscuro",
        provider="OpenStreetMap Standard",
        tiles=OSM_TILES,
        attribution=OSM_ATTRIBUTION,
        max_zoom=19,
        max_native_zoom=19,
        fallback_tiles=OSM_TILES,
        fallback_attribution=OSM_ATTRIBUTION,
        fallback_max_native_zoom=19,
        css_filter="invert(92%) hue-rotate(180deg) brightness(76%) contrast(92%) saturate(70%)",
    ),
}


def basemap_for_theme(theme: str) -> BasemapConfig:
    return BASEMAPS.get(theme, BASEMAPS["Oscuro"])


def looks_like_empty_esri_tile(status_code: int, content_length: int, zoom: int) -> bool:
    return status_code == 200 and zoom > 16 and content_length <= 3000
