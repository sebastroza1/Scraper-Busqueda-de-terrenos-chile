from __future__ import annotations

from html import escape
from typing import Any

import folium


ICON_REGISTRY: dict[str, dict[str, Any]] = {
    "metro_current": {"label": "Metro actual", "color": "#FF3F4A", "glyph": "M"},
    "metro_future": {"label": "Metro futuro", "color": "#1E90FF", "glyph": "M", "dashed": True},
    "metro_station": {"label": "Estación de metro", "color": "#FF3F4A", "glyph": "M"},
    "home": {"label": "Casa / vivienda", "color": "#2563EB", "glyph": "H"},
    "building": {"label": "Edificio / departamento", "color": "#8B5CF6", "glyph": "B"},
    "hospital": {"label": "Hospital / clínica", "color": "#FF3F4A", "glyph": "+"},
    "pharmacy": {"label": "Farmacia", "color": "#10B981", "glyph": "+"},
    "supermarket": {"label": "Supermercado", "color": "#FF7A1A", "glyph": "S"},
    "park": {"label": "Parque", "color": "#10B981", "glyph": "P"},
    "education": {"label": "Universidad / educación superior", "color": "#7C3AED", "glyph": "U"},
    "school": {"label": "Colegio / escuela", "color": "#FBBF24", "glyph": "E"},
    "terrain": {"label": "Terreno / lote", "color": "#10B981", "glyph": "T"},
    "risk": {"label": "Riesgo", "color": "#FF3F4A", "glyph": "!"},
    "wetland": {"label": "Humedal", "color": "#2563EB", "glyph": "W"},
    "protected": {"label": "Área protegida", "color": "#22C55E", "glyph": "A"},
    "mop": {"label": "Obras MOP", "color": "#FF7A1A", "glyph": "M"},
    "seia": {"label": "Proyecto SEIA", "color": "#8B5CF6", "glyph": "S"},
    "health": {"label": "Salud / establecimiento", "color": "#EC407A", "glyph": "+"},
    "mall": {"label": "Mall / centro comercial", "color": "#EC407A", "glyph": "C"},
    "fuel": {"label": "Bencinera", "color": "#2563EB", "glyph": "F"},
    "water": {"label": "Agua / hidrografía", "color": "#06B6D4", "glyph": "~"},
    "industrial": {"label": "Zona industrial", "color": "#64748B", "glyph": "I"},
    "selected_location": {"label": "Ubicación seleccionada", "color": "#2563EB", "glyph": ""},
    "construction": {"label": "Construcción OSM", "color": "#FF7A1A", "glyph": "!"},
}


def icon_config(key: str) -> dict[str, Any]:
    return ICON_REGISTRY.get(key, ICON_REGISTRY["terrain"])


def marker_svg(key: str, size: int = 38) -> str:
    cfg = icon_config(key)
    color = cfg["color"]
    glyph = escape(str(cfg.get("glyph") or ""))
    inner = ""
    if key == "selected_location":
        inner = (
            "<circle cx='24' cy='19' r='7' fill='white' opacity='.96'/>"
            f"<circle cx='24' cy='19' r='3.5' fill='{color}'/>"
        )
    else:
        inner = (
            "<circle cx='24' cy='19' r='11' fill='white' opacity='.96'/>"
            f"<text x='24' y='24' text-anchor='middle' font-family='Arial, sans-serif' "
            f"font-size='14' font-weight='900' fill='{color}'>{glyph}</text>"
        )
    dash = "stroke-dasharray='4 3'" if cfg.get("dashed") else ""
    return (
        f"<svg width='{size}' height='{size + 10}' viewBox='0 0 48 58' xmlns='http://www.w3.org/2000/svg'>"
        "<filter id='s' x='-30%' y='-20%' width='160%' height='160%'>"
        "<feDropShadow dx='0' dy='5' stdDeviation='4' flood-opacity='.28'/></filter>"
        f"<path d='M24 4C13 4 5 12.4 5 23.1c0 14.5 19 30.9 19 30.9s19-16.4 19-30.9C43 12.4 35 4 24 4Z' "
        f"fill='{color}' stroke='white' stroke-width='2.5' {dash} filter='url(#s)'/>"
        f"{inner}</svg>"
    )


def marker_icon(key: str, size: int = 38) -> folium.DivIcon:
    return folium.DivIcon(
        icon_size=(size, size + 10),
        icon_anchor=(size // 2, size + 8),
        popup_anchor=(0, -size),
        html=f"<div class='lf-marker-icon'>{marker_svg(key, size)}</div>",
    )


def legend_symbol_html(key: str) -> str:
    cfg = icon_config(key)
    return (
        "<span style='display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;'>"
        f"{marker_svg(key, 22)}</span>"
    )


def panel_icon_html(key: str) -> str:
    cfg = icon_config(key)
    glyph = escape(str(cfg.get("glyph") or ""))
    return (
        f"<span style='display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;"
        f"border-radius:7px;background:{cfg['color']}22;color:{cfg['color']};font-weight:900;"
        f"border:1px solid {cfg['color']}55;font-size:12px;'>{glyph}</span>"
    )
