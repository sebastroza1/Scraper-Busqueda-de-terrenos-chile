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
    "supermarket": {"label": "Supermercado", "color": "#FF7A1A", "glyph": "cart"},
    "park": {"label": "Parque", "color": "#10B981", "glyph": "tree"},
    "education": {"label": "Universidad / educación superior", "color": "#7C3AED", "glyph": "cap"},
    "school": {"label": "Colegio / escuela", "color": "#FBBF24", "glyph": "school"},
    "terrain": {"label": "Terreno / lote", "color": "#10B981", "glyph": "lot"},
    "risk": {"label": "Riesgo", "color": "#FF3F4A", "glyph": "!"},
    "wetland": {"label": "Humedal", "color": "#2563EB", "glyph": "W"},
    "protected": {"label": "Área protegida", "color": "#22C55E", "glyph": "A"},
    "mop": {"label": "Obras MOP", "color": "#FF7A1A", "glyph": "M"},
    "seia": {"label": "Proyecto SEIA", "color": "#8B5CF6", "glyph": "S"},
    "health": {"label": "Salud / establecimiento", "color": "#EC407A", "glyph": "+"},
    "mall": {"label": "Mall / centro comercial", "color": "#EC407A", "glyph": "bag"},
    "fuel": {"label": "Bencinera", "color": "#2563EB", "glyph": "fuel"},
    "water": {"label": "Agua / hidrografía", "color": "#06B6D4", "glyph": "~"},
    "industrial": {"label": "Zona industrial", "color": "#64748B", "glyph": "I"},
    "selected_location": {"label": "Ubicación seleccionada", "color": "#2563EB", "glyph": ""},
    "construction": {"label": "Construcción OSM", "color": "#FF7A1A", "glyph": "build"},
}


def icon_config(key: str) -> dict[str, Any]:
    return ICON_REGISTRY.get(key, ICON_REGISTRY["terrain"])


def glyph_svg(glyph: str, color: str) -> str:
    if glyph == "cart":
        return f"<path d='M15 15h4l2.4 9.2h10.3l2-6.4H22.2' fill='none' stroke='{color}' stroke-width='2.7' stroke-linecap='round' stroke-linejoin='round'/><circle cx='23' cy='29' r='2' fill='{color}'/><circle cx='32' cy='29' r='2' fill='{color}'/>"
    if glyph == "tree":
        return f"<path d='M24 11c-4.5 0-8 3.7-8 8.1 0 3.7 2.4 6.5 6 7.5v5.2h4v-5.2c3.6-1 6-3.8 6-7.5 0-4.4-3.5-8.1-8-8.1Z' fill='{color}'/><path d='M19 21h10M24 16v15' stroke='white' stroke-width='1.7' stroke-linecap='round'/>"
    if glyph == "cap":
        return f"<path d='M13 19l11-6 11 6-11 6-11-6Z' fill='{color}'/><path d='M18 22v5c4 3 8 3 12 0v-5' fill='none' stroke='{color}' stroke-width='2.5' stroke-linecap='round'/><path d='M34 20v7' stroke='{color}' stroke-width='2.2' stroke-linecap='round'/>"
    if glyph == "bag":
        return f"<path d='M16 18h16l-1.2 15H17.2L16 18Z' fill='{color}'/><path d='M20 18c0-4 8-4 8 0' fill='none' stroke='white' stroke-width='2.2' stroke-linecap='round'/>"
    if glyph == "fuel":
        return f"<path d='M18 13h10v20H18z' fill='{color}'/><path d='M20 16h6v5h-6z' fill='white'/><path d='M28 17l5 5v8c0 2-3 2-3 0v-5' fill='none' stroke='{color}' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'/>"
    if glyph == "build":
        return f"<path d='M16 29h16v4H16z' fill='{color}'/><path d='M18 16h4v13h-4zM26 13h4v16h-4z' fill='{color}'/><path d='M15 20h18' stroke='{color}' stroke-width='2.2' stroke-linecap='round'/><path d='M21 16l5-5h8' fill='none' stroke='{color}' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'/>"
    if glyph == "lot":
        return f"<path d='M15 16l15-4 4 16-15 4-4-16Z' fill='none' stroke='{color}' stroke-width='2.7' stroke-linejoin='round'/><path d='M20 15l4 15M28 13l4 14' stroke='{color}' stroke-width='1.8'/>"
    if glyph == "school":
        return f"<path d='M14 22l10-8 10 8v11H14V22Z' fill='{color}'/><path d='M20 33v-8h8v8' fill='white'/><path d='M24 14v-4' stroke='{color}' stroke-width='2' stroke-linecap='round'/>"
    if glyph == "+":
        return f"<path d='M21 12h6v8h8v6h-8v8h-6v-8h-8v-6h8z' fill='{color}'/>"
    if glyph == "!":
        return f"<path d='M24 12l12 22H12L24 12Z' fill='{color}'/><path d='M24 19v7' stroke='white' stroke-width='2.6' stroke-linecap='round'/><circle cx='24' cy='30' r='1.7' fill='white'/>"
    if glyph == "~":
        return f"<path d='M15 22c4-4 8 4 12 0s8 4 12 0M15 29c4-4 8 4 12 0s8 4 12 0' fill='none' stroke='{color}' stroke-width='2.8' stroke-linecap='round'/>"
    text = escape(glyph)
    return (
        f"<text x='24' y='24' text-anchor='middle' font-family='Arial, sans-serif' "
        f"font-size='14' font-weight='900' fill='{color}'>{text}</text>"
    )


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
            f"{glyph_svg(glyph, color)}"
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
