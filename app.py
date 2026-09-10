from __future__ import annotations

import json
import math
import time
from datetime import datetime
from typing import Any

import folium
import pandas as pd
import requests
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium

from landfinder.basemaps import basemap_for_theme
from landfinder.config import USER_AGENT, source_config
from landfinder.filter_model import build_source_plan
from landfinder.map_engine import load_map_source
from landfinder.metro_adapter import metro_area_summary, metro_current_for_area, metro_future_for_area
from landfinder.probes import health_state, probe_source
from landfinder.registry import load_sources
from landfinder.storage import load_history, save_result
from landfinder.urban_value import (
    ASSET_TYPES,
    CURRENT_LINE_ORDER,
    FUTURE_LINE_ORDER,
    METRO_COLORS,
    haversine_m,
    query_built_assets,
    query_osm_construction,
)


SOURCES = load_sources()
SOURCE_BY_ID = {source["id"]: source for source in SOURCES}

AREA_COLORS = ["#1473E6", "#16A36A", "#E74C5B", "#8E44AD", "#F39C12"]
SANTIAGO_CENTER = (-33.4489, -70.6693)
RM_BOUNDS = {
    "south": -33.95,
    "north": -33.05,
    "west": -71.25,
    "east": -70.10,
}

COMMUNE_GAZETTEER = {
    "santiago": (-33.4489, -70.6693, 12),
    "nunoa": (-33.4569, -70.5978, 13),
    "ñuñoa": (-33.4569, -70.5978, 13),
    "providencia": (-33.4263, -70.6170, 13),
    "las condes": (-33.4088, -70.5674, 12),
    "vitacura": (-33.4001, -70.5980, 12),
    "la reina": (-33.4478, -70.5345, 12),
    "macul": (-33.4850, -70.5992, 12),
    "san miguel": (-33.5007, -70.6514, 13),
    "estacion central": (-33.4628, -70.6998, 13),
    "estación central": (-33.4628, -70.6998, 13),
    "quinta normal": (-33.4297, -70.6992, 13),
    "renca": (-33.4066, -70.7283, 12),
    "cerrillos": (-33.5024, -70.7163, 12),
    "maipu": (-33.5108, -70.7562, 12),
    "maipú": (-33.5108, -70.7562, 12),
    "la florida": (-33.5227, -70.5982, 12),
    "puente alto": (-33.6117, -70.5758, 12),
}

ADDRESS_FALLBACKS = {
    "santa raquel 8204": (-33.5623, -70.60053, 16, "Santa Raquel 8204, La Florida, Santiago"),
    "av santa raquel 8204": (-33.5623, -70.60053, 16, "Santa Raquel 8204, La Florida, Santiago"),
    "avenida santa raquel 8204": (-33.5623, -70.60053, 16, "Santa Raquel 8204, La Florida, Santiago"),
}

TERRITORY_LAYER_IDS = [
    "minvu_limites_urbanos",
    "minvu_prms_uso_suelo",
    "ide_hidrografia",
    "dga_derechos",
]

RISK_LAYER_IDS = [
    "minvu_area_riesgo",
    "dga_prohibiciones",
    "mma_humedales",
    "mma_areas_protegidas",
    "senapred_tsunami",
    "sernageomin_relaves",
]

FUTURE_GIS_IDS = {
    "seia": "sea_proyectos",
    "mop": "mop_contratos_obras",
}

LAYER_DISPLAY_NAMES = {
    "built": "Equipamiento actual",
    "metro_current": "Metro actual",
    "metro_future": "Metro futuro",
    "mop_red_vial": "MOP · Red Vial",
    "osm_construction": "Construcciones OSM",
}


class CenterSantiagoControl(MacroElement):
    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var centerControl = L.control({position: "bottomright"});
        centerControl.onAdd = function(map) {
          var wrap = L.DomUtil.create("div", "lf-center-control");
          wrap.innerHTML = "<button type='button'>Centrar Santiago</button>";
          L.DomEvent.disableClickPropagation(wrap);
          L.DomEvent.on(wrap, "click", function(event) {
            L.DomEvent.stop(event);
            map.setView([{{ this.lat }}, {{ this.lon }}], {{ this.zoom }});
          });
          return wrap;
        };
        centerControl.addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, lat: float, lon: float, zoom: int) -> None:
        super().__init__()
        self.lat = lat
        self.lon = lon
        self.zoom = zoom


class BasemapFallbackControl(MacroElement):
    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var primaryLayer = {{ this.primary_layer }};
        var fallbackActive = false;
        var errorCount = 0;
        var fallbackNotice = null;
        primaryLayer.on("loading", function() {
          console.debug("[Landfinder][tile] BASEMAP:", "{{ this.provider }}", "event: loading");
        });
        primaryLayer.on("load", function() {
          console.debug("[Landfinder][tile] BASEMAP:", "{{ this.provider }}", "event: load");
        });
        primaryLayer.on("tileload", function(event) {
          var coords = event.coords || {};
          console.debug("[Landfinder][tile] BASEMAP:", "{{ this.provider }}", "zoom:", coords.z, "tile:", coords.x + "/" + coords.y, "status: success");
        });
        primaryLayer.on("tileerror", function(event) {
          var coords = event.coords || {};
          errorCount += 1;
          console.warn("[Landfinder][tile] BASEMAP:", "{{ this.provider }}", "zoom:", coords.z, "tile:", coords.x + "/" + coords.y, "status: error");
          if (!fallbackActive && errorCount >= {{ this.error_threshold }}) {
            fallbackActive = true;
            {{ this._parent.get_name() }}.removeLayer(primaryLayer);
            L.tileLayer("{{ this.fallback_tiles }}", {
              attribution: "{{ this.fallback_attribution }}",
              maxZoom: {{ this.max_zoom }},
              maxNativeZoom: {{ this.fallback_max_native_zoom }},
            }).addTo({{ this._parent.get_name() }});
            fallbackNotice = L.control({position: "topright"});
            fallbackNotice.onAdd = function() {
              var el = L.DomUtil.create("div", "lf-basemap-fallback");
              el.innerHTML = "Mapa base alternativo activo";
              return el;
            };
            fallbackNotice.addTo({{ this._parent.get_name() }});
          }
        });
        {% endmacro %}
        """
    )

    def __init__(
        self,
        primary_layer: str,
        provider: str,
        fallback_tiles: str,
        fallback_attribution: str,
        max_zoom: int,
        fallback_max_native_zoom: int,
        error_threshold: int = 3,
    ) -> None:
        super().__init__()
        self.primary_layer = primary_layer
        self.provider = provider
        self.fallback_tiles = fallback_tiles
        self.fallback_attribution = fallback_attribution
        self.max_zoom = max_zoom
        self.fallback_max_native_zoom = fallback_max_native_zoom
        self.error_threshold = error_threshold


st.set_page_config(
    page_title="Landfinder Chile",
    page_icon="LF",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
<style>
:root {
  --lf-ink:#EAF2FF;
  --lf-ink-2:#BFD1E8;
  --lf-line:#24364D;
  --lf-bg:#08111F;
  --lf-panel:#101B2A;
  --lf-muted:#91A4BC;
  --lf-blue:#1473E6;
  --lf-green:#16A36A;
  --lf-red:#E74C5B;
  --lf-cyan:#18C5D8;
}

.stApp {
  background: var(--lf-bg);
  color: var(--lf-ink);
}

[data-testid="stHeader"] {
  background: rgba(8,17,31,.94);
}

section[data-testid="stSidebar"] {
  display: none;
}

.block-container {
  padding: .75rem .9rem 1rem;
  max-width: 100%;
}

div[data-testid="stHorizontalBlock"] {
  gap: .65rem;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--lf-panel);
  border: 1px solid var(--lf-line) !important;
  border-radius: 8px;
  box-shadow: 0 14px 28px rgba(0,0,0,.22);
}

.stButton > button {
  border-radius: 8px;
  border: 1px solid #2B4059;
  font-weight: 750;
  min-height: 38px;
  background: #172437 !important;
  color: #EAF2FF !important;
}

.stFormSubmitButton > button {
  border-radius: 8px;
  border: 1px solid #0969E8 !important;
  font-weight: 750;
  min-height: 38px;
  background: #0969E8 !important;
  color: #FFFFFF !important;
}

.stFormSubmitButton > button * {
  color: #FFFFFF !important;
}

.stButton > button[kind="primary"] {
  background: #0969E8 !important;
  color: #FFFFFF !important;
  border-color: #0969E8 !important;
}

.stButton > button:disabled,
.stButton > button[disabled] {
  background: #EEF3F8 !important;
  color: #62758A !important;
  border-color: #D7E2EE !important;
  opacity: 1;
}

.stMarkdown, .stMarkdown p, label, span, p {
  color: #EAF2FF;
}

input,
textarea,
div[data-baseweb="input"],
div[data-baseweb="textarea"] {
  background: #0D1726 !important;
  color: #EAF2FF !important;
  border-color: #2B4059 !important;
}

input::placeholder,
textarea::placeholder {
  color: #99A9BC !important;
  opacity: 1 !important;
}

div[data-baseweb="select"] > div {
  background: #0D1726 !important;
  color: #EAF2FF !important;
  border-color: #2B4059 !important;
}

div[data-testid="stMetric"] {
  background: #0D1726;
  border: 1px solid #24364D;
  border-radius: 8px;
  padding: 10px 12px;
}

div[data-testid="stExpander"] {
  border-color: #24364D;
  border-radius: 8px;
  background: #101B2A;
}

div[data-testid="stExpander"] details summary,
div[data-testid="stExpander"] details summary *,
div[data-testid="stExpander"] button,
div[data-testid="stExpander"] button * {
  background: #101B2A !important;
  color: #EAF2FF !important;
  border-color: transparent !important;
}

div[data-testid="stAlert"] {
  background: #102A45 !important;
  color: #D9ECFF !important;
  border: 1px solid #24537D !important;
}

div[data-testid="stAlert"] * {
  color: #D9ECFF !important;
}

.lf-shell {
  background: linear-gradient(100deg,#071426 0%,#0E2B49 100%);
  color: #fff;
  border-radius: 8px;
  padding: 12px 18px;
  display: grid;
  grid-template-columns: minmax(260px, 340px) 1fr minmax(210px, 260px);
  align-items: center;
  gap: 16px;
  box-shadow: 0 16px 36px rgba(0,0,0,.32);
  margin-bottom: 8px;
  min-height: 64px;
}

.lf-brand {
  display: flex;
  gap: 10px;
  align-items: center;
}

.lf-logo {
  width: 42px;
  height: 30px;
  background: linear-gradient(135deg,#18C5D8,#1473E6);
  clip-path: polygon(0 100%,24% 35%,44% 100%,61% 10%,100% 100%);
}

.lf-brand-title {
  font-size: 19px;
  font-weight: 900;
  line-height: 1.25;
  letter-spacing: 0;
  padding-top: 3px;
}

.lf-brand-sub {
  color: #BFE7F1;
  font-size: 12px;
  margin-top: 2px;
}

.lf-nav {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #FFFFFF;
  white-space: nowrap;
}

.lf-map-wrap {
  position: relative;
}

.lf-map-hint {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  padding: 7px 10px;
  border-radius: 8px;
  background: #0D1726;
  border: 1px solid #24364D;
  color: #BFD1E8;
  font-size: 12px;
}

.lf-section-title {
  font-size: 11px;
  font-weight: 850;
  letter-spacing: .02em;
  text-transform: uppercase;
  color: #91A4BC;
  margin: 8px 0 4px;
}

.lf-area-row {
  border-left: 4px solid var(--area-color);
  border-radius: 8px;
  border: 1px solid #24364D;
  background: #0D1726;
  padding: 8px;
  margin: 6px 0;
}

.lf-area-row.is-active {
  box-shadow: 0 0 0 1px var(--area-color), 0 10px 22px rgba(0,0,0,.18);
}

.lf-area-meta {
  color: #91A4BC;
  font-size: 12px;
}

.lf-summary-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #24364D;
  font-size: 13px;
}

.lf-summary-row:last-child {
  border-bottom: 0;
}

.lf-summary-row span {
  color: #91A4BC;
}

.lf-summary-row b {
  color: #EAF2FF;
  text-align: right;
}

.lf-nav span {
  color: #FFFFFF;
}

.lf-avatar {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg,#1473E6,#7D86FF);
  color: #fff;
  font-weight: 850;
  margin-left: 8px;
}

.lf-panel-title {
  font-weight: 900;
  color: #EAF2FF;
  font-size: 15px;
  margin-bottom: 2px;
}

.lf-muted {
  color: #91A4BC;
  font-size: 12px;
}

.lf-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 2px 0 8px;
}

.lf-chip {
  color:#fff;
  font-weight:800;
  border-radius:8px;
  padding:8px 11px;
  box-shadow:0 5px 14px rgba(0,0,0,.13);
  line-height:1.05;
}

.lf-pill {
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:5px 8px;
  border-radius:999px;
  background:#172437;
  color:#D9ECFF;
  font-size:12px;
  font-weight:700;
  margin:2px 3px 2px 0;
}

.lf-source-state {
  border-left:4px solid #1473E6;
  background:#0D1726;
  padding:8px 10px;
  border-radius:6px;
  margin:5px 0;
  font-size:12px;
}

.lf-next {
  background:#0D1726;
  border:1px dashed #344B66;
  color:#BFD1E8;
  border-radius:8px;
  padding:12px;
}

.lf-map-loading {
  background: linear-gradient(135deg, rgba(7,20,38,.96), rgba(12,40,68,.96));
  border: 1px solid #24537D;
  color: #EAF2FF;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 8px;
  box-shadow: 0 14px 28px rgba(0,0,0,.28);
}

.lf-map-loading strong {
  color: #FFFFFF;
}

div[role="radiogroup"] {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

div[role="radiogroup"] label,
div[role="radiogroup"] div[role="radio"],
button[role="radio"][data-variant="pills"] {
  background: #172437;
  color: #EAF2FF;
  border: 1px solid #2B4059;
  border-radius: 8px;
  padding: 7px 10px;
}

div[role="radiogroup"] label *,
div[role="radiogroup"] div[role="radio"] *,
button[role="radio"][data-variant="pills"] * {
  color: #EAF2FF !important;
}

div[role="radiogroup"] label:has(input:checked),
div[role="radiogroup"] div[role="radio"][aria-checked="true"],
button[role="radio"][data-variant="pills"][aria-checked="true"],
button[role="radio"][data-variant="pills"][data-selected="true"] {
  background: #0969E8 !important;
  border-color: #0969E8 !important;
  color: #FFFFFF !important;
}

div[role="radiogroup"] label:has(input:checked) *,
div[role="radiogroup"] div[role="radio"][aria-checked="true"] *,
button[role="radio"][data-variant="pills"][aria-checked="true"] *,
button[role="radio"][data-variant="pills"][data-selected="true"] * {
  color: #FFFFFF !important;
}

div[data-testid="stPills"] button {
  background: #172437 !important;
  color: #EAF2FF !important;
  border: 1px solid #2B4059 !important;
  border-radius: 8px !important;
  min-height: 38px;
}

div[data-testid="stPills"] button[aria-selected="true"] {
  background: #0969E8 !important;
  color: #FFFFFF !important;
  border-color: #0969E8 !important;
}

div[data-testid="stPills"] button[aria-selected="true"] * {
  color: #FFFFFF !important;
}

@media (max-width: 1100px) {
  .lf-shell {
    grid-template-columns: 1fr;
  }
  .lf-nav {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

@media (min-width: 1101px) {
  .main .block-container {
    overflow: hidden;
  }
}

#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
</style>
""",
    unsafe_allow_html=True,
)


def source_label(source_id: str) -> str:
    source = SOURCE_BY_ID.get(source_id, {})
    return source.get("map_label") or source.get("name") or source_id


def normalize_query(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def parse_coordinates(text: str) -> tuple[float, float] | None:
    cleaned = text.replace(";", ",").replace(" ", "")
    if "," not in cleaned:
        return None
    parts = cleaned.split(",", 1)
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        return None
    if -56 <= lat <= -17 and -76 <= lon <= -66:
        return lat, lon
    return None


def looks_like_address(text: str) -> bool:
    key = normalize_query(text)
    street_tokens = [
        "av.",
        "avenida",
        "calle",
        "pasaje",
        "camino",
        "ruta",
        "autopista",
        "pje",
        "los ",
        "las ",
    ]
    return any(char.isdigit() for char in key) or any(token in key for token in street_tokens)


def in_rm_bounds(lat: float, lon: float) -> bool:
    return (
        RM_BOUNDS["south"] <= lat <= RM_BOUNDS["north"]
        and RM_BOUNDS["west"] <= lon <= RM_BOUNDS["east"]
    )


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def geocode_address(text: str) -> tuple[float, float, int, str] | None:
    raw_query = text.strip()
    if not raw_query:
        return None
    normalized = normalize_query(raw_query)
    for key, fallback in ADDRESS_FALLBACKS.items():
        if key in normalized:
            return fallback
    address_query = looks_like_address(raw_query)
    queries = [raw_query]
    if address_query and not any(normalize_query(name) in normalized for name in COMMUNE_GAZETTEER):
        queries = [
            f"{raw_query}, La Florida, Santiago, Chile",
            f"{raw_query}, Santiago, Región Metropolitana, Chile",
            f"{raw_query}, Región Metropolitana, Chile",
            raw_query,
        ]
    queries = [query if "chile" in normalize_query(query) else f"{query}, Chile" for query in queries]

    candidates: list[tuple[float, float, int, str]] = []
    try:
        for query in queries:
            params: dict[str, Any] = {
                "q": query,
                "format": "jsonv2",
                "limit": 5,
                "countrycodes": "cl",
                "addressdetails": 1,
            }
            if address_query:
                params.update(
                    {
                        "bounded": 1,
                        "viewbox": f"{RM_BOUNDS['west']},{RM_BOUNDS['north']},{RM_BOUNDS['east']},{RM_BOUNDS['south']}",
                    }
                )
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params=params,
                timeout=8,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            response.raise_for_status()
            for result in response.json():
                try:
                    lat = float(result["lat"])
                    lon = float(result["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                if address_query and not in_rm_bounds(lat, lon):
                    continue
                label = result.get("display_name") or raw_query
                candidates.append((lat, lon, 16 if address_query else 13, label))
            if candidates:
                break
    except Exception:
        return None
    return candidates[0] if candidates else None


def resolve_search(text: str) -> tuple[float, float, int, str] | None:
    coords = parse_coordinates(text)
    if coords:
        return coords[0], coords[1], 15, "coordenadas"

    if looks_like_address(text):
        geocoded = geocode_address(text)
        if geocoded:
            return geocoded

    key = normalize_query(text)
    for name, (lat, lon, zoom) in COMMUNE_GAZETTEER.items():
        if normalize_query(name) in key or key in normalize_query(name):
            return lat, lon, zoom, name.title()
    return geocode_address(text)


def compact_place_label(label: str, max_length: int = 96) -> str:
    if len(label) <= max_length:
        return label
    parts = [part.strip() for part in label.split(",") if part.strip()]
    if len(parts) >= 3:
        short = ", ".join(parts[:3])
        if len(short) <= max_length:
            return short
    return label[: max_length - 1].rstrip() + "…"


def clean_source_error(error: str | None) -> str:
    if not error:
        return ""
    if "OpenStreetMap/Overpass no respondió" in error:
        return error
    if "overpass" in error.lower() or "HTTPSConnectionPool" in error:
        return (
            "OpenStreetMap/Overpass no respondió a tiempo. "
            "Puedes reintentar o continuar con fuentes SEIA, MOP, MINVU y territorio."
        )
    if len(error) > 180:
        return error[:177].rstrip() + "..."
    return error


def render_theme_overrides() -> None:
    light = st.session_state.get("page_theme") == "Claro"
    if light:
        css = """
        <style>
        :root {
          --lf-ink:#172033;
          --lf-ink-2:#334155;
          --lf-line:#D8E1EC;
          --lf-bg:#F3F6FA;
          --lf-panel:#FFFFFF;
          --lf-panel-2:#F7F9FC;
          --lf-muted:#65758B;
          --lf-primary:#1677E8;
          --lf-primary-hover:#1265C7;
          --lf-selected:#EFF6FF;
        }
        .stApp { background: var(--lf-bg); color: var(--lf-ink); }
        [data-testid="stHeader"] { background: rgba(243,246,250,.95); }
        .lf-shell,
        .lf-shell *,
        .lf-brand-title,
        .lf-nav,
        .lf-nav span {
          color: #FFFFFF !important;
        }
        .lf-brand-sub { color: #BFE7F1 !important; }
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stMetric"],
        div[data-testid="stExpander"] {
          background: var(--lf-panel) !important;
          border-color: var(--lf-line) !important;
          box-shadow: 0 10px 24px rgba(31,57,88,.08) !important;
        }
        .stMarkdown, .stMarkdown p, label, span, p,
        .lf-panel-title { color: var(--lf-ink) !important; }
        .lf-muted { color: var(--lf-muted) !important; }
        input, textarea, div[data-baseweb="input"], div[data-baseweb="textarea"],
        div[data-baseweb="select"] > div {
          background: var(--lf-panel-2) !important;
          color: var(--lf-ink) !important;
          border-color: var(--lf-line) !important;
          box-shadow: none !important;
        }
        input:hover, textarea:hover,
        div[data-baseweb="input"]:hover,
        div[data-baseweb="textarea"]:hover,
        div[data-baseweb="select"] > div:hover {
          border-color: #B7C6D8 !important;
        }
        input:focus, textarea:focus,
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="textarea"]:focus-within,
        div[data-baseweb="select"]:focus-within > div {
          border-color: var(--lf-primary) !important;
          box-shadow: 0 0 0 3px rgba(22,119,232,.12) !important;
        }
        input::placeholder, textarea::placeholder { color: #94A3B8 !important; }
        .stButton > button {
          background: var(--lf-panel-2) !important;
          color: var(--lf-ink) !important;
          border-color: var(--lf-line) !important;
        }
        .stButton > button:hover {
          border-color: #B7C6D8 !important;
          background: #F1F6FC !important;
        }
        .stButton > button[kind="primary"],
        .stFormSubmitButton > button {
          background: var(--lf-primary) !important;
          color: #FFFFFF !important;
          border-color: var(--lf-primary) !important;
        }
        .stButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button:hover {
          background: var(--lf-primary-hover) !important;
          border-color: var(--lf-primary-hover) !important;
        }
        .lf-source-state, .lf-next {
          background: var(--lf-panel-2) !important;
          color: var(--lf-ink) !important;
          border-color: var(--lf-line) !important;
        }
        .lf-map-hint,
        .lf-area-row {
          background: var(--lf-panel) !important;
          color: var(--lf-ink) !important;
          border-color: var(--lf-line) !important;
        }
        .lf-area-row.is-active {
          background: var(--lf-selected) !important;
        }
        .lf-section-title,
        .lf-area-meta,
        .lf-summary-row span {
          color: var(--lf-muted) !important;
        }
        .lf-summary-row {
          border-bottom-color: var(--lf-line) !important;
        }
        .lf-summary-row b {
          color: var(--lf-ink) !important;
        }
        div[role="radiogroup"] label,
        div[role="radiogroup"] div[role="radio"],
        button[role="radio"][data-variant="pills"],
        div[data-testid="stPills"] button {
          background: var(--lf-panel-2) !important;
          color: var(--lf-ink) !important;
          border-color: var(--lf-line) !important;
        }
        div[role="radiogroup"] label *,
        div[role="radiogroup"] div[role="radio"] *,
        button[role="radio"][data-variant="pills"] *,
        div[data-testid="stPills"] button * {
          color: var(--lf-ink) !important;
        }
        div[data-testid="stPills"] button[aria-selected="true"],
        button[role="radio"][data-variant="pills"][aria-checked="true"],
        button[role="radio"][data-variant="pills"][data-selected="true"] {
          background: var(--lf-primary) !important;
          color: #FFFFFF !important;
          border-color: var(--lf-primary) !important;
        }
        div[data-testid="stPills"] button[aria-selected="true"] *,
        button[role="radio"][data-variant="pills"][aria-checked="true"] *,
        button[role="radio"][data-variant="pills"][data-selected="true"] * {
          color: #FFFFFF !important;
        }
        </style>
        """
    else:
        css = """
        <style>
        :root {
          --lf-ink:#EAF2FF;
          --lf-ink-2:#BFD1E8;
          --lf-line:#24364D;
          --lf-bg:#08111F;
          --lf-panel:#101B2A;
          --lf-muted:#91A4BC;
        }
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)


def init_state() -> None:
    defaults: dict[str, Any] = {
        "profile": {
            "name": "Sebastián",
            "email": "demo@landfinder.cl",
            "company": "Landfinder Chile",
            "role": "Planificador",
            "plan": "Free",
        },
        "workspace": {"name": "Workspace personal", "project": "Exploración territorial"},
        "areas": [],
        "active_area_id": None,
        "map_bundle": {},
        "api_results": {},
        "source_cache": {},
        "source_status": {},
        "source_circuits": {},
        "active_request_id": None,
        "mode": "Explorar",
        "map_center": SANTIAGO_CENTER,
        "map_zoom": 11,
        "fit_all_areas_once": False,
        "page_theme": "Oscuro",
        "active_filter_section": "built",
        "left_panel_open": True,
        "adding_area": False,
        "pending_area_point": None,
        "last_area_click_key": None,
        "selected_detail": None,
        "layer_search": "",
        "selected_built": [],
        "show_metro_current": False,
        "show_metro_future": False,
        "show_road_network": False,
        "show_osm_construction": False,
        "show_seia": False,
        "show_mop": False,
        "selected_territory": [],
        "selected_risks": [],
        "filters": {
            "surface_min": 0,
            "surface_max": 0,
            "price_min": 0,
            "price_max": 0,
            "near_metro": False,
            "near_metro_distance": 1000,
            "near_hospital": False,
            "near_hospital_distance": 1500,
            "near_supermarket": False,
            "near_supermarket_distance": 1000,
            "near_park": False,
            "near_park_distance": 1000,
            "exclude_risk": False,
            "exclude_protected": False,
            "exclude_wetlands": False,
        },
        "last_applied_layers": {
            "built": [],
            "metro_current": False,
            "metro_future": False,
            "road_network": False,
            "osm_construction": False,
            "seia": False,
            "mop": False,
            "territory": [],
            "risks": [],
        },
        "last_apply_message": None,
        "pending_filter_apply": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    for key, value in defaults["filters"].items():
        st.session_state.filters.setdefault(key, value)
    for key, value in defaults["last_applied_layers"].items():
        st.session_state.last_applied_layers.setdefault(key, value)

    for idx, area in enumerate(st.session_state.areas):
        area.setdefault("visible", True)
        area.setdefault("color", AREA_COLORS[idx % len(AREA_COLORS)])
        area.setdefault("geometry_type", "circle")
    if st.session_state.active_filter_section not in {
        "built",
        "transport",
        "future",
        "territory",
        "risks",
    }:
        st.session_state.active_filter_section = "built"


def next_area_id() -> str | None:
    used = {area["id"] for area in st.session_state.areas}
    for letter in "ABCDE":
        if letter not in used:
            return letter
    return None


def get_area(area_id: str | None) -> dict[str, Any] | None:
    if not area_id:
        return None
    return next((area for area in st.session_state.areas if area["id"] == area_id), None)


def active_area() -> dict[str, Any] | None:
    area = get_area(st.session_state.active_area_id)
    if area:
        return area
    if st.session_state.areas:
        st.session_state.active_area_id = st.session_state.areas[0]["id"]
        return st.session_state.areas[0]
    return None


def area_surface_km2(area: dict[str, Any]) -> float:
    return math.pi * (area["radius_m"] / 1000) ** 2


def area_leaflet_bounds(area: dict[str, Any]) -> list[list[float]]:
    lat = float(area["lat"])
    lon = float(area["lon"])
    radius_m = float(area["radius_m"])
    lat_delta = radius_m / 111_320.0
    lon_scale = max(math.cos(math.radians(lat)), 0.15)
    lon_delta = radius_m / (111_320.0 * lon_scale)
    return [[lat - lat_delta, lon - lon_delta], [lat + lat_delta, lon + lon_delta]]


def combined_area_bounds(areas: list[dict[str, Any]]) -> list[list[float]] | None:
    visible = [area for area in areas if area.get("visible", True)]
    if not visible:
        return None
    souths, wests, norths, easts = [], [], [], []
    for area in visible:
        (south, west), (north, east) = area_leaflet_bounds(area)
        souths.append(south)
        wests.append(west)
        norths.append(north)
        easts.append(east)
    return [[min(souths), min(wests)], [max(norths), max(easts)]]


def selected_layer_snapshot() -> dict[str, Any]:
    return {
        "built": list(st.session_state.selected_built),
        "metro_current": bool(st.session_state.show_metro_current),
        "metro_future": bool(st.session_state.show_metro_future),
        "road_network": bool(st.session_state.show_road_network),
        "osm_construction": bool(st.session_state.show_osm_construction),
        "seia": bool(st.session_state.show_seia),
        "mop": bool(st.session_state.show_mop),
        "territory": list(st.session_state.selected_territory),
        "risks": list(st.session_state.selected_risks),
    }


def should_show(label: str, terms: list[str]) -> bool:
    query = normalize_query(st.session_state.layer_search)
    if not query:
        return True
    return query in normalize_query(" ".join([label, *terms]))


def status_text(result: dict[str, Any] | None) -> str:
    if not result:
        return "Sin consultar"
    status = result.get("status")
    count = result.get("count", 0)
    duration = result.get("duration_ms")
    cache = result.get("cache")
    suffix_parts = []
    if isinstance(duration, int) and duration > 0:
        suffix_parts.append(f"{duration} ms")
    if cache in {"HIT", "STALE"}:
        suffix_parts.append("cache" if cache == "HIT" else "cache anterior")
    suffix = f" · {' · '.join(suffix_parts)}" if suffix_parts else ""
    if status in {"OK", "CACHE_HIT"}:
        return f"{count or 0} elementos{suffix}"
    if status == "OK_SIN_COINCIDENCIAS":
        return f"Sin coincidencias en el área{suffix}"
    if status == "VISUAL_ONLY":
        return f"Capa visual disponible{suffix}"
    if status == "STALE_CACHE":
        return f"Fuente pausada; mostrando cache anterior ({count or 0})"
    if status == "SOURCE_ERROR":
        return f"No disponible temporalmente{suffix}"
    return status or "Sin estado"


def bundle_counts(bundle: dict[str, Any]) -> dict[str, Any]:
    current_lines = [
        ref for ref, line in (bundle.get("metro_current") or {}).items()
        if line.get("passes_area") is True
    ]
    future_lines = [
        ref for ref, line in (bundle.get("metro_future") or {}).items()
        if line.get("passes_area") is True
    ]
    stations = sum(
        len(line.get("stations_in_area") or [])
        for line in (bundle.get("metro_current") or {}).values()
    )
    risks = sum(
        int(result.get("count") or 0)
        for result in (bundle.get("risks") or {}).values()
        if result.get("status") == "OK"
    )
    territory = sum(
        int(result.get("count") or 0)
        for result in (bundle.get("technical") or {}).values()
        if result.get("status") == "OK"
    )
    return {
        "assets": len(bundle.get("visual_assets") or []),
        "stations": stations,
        "current_lines": current_lines,
        "future_lines": future_lines,
        "future_records": len(bundle.get("future_records") or []),
        "risks": risks,
        "territory": territory,
    }


def format_distance_m(distance: float | int | None) -> str:
    if distance is None:
        return "N/D"
    if distance >= 1000:
        return f"{distance / 1000:.1f} km"
    return f"{distance:.0f} m"


def format_metro_summary(summary: dict[str, Any] | None) -> str:
    if not summary:
        return "N/D"
    station = summary.get("nearest_station")
    current_nearby = summary.get("current_nearby") or []
    station_text = "sin estación cercana"
    if station:
        station_text = f"{station.get('name')} · {format_distance_m(station.get('distance_m'))}"
    lines = ", ".join(
        f"{item['ref']} · {format_distance_m(item.get('distance_to_area_m'))}"
        for item in current_nearby[:3]
    )
    if not lines:
        lines = "sin líneas cercanas"
    inside = summary.get("stations_inside_count", 0)
    return f"{station_text}; {lines}; {inside} estaciones dentro"


def terrain_filter_count() -> int:
    filters = st.session_state.filters
    active = 0
    for key in ("surface_min", "surface_max", "price_min", "price_max"):
        active += 1 if int(filters.get(key, 0) or 0) > 0 else 0
    for key in (
        "near_metro",
        "near_hospital",
        "near_supermarket",
        "near_park",
        "exclude_risk",
        "exclude_protected",
        "exclude_wetlands",
    ):
        active += 1 if filters.get(key) else 0
    return active


def section_active_count(section: str) -> int:
    if section == "built":
        return len(st.session_state.selected_built)
    if section == "transport":
        return (
            int(st.session_state.show_metro_current)
            + int(st.session_state.show_metro_future)
            + int(st.session_state.show_road_network)
        )
    if section == "future":
        return int(st.session_state.show_osm_construction) + int(st.session_state.show_seia) + int(st.session_state.show_mop)
    if section == "territory":
        return len(st.session_state.selected_territory)
    if section == "risks":
        return len(st.session_state.selected_risks)
    if section == "filters":
        return terrain_filter_count()
    return 0


def render_section_button(section: str, label: str) -> bool:
    count = section_active_count(section)
    suffix = f" [{count}]" if count else ""
    opened = st.session_state.active_filter_section == section
    icon = "v" if opened else ">"
    if st.button(f"{icon} {label}{suffix}", key=f"section_{section}", use_container_width=True):
        st.session_state.active_filter_section = section
        st.rerun()
    return opened


def render_filter_group(title: str) -> None:
    st.markdown(f'<div class="lf-section-title">{title}</div>', unsafe_allow_html=True)


def clear_layers_and_filters() -> None:
    for asset_type in ASSET_TYPES:
        st.session_state[f"built_{asset_type}"] = False
    for source_id in TERRITORY_LAYER_IDS:
        st.session_state[f"territory_{source_id}"] = False
    for source_id in RISK_LAYER_IDS:
        st.session_state[f"risk_{source_id}"] = False
    st.session_state.show_metro_current = False
    st.session_state.show_metro_future = False
    st.session_state.show_road_network = False
    st.session_state.show_osm_construction = False
    st.session_state.show_seia = False
    st.session_state.show_mop = False
    for state_key in (
        "show_metro_current",
        "show_metro_future",
        "show_road_network",
        "show_osm_construction",
        "show_seia",
        "show_mop",
    ):
        st.session_state[f"ui_{state_key}"] = False
    st.session_state.selected_built = []
    st.session_state.selected_territory = []
    st.session_state.selected_risks = []
    st.session_state.filters.update(
        {
            "surface_min": 0,
            "surface_max": 0,
            "price_min": 0,
            "price_max": 0,
            "near_metro": False,
            "near_metro_distance": 1000,
            "near_hospital": False,
            "near_hospital_distance": 1500,
            "near_supermarket": False,
            "near_supermarket_distance": 1000,
            "near_park": False,
            "near_park_distance": 1000,
            "exclude_risk": False,
            "exclude_protected": False,
            "exclude_wetlands": False,
        }
    )


def runtime_now() -> float:
    return time.time()


def cache_key_for(area: dict[str, Any], source_id: str, params: Any) -> str:
    payload = {
        "area": {
            "lat": round(float(area["lat"]), 6),
            "lon": round(float(area["lon"]), 6),
            "radius_m": int(area["radius_m"]),
        },
        "source": source_id,
        "params": params,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def source_label_for_runtime(source_id: str) -> str:
    return LAYER_DISPLAY_NAMES.get(source_id, source_label(source_id) if source_id in SOURCE_BY_ID else source_id)


def set_source_status(source_id: str, status: str, duration_ms: int, feature_count: int | None, cache: str, error: str | None = None) -> None:
    st.session_state.source_status[source_id] = {
        "status": status,
        "duration_ms": duration_ms,
        "feature_count": feature_count,
        "cache": cache,
        "error": error,
        "lastUpdated": datetime.now().isoformat(timespec="seconds"),
    }
    print(
        f"[Landfinder][source] {source_id} status={status} duration={duration_ms}ms "
        f"cache={cache} features={feature_count} error={clean_source_error(error) if error else ''}"
    )


def circuit_allows(source_id: str, cfg: dict[str, Any]) -> bool:
    circuit = st.session_state.source_circuits.get(source_id, {})
    if circuit.get("state") != "OPEN":
        return True
    opened_at = float(circuit.get("opened_at", 0))
    if runtime_now() - opened_at >= cfg.get("circuit_cooldown_seconds", 180):
        circuit["state"] = "HALF_OPEN"
        st.session_state.source_circuits[source_id] = circuit
        return True
    return False


def record_circuit_success(source_id: str) -> None:
    st.session_state.source_circuits[source_id] = {"state": "CLOSED", "failures": 0, "opened_at": None}


def record_circuit_failure(source_id: str, cfg: dict[str, Any]) -> None:
    circuit = st.session_state.source_circuits.get(source_id, {"state": "CLOSED", "failures": 0})
    failures = int(circuit.get("failures", 0)) + 1
    state = "OPEN" if failures >= int(cfg.get("circuit_failures", 3)) else "CLOSED"
    st.session_state.source_circuits[source_id] = {
        "state": state,
        "failures": failures,
        "opened_at": runtime_now() if state == "OPEN" else circuit.get("opened_at"),
    }


def run_source(
    source_id: str,
    params: Any,
    area: dict[str, Any],
    producer,
    cfg: dict[str, Any] | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    cfg = cfg or source_config(SOURCE_BY_ID.get(source_id, source_id))
    key = cache_key_for(area, source_id, params)
    cached = st.session_state.source_cache.get(key)
    ttl = int(cfg.get("cache_ttl_seconds", 0) or 0)
    now = runtime_now()
    if cached and ttl and now - float(cached.get("stored_at", 0)) <= ttl:
        result = cached["value"]
        count = cached.get("count")
        set_source_status(source_id, "cache_hit", 0, count, "HIT")
        state = {"status": "CACHE_HIT", "count": count, "error": None, "duration_ms": 0, "cache": "HIT"}
        return result, state
    if cached:
        set_source_status(source_id, "refreshing", 0, cached.get("count"), "STALE")

    if not circuit_allows(source_id, cfg):
        count = cached.get("count") if cached else None
        if cached:
            set_source_status(source_id, "circuit_open_cache", 0, count, "STALE")
            state = {"status": "STALE_CACHE", "count": count, "error": None, "duration_ms": 0, "cache": "STALE"}
            return cached["value"], state
        error = "Fuente pausada temporalmente por fallos repetidos. Reintenta más tarde."
        set_source_status(source_id, "circuit_open", 0, None, "MISS", error)
        return None, {"status": "SOURCE_ERROR", "count": None, "error": error, "duration_ms": 0, "cache": "MISS"}

    start = time.perf_counter()
    try:
        result = producer()
        duration_ms = int((time.perf_counter() - start) * 1000)
        count = source_result_count(result)
        st.session_state.source_cache[key] = {
            "value": result,
            "stored_at": now,
            "count": count,
            "lastUpdated": datetime.now().isoformat(timespec="seconds"),
        }
        record_circuit_success(source_id)
        set_source_status(source_id, "success", duration_ms, count, "MISS")
        state = {
            "status": "OK" if count else "OK_SIN_COINCIDENCIAS",
            "count": count,
            "error": None,
            "duration_ms": duration_ms,
            "cache": "MISS",
        }
        return result, state
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        error = str(exc)
        record_circuit_failure(source_id, cfg)
        if cached:
            count = cached.get("count")
            set_source_status(source_id, "stale_cache", duration_ms, count, "STALE", error)
            return cached["value"], {
                "status": "STALE_CACHE",
                "count": count,
                "error": error,
                "duration_ms": duration_ms,
                "cache": "STALE",
            }
        set_source_status(source_id, "timeout" if "timeout" in error.lower() else "error", duration_ms, None, "MISS", error)
        return None, {"status": "SOURCE_ERROR", "count": None, "error": error, "duration_ms": duration_ms, "cache": "MISS"}


def source_result_count(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        if "count" in result and isinstance(result.get("count"), int):
            return int(result["count"])
        if "features" in result and isinstance(result.get("features"), list):
            return len(result["features"])
        if all(isinstance(value, dict) for value in result.values()):
            total = 0
            for value in result.values():
                if "segments" in value:
                    total += len(value.get("segments") or [])
                elif "stations_in_area" in value:
                    total += len(value.get("stations_in_area") or [])
            return total
    return 0


def add_area_circle(map_obj: folium.Map, area: dict[str, Any], active: bool = False) -> None:
    if not area.get("visible", True):
        return
    color = area["color"]
    folium.Circle(
        [area["lat"], area["lon"]],
        radius=area["radius_m"],
        color=color,
        weight=5 if active else 3,
        fill=True,
        fill_color=color,
        fill_opacity=0.16 if active else 0.09,
        tooltip=f"{area['name']} · {area['sector']}",
    ).add_to(map_obj)
    folium.CircleMarker(
        [area["lat"], area["lon"]],
        radius=8,
        color="#FFFFFF",
        weight=3,
        fill=True,
        fill_color=color,
        fill_opacity=1,
        tooltip=f"{area['name']} · {area['sector']}",
    ).add_to(map_obj)
    folium.Marker(
        [area["lat"], area["lon"]],
        icon=folium.DivIcon(
            html=f"""
            <div style="background:{color};color:white;border:2px solid white;
                        box-shadow:0 4px 12px rgba(0,0,0,.25);border-radius:8px;
                        padding:5px 9px;font-weight:800;white-space:nowrap;font-size:12px;">
              {area['name']}
            </div>
            """
        ),
    ).add_to(map_obj)


def add_metro_line(map_obj: folium.Map, line: dict[str, Any], future: bool = False) -> None:
    color = line.get("color") or METRO_COLORS.get(line.get("ref"), "#555555")
    ref = line.get("ref") or "Metro"
    label = f"{'Metro futuro' if future else 'Metro actual'} · {ref}"
    group = folium.FeatureGroup(name=label, show=True)
    for segment in line.get("segments") or []:
        folium.PolyLine(
            segment,
            color=color,
            weight=6 if not future else 5,
            opacity=0.95,
            dash_array="9 7" if future else None,
            tooltip=label,
        ).add_to(group)
    if not future:
        for station in line.get("stations_in_area") or []:
            folium.CircleMarker(
                [station["lat"], station["lon"]],
                radius=4,
                color=color,
                weight=2,
                fill=True,
                fill_color="#FFFFFF",
                fill_opacity=1,
                tooltip=f"{station.get('name')} · {ref}",
            ).add_to(group)
    group.add_to(map_obj)


def add_geojson_result(map_obj: folium.Map, label: str, result: dict[str, Any], color: str) -> None:
    rendered = 0
    if result.get("type") == "geojson_layers":
        group = folium.FeatureGroup(name=label, show=True)
        for layer in result.get("layers") or []:
            geojson = layer.get("geojson")
            if not geojson or not geojson.get("features"):
                continue
            rendered += len(geojson.get("features") or [])
            folium.GeoJson(
                geojson,
                name=label,
                style_function=lambda _feature, c=color: {
                    "color": c,
                    "weight": 2,
                    "fillColor": c,
                    "fillOpacity": 0.12,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["__label", "__distance_m"],
                    aliases=["Elemento", "Distancia m"],
                    sticky=False,
                ),
            ).add_to(group)
        group.add_to(map_obj)
    elif result.get("type") == "wms":
        source = next((src for src in SOURCES if src.get("map_label") == label), None)
        if source:
            for layer_name in result.get("layers") or []:
                folium.raster_layers.WmsTileLayer(
                    url=source["url"],
                    layers=layer_name,
                    name=label,
                    fmt="image/png",
                    transparent=True,
                    overlay=True,
                ).add_to(map_obj)
                rendered += 1
    print(
        f"[RENDER: {label}] status={result.get('status')} stored={len(result.get('records') or [])} rendered={rendered}"
    )


def legend_html(snapshot: dict[str, Any]) -> str:
    items = []
    for asset_type in snapshot.get("built") or []:
        cfg = ASSET_TYPES.get(asset_type)
        if cfg:
            items.append((cfg["color"], cfg["label"], "dot"))
    if snapshot.get("metro_current"):
        items.append(("#E31B23", "Metro actual", "line"))
    if snapshot.get("metro_future"):
        items.append(("#777777", "Metro futuro", "dash"))
    if snapshot.get("road_network"):
        items.append(("#1677B8", "Red vial", "line"))
    if snapshot.get("osm_construction"):
        items.append(("#FF8A32", "Construcciones OSM", "dot"))
    if snapshot.get("seia"):
        items.append(("#F5A400", "SEIA", "poly"))
    if snapshot.get("mop"):
        items.append(("#F5A400", "MOP", "poly"))
    for source_id in snapshot.get("territory") or []:
        items.append(("#1677B8", source_label(source_id), "poly"))
    for source_id in snapshot.get("risks") or []:
        items.append(("#E74C5B", source_label(source_id), "poly"))

    if not items:
        return ""

    rows = []
    for color, label, kind in items[:14]:
        if kind == "line":
            symbol = f"<span style='display:inline-block;width:22px;border-top:4px solid {color};'></span>"
        elif kind == "dash":
            symbol = f"<span style='display:inline-block;width:22px;border-top:4px dashed {color};'></span>"
        elif kind == "poly":
            symbol = f"<span style='display:inline-block;width:14px;height:10px;background:{color}33;border:2px solid {color};'></span>"
        else:
            symbol = f"<span style='display:inline-block;width:10px;height:10px;background:{color};border-radius:50%;'></span>"
        rows.append(f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:12px;'>{symbol}{label}</span>")

    return f"""
    <div style="position:absolute;left:22px;bottom:18px;z-index:9999;background:white;
                border:1px solid #D9E5F2;border-radius:8px;padding:9px 12px;
                box-shadow:0 8px 24px rgba(9,33,59,.16);font-size:12px;color:#123A5F;">
      {''.join(rows)}
    </div>
    """


def nearest_detail(lat: float, lon: float, max_distance_m: float = 80) -> dict[str, Any] | None:
    candidates = []
    for area in st.session_state.areas:
        bundle = st.session_state.map_bundle.get(area["id"], {})
        for item in bundle.get("visual_assets") or []:
            distance = haversine_m(lat, lon, item["lat"], item["lon"])
            source_url = None
            if item.get("osm_type") and item.get("osm_id"):
                source_url = f"https://www.openstreetmap.org/{item.get('osm_type')}/{item.get('osm_id')}"
            candidates.append(
                {
                    "distance": distance,
                    "title": item.get("name") or item.get("category"),
                    "category": item.get("category"),
                    "source": "OpenStreetMap",
                    "area": area["name"],
                    "source_url": source_url,
                    "metadata": item.get("tags") or {},
                }
            )
        for item in bundle.get("construction") or []:
            distance = haversine_m(lat, lon, item["lat"], item["lon"])
            source_url = None
            if item.get("osm_type") and item.get("osm_id"):
                source_url = f"https://www.openstreetmap.org/{item.get('osm_type')}/{item.get('osm_id')}"
            candidates.append(
                {
                    "distance": distance,
                    "title": item.get("name") or "Construcción mapeada",
                    "category": item.get("category"),
                    "source": "OpenStreetMap",
                    "area": area["name"],
                    "source_url": source_url,
                    "metadata": item.get("tags") or {},
                }
            )
        for ref, line in (bundle.get("metro_current") or {}).items():
            for station in line.get("stations_in_area") or []:
                distance = haversine_m(lat, lon, station["lat"], station["lon"])
                candidates.append(
                    {
                        "distance": distance,
                        "title": station.get("name"),
                        "category": f"Estación Metro {ref}",
                        "source": "OpenStreetMap",
                        "area": area["name"],
                        "source_url": None,
                        "metadata": station.get("tags") or {},
                    }
                )
    if not candidates:
        return None
    chosen = min(candidates, key=lambda item: item["distance"])
    return chosen if chosen["distance"] <= max_distance_m else None


def state_from_map_result(result: dict[str, Any], runtime_state: dict[str, Any]) -> dict[str, Any]:
    state = dict(runtime_state)
    state["status"] = result.get("status", state.get("status"))
    state["count"] = result.get("count", state.get("count"))
    state["error"] = result.get("error", state.get("error"))
    return state


def query_area(area: dict[str, Any], snapshot: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
    terrain_filters = dict(st.session_state.filters)
    source_plan = build_source_plan(snapshot, terrain_filters)
    bundle = {
        "assets": [],
        "visual_assets": [],
        "metro_current": {},
        "metro_future": {},
        "construction": [],
        "future_records": [],
        "future_gis": {},
        "technical": {},
        "risks": {},
        "restriction_data": {},
        "layer_states": {},
        "filters": terrain_filters,
        "source_plan": source_plan,
        "map_layers": snapshot,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    overpass_cfg = source_config("osm_overpass")
    overpass_timeout = int(overpass_cfg["timeout"])
    metro_cfg = source_config("metro_static")

    def request_is_current() -> bool:
        return request_id is None or st.session_state.get("active_request_id") == request_id

    if source_plan["built_query_types"]:
        result, state = run_source(
            "built",
            {"types": source_plan["built_query_types"]},
            area,
            lambda: query_built_assets(
                area["lat"],
                area["lon"],
                area["radius_m"],
                source_plan["built_query_types"],
                timeout=overpass_timeout,
            ),
            overpass_cfg,
        )
        if not request_is_current():
            return bundle
        bundle["assets"] = result or []
        visual_types = set(source_plan["built_visual_types"])
        bundle["visual_assets"] = [item for item in bundle["assets"] if item.get("type") in visual_types]
        print(
            f"[SOURCE: OSM_POI] stored={len(bundle['assets'])} "
            f"rendered={len(bundle['visual_assets'])} visual_types={','.join(sorted(visual_types)) or 'none'}"
        )
        bundle["layer_states"]["built"] = state

    if source_plan["metro_current"]:
        result, state = run_source(
            "metro_current",
            {"dataset": "local_geojson"},
            area,
            lambda: metro_current_for_area(area["lat"], area["lon"], area["radius_m"], timeout=int(metro_cfg["timeout"])),
            metro_cfg,
        )
        if not request_is_current():
            return bundle
        bundle["metro_current"] = result or {}
        bundle["layer_states"]["metro_current"] = state

    if source_plan["metro_future"]:
        result, state = run_source(
            "metro_future",
            {"dataset": "local_geojson"},
            area,
            lambda: metro_future_for_area(area["lat"], area["lon"], area["radius_m"], timeout=int(metro_cfg["timeout"])),
            metro_cfg,
        )
        if not request_is_current():
            return bundle
        bundle["metro_future"] = result or {}
        available = sum(1 for line in bundle["metro_future"].values() if line.get("geometry_available"))
        bundle["layer_states"]["metro_future"] = {
            **state,
            "status": "OK" if available else "OK_SIN_COINCIDENCIAS",
            "count": available,
        }

    if source_plan["osm_construction"]:
        result, state = run_source(
            "osm_construction",
            {"enabled": True},
            area,
            lambda: query_osm_construction(area["lat"], area["lon"], area["radius_m"], timeout=overpass_timeout),
            overpass_cfg,
        )
        if not request_is_current():
            return bundle
        bundle["construction"] = result or []
        for item in bundle["construction"]:
            bundle["future_records"].append(
                {
                    "Fuente": "OpenStreetMap",
                    "Elemento": item.get("name"),
                    "Estado": "Construcción mapeada",
                    "Distancia_m": round(haversine_m(area["lat"], area["lon"], item["lat"], item["lon"]), 1),
                }
        )
        bundle["layer_states"]["osm_construction"] = state

    for source_id in source_plan["future_gis"]:
        source = SOURCE_BY_ID.get(source_id)
        if not source:
            continue
        cfg = source_config(source)
        result, state = run_source(
            source_id,
            {"kind": "future_gis"},
            area,
            lambda source=source, cfg=cfg: load_map_source(
                source, area["lat"], area["lon"], area["radius_m"], cfg["timeout"], 500
            ),
            cfg,
        )
        if not request_is_current():
            return bundle
        result = result or {"status": "SOURCE_ERROR", "type": None, "layers": [], "records": [], "count": None, "error": state.get("error")}
        bundle["future_gis"][source_id] = result
        bundle["layer_states"][source_id] = state_from_map_result(result, state)
        for record in result.get("records") or []:
            bundle["future_records"].append(
                {
                    "Fuente": record.get("Fuente") or source_label(source_id),
                    "Elemento": record.get("Elemento"),
                    "Estado": "Registro de fuente",
                    "Distancia_m": record.get("Distancia_m"),
                }
            )

    for source_id in source_plan["territory_sources"]:
        source = SOURCE_BY_ID.get(source_id)
        if not source:
            continue
        cfg = source_config(source)
        result, state = run_source(
            source_id,
            {"kind": "territory"},
            area,
            lambda source=source, cfg=cfg: load_map_source(
                source, area["lat"], area["lon"], area["radius_m"], cfg["timeout"], 500
            ),
            cfg,
        )
        if not request_is_current():
            return bundle
        result = result or {"status": "SOURCE_ERROR", "type": None, "layers": [], "records": [], "count": None, "error": state.get("error")}
        bundle["technical"][source_id] = result
        bundle["layer_states"][source_id] = state_from_map_result(result, state)

    for source_id in source_plan["risk_sources"]:
        source = SOURCE_BY_ID.get(source_id)
        if not source:
            continue
        cfg = source_config(source)
        result, state = run_source(
            source_id,
            {"kind": "risks"},
            area,
            lambda source=source, cfg=cfg: load_map_source(
                source, area["lat"], area["lon"], area["radius_m"], cfg["timeout"], 500
            ),
            cfg,
        )
        if not request_is_current():
            return bundle
        result = result or {"status": "SOURCE_ERROR", "type": None, "layers": [], "records": [], "count": None, "error": state.get("error")}
        bundle["restriction_data"][source_id] = result
        if source_id in source_plan["risk_visual_sources"]:
            bundle["risks"][source_id] = result
        bundle["layer_states"][source_id] = state_from_map_result(result, state)

    if bundle["metro_current"] or bundle["metro_future"]:
        bundle["metro_summary"] = metro_area_summary(
            bundle.get("metro_current") or {},
            bundle.get("metro_future") or {},
            area["lat"],
            area["lon"],
            area["radius_m"],
            nearby_threshold_m=float(terrain_filters.get("near_metro_distance", 1000) or 1000),
        )

    return bundle


def apply_filters_to_targets(target_areas: list[dict[str, Any]], progress_slot=None) -> None:
    snapshot = selected_layer_snapshot()
    st.session_state.last_applied_layers = snapshot
    request_id = f"{runtime_now():.6f}"
    st.session_state.active_request_id = request_id
    progress = progress_slot.progress(0, text="Preparando consultas territoriales...") if progress_slot else None
    status = progress_slot.empty() if progress_slot else None
    for index, area in enumerate(target_areas, 1):
        if st.session_state.get("active_request_id") != request_id:
            break
        if status:
            status.write(f"Consultando fuentes para **{area['name']}**...")
        if progress:
            progress.progress((index - 1) / len(target_areas), text=f"Consultando {area['name']}...")
        st.session_state.map_bundle[area["id"]] = query_area(area, snapshot, request_id)
        if progress:
            progress.progress(index / len(target_areas), text=f"{area['name']} listo")
    if status:
        status.success("Filtros aplicados. Las fuentes con error quedaron aisladas del resto.")
    st.session_state.last_apply_message = datetime.now().isoformat(timespec="seconds")
    st.session_state.pending_filter_apply = False


def render_header(profile: dict[str, Any]) -> None:
    st.markdown(
        f"""
        <div class="lf-shell">
          <div class="lf-brand">
            <div class="lf-logo"></div>
            <div>
              <div class="lf-brand-title">Landfinder Chile</div>
              <div class="lf-brand-sub">Territorio para mejores decisiones</div>
            </div>
          </div>
          <div></div>
          <div class="lf-nav">
            <span class="lf-avatar">SA</span>
            <span>{profile['name']}<br><span style="color:#BFE7F1;">{profile['role']}</span></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_layer_checkbox(label: str, state_key: str, terms: list[str]) -> None:
    if should_show(label, terms):
        widget_key = f"ui_{state_key}"
        if widget_key not in st.session_state:
            st.session_state[widget_key] = bool(st.session_state.get(state_key, False))
        st.checkbox(label, key=widget_key)
        st.session_state[state_key] = bool(st.session_state.get(widget_key, False))


def render_asset_checkbox(asset_type: str, selected: list[str]) -> list[str]:
    cfg = ASSET_TYPES[asset_type]
    state_key = f"built_{asset_type}"
    if state_key not in st.session_state:
        st.session_state[state_key] = asset_type in st.session_state.selected_built
    if should_show(cfg["label"], [asset_type, "equipamiento", "osm", "servicios"]):
        st.checkbox(cfg["label"], key=state_key)
    if st.session_state.get(state_key):
        selected.append(asset_type)
    return selected


def render_distance_filter(label: str, enabled_key: str, distance_key: str, default_m: int) -> None:
    filters = st.session_state.filters
    cols = st.columns([0.58, 0.42], gap="small")
    filters[enabled_key] = cols[0].checkbox(
        label,
        value=bool(filters.get(enabled_key, False)),
        key=f"ui_filter_{enabled_key}",
    )
    filters[distance_key] = cols[1].number_input(
        f"Distancia {label}",
        min_value=100,
        max_value=10000,
        value=int(filters.get(distance_key, default_m) or default_m),
        step=100,
        format="%d",
        label_visibility="collapsed",
        key=f"ui_filter_{distance_key}",
    )


def render_terrain_search_panel(area: dict[str, Any] | None) -> bool:
    with st.container(border=True):
        st.markdown('<div class="lf-panel-title">Buscar terrenos</div>', unsafe_allow_html=True)
        if area:
            st.caption(f"Restricción espacial: {area['name']}.")
        else:
            st.caption("Crea o selecciona un área para delimitar la búsqueda.")

        filters = st.session_state.filters
        render_filter_group("Características")
        c1, c2 = st.columns(2)
        filters["surface_min"] = c1.number_input("Sup. mínima m2", min_value=0, value=int(filters.get("surface_min", 0)), step=100)
        filters["surface_max"] = c2.number_input("Sup. máxima m2", min_value=0, value=int(filters.get("surface_max", 0)), step=100)
        filters["price_min"] = c1.number_input("Precio mínimo", min_value=0, value=int(filters.get("price_min", 0)), step=1000)
        filters["price_max"] = c2.number_input("Precio máximo", min_value=0, value=int(filters.get("price_max", 0)), step=1000)

        render_filter_group("Cercanía")
        render_distance_filter("Metro actual", "near_metro", "near_metro_distance", 1000)
        render_distance_filter("Hospital", "near_hospital", "near_hospital_distance", 1500)
        render_distance_filter("Supermercado", "near_supermarket", "near_supermarket_distance", 1000)
        render_distance_filter("Parque", "near_park", "near_park_distance", 1000)

        render_filter_group("Exclusiones")
        filters["exclude_risk"] = st.checkbox(
            "Áreas de riesgo",
            value=bool(filters.get("exclude_risk", False)),
            key="ui_filter_exclude_risk",
        )
        filters["exclude_wetlands"] = st.checkbox(
            "Humedales",
            value=bool(filters.get("exclude_wetlands", False)),
            key="ui_filter_exclude_wetlands",
        )
        filters["exclude_protected"] = st.checkbox(
            "Áreas protegidas",
            value=bool(filters.get("exclude_protected", False)),
            key="ui_filter_exclude_protected",
        )

        c1, c2 = st.columns(2)
        if c1.button("Limpiar", use_container_width=True):
            clear_layers_and_filters()
            st.rerun()
        return c2.button("Buscar terrenos", type="primary", use_container_width=True)


def render_left_panel(area: dict[str, Any] | None) -> None:
    apply_clicked = False

    with st.container(border=True):
        area_title, area_action = st.columns([0.48, 0.52])
        area_title.markdown('<div class="lf-panel-title">Área de trabajo</div>', unsafe_allow_html=True)
        if area_action.button("+ Nueva área", type="primary", use_container_width=True):
            st.session_state.adding_area = True
            st.session_state.pending_area_point = None
            st.session_state.selected_detail = None
            st.rerun()

        if st.session_state.areas:
            area_options = [item["id"] for item in st.session_state.areas]
            active_id = st.session_state.active_area_id if st.session_state.active_area_id in area_options else area_options[0]
            selected_id = st.selectbox(
                "Área activa",
                area_options,
                index=area_options.index(active_id),
                format_func=lambda item_id: f"Área {item_id} · {compact_place_label(get_area(item_id)['sector'], 32)}",
            )
            if selected_id != st.session_state.active_area_id:
                selected_area = get_area(selected_id)
                if selected_area:
                    st.session_state.active_area_id = selected_id
                    st.session_state.map_center = (selected_area["lat"], selected_area["lon"])
                    st.session_state.map_zoom = 14
                    st.session_state.selected_detail = None
                    st.rerun()

        if st.session_state.adding_area:
            st.info("Haz clic en el mapa o escribe una dirección para fijar el centro.")
            point = st.session_state.pending_area_point
            with st.form("create_area_form"):
                new_id = next_area_id()
                if not new_id:
                    st.warning("El MVP admite hasta 5 áreas simultáneas.")
                    submitted = False
                else:
                    default_lat = point["lat"] if point else (area["lat"] if area else st.session_state.map_center[0])
                    default_lon = point["lng"] if point else (area["lon"] if area else st.session_state.map_center[1])
                    address = st.text_input(
                        "Dirección o referencia",
                        "",
                        placeholder="Ej: Av. Irarrázaval 2401, Ñuñoa",
                        help="Si escribes una dirección, Landfinder la usará como centro del área.",
                    )
                    name = st.text_input("Nombre", f"Área {new_id}")
                    sector = st.text_input("Sector / comuna", "Punto seleccionado" if point else "Santiago")
                    lat = st.number_input("Latitud", value=float(default_lat), format="%.6f")
                    lon = st.number_input("Longitud", value=float(default_lon), format="%.6f")
                    radius = st.selectbox("Radio", [500, 1000, 2000, 3000, 5000], index=2)
                    submitted = st.form_submit_button("Confirmar área")
                if submitted and new_id:
                    resolved_area = resolve_search(address) if address.strip() else None
                    if address.strip() and not resolved_area:
                        st.warning("No pude resolver esa dirección. Agrega comuna/ciudad, por ejemplo `Santa Raquel 8204, La Florida, Santiago`, o usa lat,lng.")
                        return
                    if resolved_area:
                        lat = resolved_area[0]
                        lon = resolved_area[1]
                        sector = compact_place_label(resolved_area[3], 72)
                    st.session_state.areas.append(
                        {
                            "id": new_id,
                            "name": name,
                            "sector": sector,
                            "lat": float(lat),
                            "lon": float(lon),
                            "radius_m": int(radius),
                            "color": AREA_COLORS[len(st.session_state.areas) % len(AREA_COLORS)],
                            "visible": True,
                            "geometry_type": "circle",
                        }
                    )
                    st.session_state.active_area_id = new_id
                    st.session_state.map_center = (float(lat), float(lon))
                    st.session_state.map_zoom = 13
                    st.session_state.fit_all_areas_once = len(st.session_state.areas) > 1
                    st.session_state.adding_area = False
                    st.session_state.pending_area_point = None
                    st.rerun()

        if st.session_state.areas:
            if len(st.session_state.areas) > 1 and st.button("Ver todas las áreas", use_container_width=True):
                st.session_state.fit_all_areas_once = True
                st.rerun()
            for area_item in list(st.session_state.areas):
                active = area_item["id"] == st.session_state.active_area_id
                st.markdown(
                    f"<div class='lf-area-row {'is-active' if active else ''}' style='--area-color:{area_item['color']};'>"
                    f"<b>{area_item['name']}</b><br>"
                    f"<span class='lf-area-meta'>{compact_place_label(area_item['sector'], 34)} · {area_surface_km2(area_item):.1f} km2</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                cols = st.columns([0.16, 0.42, 0.20, 0.22])
                cols[0].markdown(
                    f"<span class='lf-pill' style='background:{area_item['color']}22;color:{area_item['color']};'>{area_item['id']}</span>",
                    unsafe_allow_html=True,
                )
                if cols[1].button("Centrar", key=f"active_{area_item['id']}", use_container_width=True):
                    st.session_state.active_area_id = area_item["id"]
                    st.session_state.map_center = (area_item["lat"], area_item["lon"])
                    st.session_state.map_zoom = 14
                    st.session_state.selected_detail = None
                    st.rerun()
                area_item["visible"] = cols[2].checkbox(
                    "Ver",
                    value=area_item.get("visible", True),
                    key=f"visible_{area_item['id']}",
                    label_visibility="collapsed",
                )
                if cols[3].button("X", key=f"remove_{area_item['id']}"):
                    st.session_state.areas = [a for a in st.session_state.areas if a["id"] != area_item["id"]]
                    st.session_state.map_bundle.pop(area_item["id"], None)
                    if st.session_state.active_area_id == area_item["id"]:
                        st.session_state.active_area_id = st.session_state.areas[0]["id"] if st.session_state.areas else None
                    st.rerun()
        else:
            if st.button("+ Crear primera área", use_container_width=True):
                st.session_state.adding_area = True
                st.rerun()

    with st.container(border=True):
        title_col, clear_col = st.columns([0.62, 0.38])
        title_col.markdown('<div class="lf-panel-title">Capas del mapa</div>', unsafe_allow_html=True)
        if clear_col.button("Limpiar todo", use_container_width=True):
            clear_layers_and_filters()
            st.rerun()
        st.text_input("Filtrar capas", placeholder="Filtrar capas...", key="layer_search", label_visibility="collapsed")

        if render_section_button("built", "Equipamiento actual"):
            selected = []
            render_filter_group("Comercio")
            for asset_type in ("supermarket", "mall"):
                selected = render_asset_checkbox(asset_type, selected)
            render_filter_group("Salud")
            for asset_type in ("hospital", "pharmacy"):
                selected = render_asset_checkbox(asset_type, selected)
            render_filter_group("Educación")
            selected = render_asset_checkbox("education", selected)
            render_filter_group("Parques / áreas verdes")
            selected = render_asset_checkbox("park", selected)
            st.session_state.selected_built = selected

        if render_section_button("transport", "Transporte"):
            render_layer_checkbox("Metro actual", "show_metro_current", ["metro", "linea", "estaciones"])
            render_layer_checkbox("Metro futuro", "show_metro_future", ["metro", "futuro", "linea 7", "linea 8", "linea 9"])
            render_layer_checkbox("Red vial", "show_road_network", ["mop", "red", "vial", "calles"])

        if render_section_button("future", "Desarrollo futuro"):
            render_layer_checkbox("Construcciones detectadas OSM", "show_osm_construction", ["obra", "construccion"])
            render_layer_checkbox("Proyectos SEIA", "show_seia", ["sea", "ambiental", "proyecto"])
            render_layer_checkbox("Obras / contratos MOP", "show_mop", ["mop", "obra", "contrato"])

        if render_section_button("territory", "Territorio y normativa"):
            selected = []
            for source_id in TERRITORY_LAYER_IDS:
                if source_id not in SOURCE_BY_ID:
                    continue
                label = source_label(source_id)
                state_key = f"territory_{source_id}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = source_id in st.session_state.selected_territory
                if should_show(label, [SOURCE_BY_ID[source_id].get("category", ""), SOURCE_BY_ID[source_id].get("provider", "")]):
                    st.checkbox(label, key=state_key)
                if st.session_state.get(state_key):
                    selected.append(source_id)
            st.session_state.selected_territory = selected

        if render_section_button("risks", "Riesgos y restricciones"):
            selected = []
            for source_id in RISK_LAYER_IDS:
                if source_id not in SOURCE_BY_ID:
                    continue
                label = source_label(source_id)
                state_key = f"risk_{source_id}"
                if state_key not in st.session_state:
                    st.session_state[state_key] = source_id in st.session_state.selected_risks
                if should_show(label, [SOURCE_BY_ID[source_id].get("category", ""), SOURCE_BY_ID[source_id].get("provider", "")]):
                    st.checkbox(label, key=state_key)
                if st.session_state.get(state_key):
                    selected.append(source_id)
            st.session_state.selected_risks = selected

        apply_clicked = st.button("Actualizar mapa", type="primary", use_container_width=True)

    terrain_search_clicked = render_terrain_search_panel(area)
    apply_clicked = apply_clicked or terrain_search_clicked

    if apply_clicked:
        target_areas = [area] if area else []
        if not target_areas:
            st.warning("Crea o muestra al menos un área antes de aplicar filtros.")
        else:
            st.session_state.pending_filter_apply = True


def render_map() -> None:
    theme = st.session_state.get("page_theme", "Oscuro")
    basemap = basemap_for_theme(theme)
    map_obj = folium.Map(
        location=list(st.session_state.map_center),
        zoom_start=int(st.session_state.map_zoom),
        tiles=None,
        max_zoom=basemap.max_zoom,
        control_scale=True,
    )
    primary_layer = folium.TileLayer(
        tiles=basemap.tiles,
        attr=basemap.attribution,
        name=basemap.label,
        max_zoom=basemap.max_zoom,
        max_native_zoom=basemap.max_native_zoom,
        overlay=False,
        control=False,
    )
    primary_layer.add_to(map_obj)
    BasemapFallbackControl(
        primary_layer.get_name(),
        basemap.provider,
        basemap.fallback_tiles,
        basemap.fallback_attribution,
        basemap.max_zoom,
        basemap.fallback_max_native_zoom,
    ).add_to(map_obj)
    Fullscreen(position="topright").add_to(map_obj)
    dark_controls = theme == "Oscuro"
    map_obj.get_root().html.add_child(
        folium.Element(
            f"""
            <style>
            .leaflet-container {{
              background: {'#08111F' if dark_controls else '#F4F8FC'};
              font-family: Inter, Segoe UI, Arial, sans-serif;
            }}
            .leaflet-control-layers,
            .leaflet-bar a,
            .leaflet-popup-content-wrapper,
            .leaflet-popup-tip {{
              background: {'#0D1726' if dark_controls else '#FFFFFF'} !important;
              color: {'#EAF2FF' if dark_controls else '#071426'} !important;
              border-color: {'#24364D' if dark_controls else '#CBD8E6'} !important;
            }}
            .leaflet-bar a {{
              border-bottom-color: {'#24364D' if dark_controls else '#CBD8E6'} !important;
            }}
            .lf-center-control button {{
              min-height: 38px;
              padding: 0 13px;
              border-radius: 8px;
              border: 1px solid {'#2B4059' if dark_controls else '#CBD8E6'};
              background: {'#0D1726' if dark_controls else '#FFFFFF'};
              color: {'#EAF2FF' if dark_controls else '#071426'};
              font-weight: 800;
              box-shadow: 0 10px 24px rgba(0,0,0,.20);
              cursor: pointer;
            }}
            .lf-basemap-fallback {{
              padding: 8px 10px;
              border-radius: 8px;
              border: 1px solid {'#2B4059' if dark_controls else '#CBD8E6'};
              background: {'#0D1726' if dark_controls else '#FFFFFF'};
              color: {'#EAF2FF' if dark_controls else '#071426'};
              font-size: 12px;
              font-weight: 750;
              box-shadow: 0 10px 24px rgba(0,0,0,.18);
            }}
            </style>
            """
        )
    )
    CenterSantiagoControl(SANTIAGO_CENTER[0], SANTIAGO_CENTER[1], 11).add_to(map_obj)

    for area_item in st.session_state.areas:
        add_area_circle(map_obj, area_item, active=area_item["id"] == st.session_state.active_area_id)

    if st.session_state.get("fit_all_areas_once"):
        bounds = combined_area_bounds(st.session_state.areas)
        if bounds:
            map_obj.fit_bounds(bounds, padding=(32, 32))
        st.session_state.fit_all_areas_once = False

    for area_item in st.session_state.areas:
        if not area_item.get("visible", True):
            continue
        bundle = st.session_state.map_bundle.get(area_item["id"], {})
        map_layers = bundle.get("map_layers") or st.session_state.last_applied_layers

        if bundle.get("visual_assets"):
            cluster = MarkerCluster(name=f"Equipamientos · {area_item['name']}")
            for item in bundle.get("visual_assets") or []:
                distance = haversine_m(area_item["lat"], area_item["lon"], item["lat"], item["lon"])
                folium.CircleMarker(
                    [item["lat"], item["lon"]],
                    radius=6,
                    color=item.get("color", "#1473E6"),
                    weight=2,
                    fill=True,
                    fill_color=item.get("color", "#1473E6"),
                    fill_opacity=0.92,
                    tooltip=f"{item.get('name')} · {item.get('category')}",
                    popup=(
                        f"<b>{item.get('name')}</b><br>{item.get('category')}<br>"
                        f"Fuente: OpenStreetMap<br>Distancia al área: {distance:,.0f} m".replace(",", ".")
                    ),
                ).add_to(cluster)
            cluster.add_to(map_obj)

        if map_layers.get("metro_current"):
            for ref in CURRENT_LINE_ORDER:
                line = (bundle.get("metro_current") or {}).get(ref)
                if line and line.get("segments"):
                    add_metro_line(map_obj, line, future=False)

        if map_layers.get("metro_future"):
            for ref in FUTURE_LINE_ORDER:
                line = (bundle.get("metro_future") or {}).get(ref)
                if line and line.get("segments"):
                    add_metro_line(map_obj, line, future=True)

        if map_layers.get("osm_construction") and bundle.get("construction"):
            construction = folium.FeatureGroup(name=f"Construcciones OSM · {area_item['name']}", show=True)
            for item in bundle.get("construction") or []:
                folium.CircleMarker(
                    [item["lat"], item["lon"]],
                    radius=6,
                    color="#FF8A32",
                    weight=2,
                    fill=True,
                    fill_color="#FF8A32",
                    fill_opacity=0.92,
                    tooltip=item.get("name"),
                ).add_to(construction)
            construction.add_to(map_obj)

        future_visible = set(build_source_plan(map_layers, bundle.get("filters") or {}).get("future_gis") or [])
        for source_id, result in (bundle.get("future_gis") or {}).items():
            if source_id in future_visible:
                add_geojson_result(map_obj, source_label(source_id), result, "#F5A400")
        visible_territory = set(map_layers.get("territory") or [])
        if map_layers.get("road_network"):
            visible_territory.add("mop_red_vial")
        for source_id, result in (bundle.get("technical") or {}).items():
            if source_id in visible_territory:
                add_geojson_result(map_obj, source_label(source_id), result, "#1677B8")
        visible_risks = set(map_layers.get("risks") or [])
        for source_id, result in (bundle.get("risks") or {}).items():
            if source_id in visible_risks:
                add_geojson_result(map_obj, source_label(source_id), result, "#E74C5B")

    legend = legend_html(st.session_state.last_applied_layers)
    if legend:
        map_obj.get_root().html.add_child(folium.Element(legend))

    folium.LayerControl(collapsed=True).add_to(map_obj)
    map_state = st_folium(
        map_obj,
        width=None,
        height=760,
        key="landfinder_single_map",
        returned_objects=["last_clicked", "last_object_clicked"],
    )

    object_click = map_state.get("last_object_clicked") if map_state else None
    plain_click = map_state.get("last_clicked") if map_state else None
    if object_click:
        detail = nearest_detail(float(object_click["lat"]), float(object_click["lng"]))
        if detail:
            st.session_state.selected_detail = detail

    if st.session_state.adding_area and plain_click:
        click_key = f"{plain_click['lat']:.6f},{plain_click['lng']:.6f}"
        if click_key != st.session_state.last_area_click_key:
            st.session_state.pending_area_point = plain_click
            st.session_state.last_area_click_key = click_key
            st.rerun()


def render_detail_panel(detail: dict[str, Any]) -> None:
    with st.container(border=True):
        if st.button("← Volver al resumen", use_container_width=True):
            st.session_state.selected_detail = None
            st.rerun()
        st.markdown('<div class="lf-panel-title">Detalle del elemento</div>', unsafe_allow_html=True)
        st.write(f"**{detail.get('title') or 'Elemento'}**")
        st.caption(detail.get("category") or "Sin categoría")
        st.metric("Distancia al clic", f"{detail.get('distance', 0):,.0f} m".replace(",", "."))
        st.write(f"Fuente: **{detail.get('source')}**")
        st.write(f"Área relacionada: **{detail.get('area')}**")
        if detail.get("source_url"):
            st.markdown(f"[Abrir fuente original]({detail['source_url']})")
        metadata = detail.get("metadata") or {}
        if metadata:
            st.markdown("**Datos relevantes**")
            rows = []
            for key, value in metadata.items():
                if value not in (None, ""):
                    rows.append({"Campo": key, "Valor": str(value)[:180]})
                if len(rows) >= 8:
                    break
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_summary_panel(area: dict[str, Any] | None) -> None:
    with st.container(border=True):
        st.markdown('<div class="lf-panel-title">Resumen del área</div>', unsafe_allow_html=True)
        if not area:
            st.info("Selecciona o crea un área para comenzar el análisis territorial.")
            return

        bundle = st.session_state.map_bundle.get(area["id"], {})
        counts = bundle_counts(bundle)
        metro_value = "N/D"
        if bundle:
            metro_value = format_metro_summary(bundle.get("metro_summary"))
        risk_value = "Pendiente de fuente"
        if bundle and any(layer_id in bundle.get("layer_states", {}) for layer_id in RISK_LAYER_IDS):
            risk_value = "Sin riesgos detectados" if counts["risks"] == 0 else f"{counts['risks']} alertas"
        rows = [
            ("Área", f"{area['name']} · {compact_place_label(area['sector'], 34)}"),
            ("Superficie", f"{area_surface_km2(area):.1f} km2"),
            ("Uso de suelo", "Pendiente de fuente"),
            ("Metro cercano", metro_value),
            ("Riesgos", risk_value),
            ("Equipamiento", str(counts["assets"]) if bundle else "N/D"),
            ("Proyectos futuros", str(counts["future_records"]) if bundle else "N/D"),
            ("Terrenos encontrados", "No configurado"),
        ]
        html_rows = "".join(
            f"<div class='lf-summary-row'><span>{label}</span><b>{value}</b></div>"
            for label, value in rows
        )
        st.markdown(html_rows, unsafe_allow_html=True)

        metro_summary = bundle.get("metro_summary") if bundle else None
        if metro_summary:
            current_nearby = metro_summary.get("current_nearby") or []
            future_nearby = metro_summary.get("future_nearby") or []
            metro_rows = []
            station = metro_summary.get("nearest_station")
            if station:
                metro_rows.append(("Estación más cercana", f"{station.get('name')} · {format_distance_m(station.get('distance_m'))}"))
            if current_nearby:
                metro_rows.append((
                    "Líneas cercanas",
                    ", ".join(f"{item['ref']} · {format_distance_m(item.get('distance_to_area_m'))}" for item in current_nearby[:4]),
                ))
            metro_rows.append(("Estaciones dentro del área", str(metro_summary.get("stations_inside_count", 0))))
            if future_nearby:
                metro_rows.append((
                    "Metro futuro",
                    ", ".join(f"{item['ref']} · {format_distance_m(item.get('distance_to_area_m'))}" for item in future_nearby[:4]),
                ))
            st.markdown('<div class="lf-section-title">Transporte</div>', unsafe_allow_html=True)
            st.markdown(
                "".join(f"<div class='lf-summary-row'><span>{label}</span><b>{value}</b></div>" for label, value in metro_rows),
                unsafe_allow_html=True,
            )

    with st.container(border=True):
        st.markdown('<div class="lf-panel-title">Estado de fuentes</div>', unsafe_allow_html=True)
        bundle = st.session_state.map_bundle.get(area["id"], {})
        if not bundle:
            st.caption("Aplica filtros para consultar fuentes.")
        else:
            for layer_id, result in (bundle.get("layer_states") or {}).items():
                label = LAYER_DISPLAY_NAMES.get(
                    layer_id,
                    source_label(layer_id) if layer_id in SOURCE_BY_ID else layer_id.replace("_", " ").title(),
                )
                st.markdown(
                    f"<div class='lf-source-state'><b>{label}</b><br>{status_text(result)}</div>",
                    unsafe_allow_html=True,
                )
                if result.get("error"):
                    st.caption(clean_source_error(result.get("error")))


def render_compare_panel() -> None:
    with st.container(border=True):
        st.markdown('<div class="lf-panel-title">Comparar áreas</div>', unsafe_allow_html=True)
        areas = [area for area in st.session_state.areas if area.get("visible", True)]
        if len(areas) < 2:
            st.info("Crea y muestra al menos dos áreas para comparar.")
            return
        rows = []
        for area in areas:
            bundle = st.session_state.map_bundle.get(area["id"], {})
            counts = bundle_counts(bundle)
            rows.append(
                {
                    "Área": area["name"],
                    "Metro en área": counts["stations"] if bundle else None,
                    "Equipamientos": counts["assets"] if bundle else None,
                    "Proyectos": counts["future_records"] if bundle else None,
                    "Riesgos": counts["risks"] if bundle else None,
                    "Superficie km2": round(area_surface_km2(area), 1),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("La comparación usa solo datos consultados y mantiene todas las áreas sobre el mismo mapa.")


def render_reports_panel(area: dict[str, Any] | None) -> None:
    with st.container(border=True):
        st.markdown('<div class="lf-panel-title">Reportes</div>', unsafe_allow_html=True)
        if not area:
            st.info("Selecciona un área para generar evidencia.")
            return
        bundle = st.session_state.map_bundle.get(area["id"], {})
        if not bundle:
            st.warning("Primero aplica filtros para esta área.")
            return
        payload = {
            "area": area,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "counts": bundle_counts(bundle),
            "sources": {
                key: {
                    "status": value.get("status"),
                    "count": value.get("count"),
                    "error": value.get("error"),
                }
                for key, value in (bundle.get("layer_states") or {}).items()
            },
            "future_records": bundle.get("future_records", []),
        }
        st.download_button(
            "Descargar JSON",
            json.dumps(payload, ensure_ascii=False, indent=2),
            f"landfinder_{area['id']}_evidencia.json",
            "application/json",
            use_container_width=True,
        )


def render_next_panel(title: str, body: str) -> None:
    with st.container(border=True):
        st.markdown(f'<div class="lf-panel-title">{title}</div>', unsafe_allow_html=True)
        st.markdown(f"<div class='lf-next'>{body}</div>", unsafe_allow_html=True)


def render_profile_panel() -> None:
    profile = st.session_state.profile
    with st.container(border=True):
        st.markdown('<div class="lf-panel-title">Perfil</div>', unsafe_allow_html=True)
        with st.form("profile_form"):
            name = st.text_input("Nombre", profile["name"])
            email = st.text_input("Correo", profile["email"])
            role_options = [
                "Planificador",
                "Corredor / consultor",
                "Constructora",
                "Entidad patrocinante",
                "Inmobiliaria",
                "Arquitectura / ingeniería",
                "Personal",
            ]
            role = st.selectbox("Uso principal", role_options, index=role_options.index(profile["role"]) if profile["role"] in role_options else 0)
            plan = st.selectbox("Plan", ["Free", "Pro", "Empresa"], index=["Free", "Pro", "Empresa"].index(profile["plan"]))
            if st.form_submit_button("Guardar"):
                st.session_state.profile.update({"name": name, "email": email, "role": role, "plan": plan})
                st.success("Perfil actualizado en esta sesión.")


def render_admin_panel() -> None:
    with st.container(border=True):
        st.markdown('<div class="lf-panel-title">Admin/API</div>', unsafe_allow_html=True)
        st.caption("Panel interno para health checks. No bloquea el mapa.")
        priorities = st.multiselect("Prioridades", ["P0", "P1", "P2", "P3"], default=["P0", "P1"])
        sources = [source for source in SOURCES if source["priority"] in priorities]
        if st.button("Probar APIs", type="primary", use_container_width=True):
            progress = st.progress(0)
            for index, source in enumerate(sources, 1):
                result = probe_source(source, int(source_config(source)["timeout"])).to_dict()
                st.session_state.api_results[source["id"]] = result
                save_result(result)
                progress.progress(index / len(sources))
        rows = []
        for source in sources:
            result = st.session_state.api_results.get(source["id"])
            health = health_state(result)["status"] if result else "idle"
            latency = result.get("latency_ms") if result else None
            rows.append({
                "Fuente": source["name"],
                "Estado": health,
                "Latencia": f"{latency} ms" if latency is not None else "-",
                "Gate": source["legal_gate"],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        with st.expander("Historial"):
            history = load_history()
            if history:
                st.dataframe(pd.DataFrame(history).head(100), use_container_width=True, hide_index=True)
            else:
                st.info("Sin historial técnico.")


def render_right_panel(area: dict[str, Any] | None) -> None:
    detail = st.session_state.selected_detail
    if detail:
        render_detail_panel(detail)
        return
    mode = st.session_state.mode
    if mode == "Comparar":
        render_compare_panel()
    elif mode == "Reportes":
        render_reports_panel(area)
    elif mode == "Proyectos":
        render_next_panel("Proyectos", "Workspace preparado para guardar áreas, responsables y reportes. Persistencia cloud pendiente.")
    elif mode == "Alertas":
        render_next_panel("Alertas", "La arquitectura de fuentes ya permite monitoreo futuro; las alertas programadas quedan fuera del MVP local.")
    elif mode == "Perfil":
        render_profile_panel()
    elif mode == "Admin/API":
        render_admin_panel()
    else:
        render_summary_panel(area)


init_state()
render_theme_overrides()
render_header(st.session_state.profile)

top_left, top_search, top_nav = st.columns([0.16, 0.50, 0.34], gap="small")
with top_left:
    panel_col, theme_col = st.columns([0.58, 0.42], gap="small")
    with panel_col:
        if st.button("Capas" if not st.session_state.left_panel_open else "Panel", use_container_width=True):
            st.session_state.left_panel_open = not st.session_state.left_panel_open
            st.rerun()
    with theme_col:
        next_theme = "Claro" if st.session_state.page_theme == "Oscuro" else "Oscuro"
        if st.button(next_theme, use_container_width=True):
            st.session_state.page_theme = next_theme
            st.rerun()
with top_search:
    with st.form("global_search"):
        c1, c2 = st.columns([0.78, 0.22])
        query = c1.text_input("Buscar", placeholder="Buscar dirección, comuna, sector o coordenadas...", label_visibility="collapsed")
        search_clicked = c2.form_submit_button("Buscar")
    if search_clicked and query:
        with st.spinner("Geocodificando ubicación..."):
            resolved = resolve_search(query)
        if resolved:
            st.session_state.map_center = (resolved[0], resolved[1])
            st.session_state.map_zoom = resolved[2]
            message = f"Mapa centrado en {compact_place_label(resolved[3])}."
            if hasattr(st, "toast"):
                st.toast(message)
            else:
                st.success(message)
        else:
            st.warning("No encontré esa ubicación. Prueba agregar comuna/ciudad, por ejemplo `Av. Irarrázaval 2401, Ñuñoa`, o usa coordenadas `lat,lng`.")
with top_nav:
    previous_mode = st.session_state.mode
    picked_mode = st.pills(
        "Modo",
        ["Explorar", "Comparar", "Reportes", "Proyectos", "Alertas", "Perfil"],
        default=st.session_state.mode,
        selection_mode="single",
        label_visibility="collapsed",
    )
    if picked_mode:
        st.session_state.mode = picked_mode
    if st.session_state.mode != previous_mode:
        st.session_state.selected_detail = None

current_area = active_area()
if st.session_state.left_panel_open:
    left, center, right = st.columns([0.22, 0.58, 0.20], gap="small")
    with left:
        render_left_panel(current_area)
else:
    center, right = st.columns([0.76, 0.24], gap="small")

with center:
    if current_area:
        st.markdown(
            f"<div class='lf-map-hint'><b>Área activa</b> {current_area['name']} · {compact_place_label(current_area['sector'], 58)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='lf-map-hint'>Sin áreas todavía. Usa + Nueva área o busca una dirección para ubicarte.</div>",
            unsafe_allow_html=True,
        )
    render_map()

with right:
    render_right_panel(active_area())

if st.session_state.pending_filter_apply:
    current = active_area()
    target_areas = [current] if current else []
    if target_areas:
        apply_filters_to_targets(target_areas)
        st.rerun()

st.caption(
    "Landfinder Chile MVP · Prefactibilidad territorial. Las fuentes externas pertenecen a sus proveedores y pueden requerir validación legal, credenciales o estabilidad adicional."
)
