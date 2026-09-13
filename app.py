from __future__ import annotations

import json
import math
import html
import time
from datetime import datetime
from typing import Any

import folium
import pandas as pd
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium

from landfinder.area_results import (
    layer_snapshot_changed,
    layer_snapshot_has_active_layers,
    make_area_bundle,
    source_cache_key,
    store_area_bundle,
    with_area_context,
)
from landfinder.basemaps import basemap_for_theme
from landfinder.config import USER_AGENT, source_config
from landfinder.filter_model import build_source_plan, renderable_area_geometries
from landfinder.geocoder import (
    geocode_address as geocode_address_structured,
    parse_coordinates as parse_coordinates_structured,
    requested_house_number as requested_house_number_structured,
)
from landfinder.icons import legend_symbol_html, marker_icon
from landfinder.map_engine import load_map_source
from landfinder.metro_adapter import metro_area_summary, metro_current_for_area, metro_dataset_status, metro_future_for_area
from landfinder.persistent_cache import (
    CACHE_SCHEMA_VERSION,
    cache_age_seconds,
    cache_digest,
    cache_payload_is_valid,
    delete_persistent_cache,
    read_persistent_cache,
    write_persistent_cache,
)
from landfinder.probes import health_state, probe_source
from landfinder.progress import progress_summary, source_progress
from landfinder.registry import load_sources
from landfinder.runtime_sources import provider_key_for
from landfinder.source_states import (
    CIRCUIT_OPEN,
    ERROR,
    FAILURE_STATES,
    LOADING,
    MISSING_DATA,
    NOT_CONFIGURED,
    NOT_REQUESTED,
    RATE_LIMITED,
    STALE,
    SUCCESS_DATA,
    SUCCESS_EMPTY,
    TERMINAL_STATES,
    TIMEOUT,
    VISUAL_ONLY,
    classify_runtime_error,
    normalize_status,
    source_result_count,
)
from landfinder.storage import load_history, save_result
from landfinder.summaries import land_use_summary_value, result_pipeline_counts
from landfinder.urban_value import (
    ASSET_TYPES,
    CURRENT_LINE_ORDER,
    FUTURE_LINE_ORDER,
    METRO_COLORS,
    haversine_m,
    query_built_assets_with_audit,
    query_osm_construction,
)


SOURCES = load_sources()
SOURCE_BY_ID = {source["id"]: source for source in SOURCES}

AREA_COLORS = ["#1473E6", "#16A36A", "#E74C5B", "#8E44AD", "#F39C12"]
SANTIAGO_CENTER = (-33.4489, -70.6693)
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

BASIC_SUMMARY_LAYERS = {
    "built": [],
    "metro_current": True,
    "metro_future": False,
    "road_network": False,
    "osm_construction": False,
    "seia": True,
    "mop": False,
    "territory": ["minvu_prms_uso_suelo"],
    "risks": ["minvu_area_riesgo", "dga_prohibiciones"],
}

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

.lf-source-detail {
  border-left:4px solid #1473E6;
  background:#0D1726;
  padding:9px 10px;
  border-radius:6px;
  margin:2px 0 6px;
  font-size:12px;
}

.lf-source-detail.is-loading {
  border-left-color:#F5A400;
}

.lf-source-detail.is-failed {
  border-left-color:#E74C5B;
}

.lf-source-detail.is-waiting {
  border-left-color:#91A4BC;
}

.lf-source-track {
  height:7px;
  margin:4px 0 7px;
}

.lf-source-pipeline {
  color:#91A4BC;
  font-size:11px;
}

.lf-progress-card {
  background:#0D1726;
  border:1px solid #24537D;
  border-radius:8px;
  padding:10px 12px;
  margin:0 0 8px;
  box-shadow:0 12px 24px rgba(0,0,0,.22);
}

.lf-progress-top {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  color:#EAF2FF;
  font-size:13px;
}

.lf-progress-track {
  width:100%;
  height:9px;
  border-radius:999px;
  background:#1E314A;
  overflow:hidden;
  margin:8px 0 6px;
}

.lf-progress-fill {
  height:100%;
  background:#1473E6;
  border-radius:999px;
}

.lf-progress-meta {
  color:#BFD1E8;
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
    return parse_coordinates_structured(text)


def requested_house_number(text: str) -> str | None:
    return requested_house_number_structured(text)


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def geocode_address(text: str) -> dict[str, Any] | None:
    try:
        result = geocode_address_structured(text)
    except Exception:
        return None
    if not result or result.get("precision") == "NOT_FOUND" or result.get("lat") is None or result.get("lon") is None:
        return None
    return result


def resolve_search_structured(text: str) -> dict[str, Any] | None:
    return geocode_address(text)


def resolve_search(text: str) -> tuple[float, float, int, str] | None:
    resolved = resolve_search_structured(text)
    if not resolved:
        return None
    return resolved["lat"], resolved["lon"], resolved["zoom"], resolved["display_name"]


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
    if "overpass" in error.lower():
        return (
            "OpenStreetMap/Overpass no respondió a tiempo. "
            "Los datos OSM pueden seguir visibles si existe caché local."
        )
    if "HTTPSConnectionPool" in error or "ConnectionError" in error or "Max retries exceeded" in error:
        return "Proveedor temporalmente no disponible. Puedes reintentar esta fuente o continuar con las demás."
    if "timed out" in error.lower() or "timeout" in error.lower():
        return "La fuente demoró demasiado y fue aislada de las demás."
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
        .lf-source-state, .lf-source-detail, .lf-next, .lf-progress-card {
          background: var(--lf-panel-2) !important;
          color: var(--lf-ink) !important;
          border-color: var(--lf-line) !important;
        }
        .lf-progress-top, .lf-progress-top * {
          color: var(--lf-ink) !important;
        }
        .lf-progress-track {
          background:#DCE8F6 !important;
        }
        .lf-progress-meta,
        .lf-source-pipeline {
          color: var(--lf-muted) !important;
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
        "source_status_by_area": {},
        "source_circuits": {},
        "source_progress": {},
        "active_request_id": None,
        "active_source_job": None,
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
        "last_search_location": None,
        "adjusting_search_location": False,
        "pending_adjusted_location": None,
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
        "pending_layer_apply": False,
        "pending_summary_apply": False,
        "geocoder_candidates": [],
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


def merged_layer_snapshot(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "built": list(dict.fromkeys([*(base.get("built") or []), *(extra.get("built") or [])])),
        "metro_current": bool(base.get("metro_current") or extra.get("metro_current")),
        "metro_future": bool(base.get("metro_future") or extra.get("metro_future")),
        "road_network": bool(base.get("road_network") or extra.get("road_network")),
        "osm_construction": bool(base.get("osm_construction") or extra.get("osm_construction")),
        "seia": bool(base.get("seia") or extra.get("seia")),
        "mop": bool(base.get("mop") or extra.get("mop")),
        "territory": list(dict.fromkeys([*(base.get("territory") or []), *(extra.get("territory") or [])])),
        "risks": list(dict.fromkeys([*(base.get("risks") or []), *(extra.get("risks") or [])])),
    }


def should_show(label: str, terms: list[str]) -> bool:
    query = normalize_query(st.session_state.layer_search)
    if not query:
        return True
    return query in normalize_query(" ".join([label, *terms]))


def status_text(result: dict[str, Any] | None) -> str:
    if not result:
        return "Sin consultar"
    status = normalize_status(result.get("status"), result.get("count"))
    count = result.get("count")
    duration = result.get("duration_ms")
    cache = result.get("cache")
    suffix_parts = []
    if isinstance(duration, int) and duration > 0:
        suffix_parts.append(f"{duration} ms")
    if cache in {"HIT", "STALE"}:
        suffix_parts.append("cache" if cache == "HIT" else "cache anterior")
    suffix = f" · {' · '.join(suffix_parts)}" if suffix_parts else ""
    if status == SUCCESS_DATA:
        return f"{count or 0} elementos{suffix}"
    if status == SUCCESS_EMPTY:
        return f"Sin coincidencias en el área{suffix}"
    if status == VISUAL_ONLY:
        return f"Capa visual disponible{suffix}"
    if status == LOADING:
        return "Cargando fuente..."
    if status == NOT_REQUESTED:
        return "En cola"
    if status == STALE:
        return f"Fuente pausada; mostrando cache anterior ({count or 0})"
    if status == TIMEOUT:
        return f"La fuente demoró demasiado{suffix}"
    if status == RATE_LIMITED:
        return f"Proveedor limitó las consultas{suffix}"
    if status == CIRCUIT_OPEN:
        return "Circuito abierto por fallos repetidos"
    if status == NOT_CONFIGURED:
        return "Fuente no configurada"
    if status == MISSING_DATA:
        return "Dataset no disponible"
    if status == ERROR:
        return f"No disponible temporalmente{suffix}"
    return status or "Sin estado"


def display_label_for_source(layer_id: str) -> str:
    if layer_id.startswith("built_"):
        return ASSET_TYPES.get(layer_id.removeprefix("built_"), {}).get("label", layer_id)
    return LAYER_DISPLAY_NAMES.get(
        layer_id,
        source_label(layer_id) if layer_id in SOURCE_BY_ID else layer_id.replace("_", " ").title(),
    )


def source_state_ratio(result: dict[str, Any] | None) -> float:
    status = normalize_status((result or {}).get("status"), (result or {}).get("count"))
    if status in TERMINAL_STATES:
        return 1.0
    if status == LOADING:
        return 0.45
    return 0.0


def source_state_class(result: dict[str, Any] | None) -> str:
    status = normalize_status((result or {}).get("status"), (result or {}).get("count"))
    if status == LOADING:
        return "is-loading"
    if status in FAILURE_STATES:
        return "is-failed"
    if status == NOT_REQUESTED:
        return "is-waiting"
    return "is-ready"


def source_duration_text(result: dict[str, Any] | None) -> str:
    duration = (result or {}).get("duration_ms")
    if isinstance(duration, int) and duration > 0:
        return f"{duration / 1000:.1f} s"
    if normalize_status((result or {}).get("status"), (result or {}).get("count")) == LOADING:
        return "en curso"
    return "-"


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
        for result in (bundle.get("restriction_data") or {}).values()
        if normalize_status(result.get("status"), result.get("count")) == SUCCESS_DATA
    )
    territory = sum(
        int(result.get("count") or 0)
        for result in (bundle.get("technical") or {}).values()
        if normalize_status(result.get("status"), result.get("count")) == SUCCESS_DATA
    )
    return {
        "assets": len(bundle.get("assets") or []),
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
        return "No consultado"
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


def layer_state(bundle: dict[str, Any], source_id: str) -> dict[str, Any] | None:
    return (bundle.get("layer_states") or {}).get(source_id)


def count_summary_value(bundle: dict[str, Any], count_key: str, source_ids: list[str]) -> str:
    if not bundle:
        return "No consultado"
    states = [layer_state(bundle, source_id) for source_id in source_ids if layer_state(bundle, source_id)]
    if not states:
        return "No consultado"
    statuses = [normalize_status(state.get("status"), state.get("count")) for state in states]
    if any(status in FAILURE_STATES for status in statuses):
        return "Temporalmente no disponible"
    if any(status in {NOT_CONFIGURED, MISSING_DATA} for status in statuses):
        return "Fuente no configurada"
    return str(bundle_counts(bundle)[count_key])


def risk_summary_value(bundle: dict[str, Any]) -> str:
    if not bundle:
        return "No consultado"
    risk_states = [
        layer_state(bundle, source_id)
        for source_id in RISK_LAYER_IDS
        if layer_state(bundle, source_id)
    ]
    if not risk_states:
        return "No consultado"
    statuses = [normalize_status(state.get("status"), state.get("count")) for state in risk_states]
    if any(status in FAILURE_STATES or status in {NOT_CONFIGURED, MISSING_DATA} for status in statuses):
        missing = sum(1 for status in statuses if status in FAILURE_STATES or status in {NOT_CONFIGURED, MISSING_DATA})
        return f"Evaluación incompleta ({missing} fuentes)"
    count = bundle_counts(bundle)["risks"]
    return "Sin riesgos detectados" if count == 0 else f"{count} alertas"


def expected_layer_state_ids(snapshot: dict[str, Any], filters: dict[str, Any] | None = None) -> list[str]:
    plan = build_source_plan(snapshot, filters or {})
    ids = [f"built_{asset_type}" for asset_type in plan["built_query_types"]]
    if plan["metro_current"]:
        ids.append("metro_current")
    if plan["metro_future"]:
        ids.append("metro_future")
    if plan["osm_construction"]:
        ids.append("osm_construction")
    ids.extend(plan["future_gis"])
    ids.extend(plan["territory_sources"])
    ids.extend(plan["risk_sources"])
    return list(dict.fromkeys(ids))


def basic_summary_state_ids() -> list[str]:
    return expected_layer_state_ids(BASIC_SUMMARY_LAYERS, {})


def area_needs_visible_layers(area_id: str | None, snapshot: dict[str, Any]) -> bool:
    if not area_id or not layer_snapshot_has_active_layers(snapshot):
        return False
    bundle = st.session_state.map_bundle.get(area_id) or {}
    states = bundle.get("layer_states") or {}
    return any(
        normalize_status((states.get(source_id) or {}).get("status"), (states.get(source_id) or {}).get("count")) not in TERMINAL_STATES
        for source_id in expected_layer_state_ids(snapshot, {})
    )


def area_needs_basic_summary(area_id: str | None) -> bool:
    if not area_id:
        return False
    bundle = st.session_state.map_bundle.get(area_id) or {}
    states = bundle.get("layer_states") or {}
    return any(
        normalize_status((states.get(source_id) or {}).get("status"), (states.get(source_id) or {}).get("count")) not in TERMINAL_STATES
        for source_id in basic_summary_state_ids()
    )


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


def clear_map_layers() -> None:
    st.session_state.active_source_job = None
    st.session_state.active_request_id = None
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
    st.session_state.last_applied_layers = {
        "built": [],
        "metro_current": False,
        "metro_future": False,
        "road_network": False,
        "osm_construction": False,
        "seia": False,
        "mop": False,
        "territory": [],
        "risks": [],
    }
    st.session_state.pending_layer_apply = False


def clear_terrain_filters() -> None:
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


def clear_layers_and_filters() -> None:
    clear_map_layers()
    clear_terrain_filters()


def runtime_now() -> float:
    return time.time()


def cache_key_for(area: dict[str, Any], source_id: str, params: Any) -> str:
    return source_cache_key(area, source_id, params)


def source_label_for_runtime(source_id: str) -> str:
    return LAYER_DISPLAY_NAMES.get(source_id, source_label(source_id) if source_id in SOURCE_BY_ID else source_id)


def set_source_status(
    source_id: str,
    status: str,
    duration_ms: int,
    feature_count: int | None,
    cache: str,
    error: str | None = None,
    area_id: str | None = None,
    request_id: str | None = None,
) -> None:
    payload = {
        "status": status,
        "duration_ms": duration_ms,
        "feature_count": feature_count,
        "cache": cache,
        "error": error,
        "lastUpdated": datetime.now().isoformat(timespec="seconds"),
        "area_id": area_id,
        "request_id": request_id,
    }
    st.session_state.source_status[source_id] = payload
    if area_id:
        st.session_state.source_status_by_area.setdefault(area_id, {})[source_id] = payload
    print(
        f"[Landfinder][source] area={area_id or '-'} source={source_id} status={status} duration={duration_ms}ms "
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
    request_id: str | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    cfg = cfg or source_config(SOURCE_BY_ID.get(source_id, source_id))
    area_id = str(area.get("id"))
    key = cache_key_for(area, source_id, params)
    circuit_key = provider_key_for(source_id, SOURCE_BY_ID)
    cached = st.session_state.source_cache.get(key)
    if cached and not cache_payload_is_valid(cached):
        st.session_state.source_cache.pop(key, None)
        cached = None
    cached = cached or read_persistent_cache(key)
    if cached:
        st.session_state.source_cache[key] = cached
    ttl = int(cfg.get("cache_ttl_seconds", 0) or 0)
    now = runtime_now()
    if cached and ttl and now - float(cached.get("stored_at", 0)) <= ttl:
        result = cached["value"]
        count = cached.get("count")
        set_source_status(source_id, "cache_hit", 0, count, "HIT", area_id=area_id, request_id=request_id)
        state = with_area_context({
            "status": SUCCESS_DATA if (count or 0) > 0 else SUCCESS_EMPTY,
            "count": count,
            "error": None,
            "duration_ms": 0,
            "cache": "HIT",
            "cache_key": key,
            "cache_digest": cache_digest(key),
            "cache_age_seconds": cache_age_seconds(cached, now),
            "pipeline": (result or {}).get("pipeline") if isinstance(result, dict) else None,
        }, area_id, source_id, request_id)
        return result, state
    if cached:
        set_source_status(source_id, "refreshing", 0, cached.get("count"), "STALE", area_id=area_id, request_id=request_id)

    if not circuit_allows(circuit_key, cfg):
        count = cached.get("count") if cached else None
        if cached:
            set_source_status(source_id, "circuit_open_cache", 0, count, "STALE", area_id=area_id, request_id=request_id)
            state = with_area_context({
                "status": STALE,
                "count": count,
                "error": None,
                "duration_ms": 0,
                "cache": "STALE",
                "cache_key": key,
                "cache_digest": cache_digest(key),
                "cache_age_seconds": cache_age_seconds(cached, now),
            }, area_id, source_id, request_id)
            return cached["value"], state
        error = "Fuente pausada temporalmente por fallos repetidos. Reintenta más tarde."
        set_source_status(source_id, "circuit_open", 0, None, "MISS", error, area_id=area_id, request_id=request_id)
        return None, with_area_context({"status": CIRCUIT_OPEN, "count": None, "error": error, "duration_ms": 0, "cache": "MISS"}, area_id, source_id, request_id)

    start = time.perf_counter()
    try:
        result = producer()
        duration_ms = int((time.perf_counter() - start) * 1000)
        count = source_result_count(result)
        cached_payload = {
            "value": result,
            "stored_at": now,
            "count": count,
            "lastUpdated": datetime.now().isoformat(timespec="seconds"),
            "schema_version": CACHE_SCHEMA_VERSION,
            "source_id": source_id,
            "area_id": area_id,
            "params": params,
            "cache_key": key,
        }
        st.session_state.source_cache[key] = cached_payload
        if count is not None:
            write_persistent_cache(key, cached_payload)
        record_circuit_success(circuit_key)
        set_source_status(source_id, "success", duration_ms, count, "MISS", area_id=area_id, request_id=request_id)
        state = with_area_context({
            "status": SUCCESS_DATA if (count or 0) > 0 else SUCCESS_EMPTY,
            "count": count,
            "error": None,
            "duration_ms": duration_ms,
            "cache": "MISS",
            "cache_key": key,
            "cache_digest": cache_digest(key),
            "cache_age_seconds": 0,
            "pipeline": result.get("pipeline") if isinstance(result, dict) else None,
        }, area_id, source_id, request_id)
        return result, state
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        error = str(exc)
        status = classify_runtime_error(error)
        record_circuit_failure(circuit_key, cfg)
        if cached:
            count = cached.get("count")
            set_source_status(source_id, "stale_cache", duration_ms, count, "STALE", error, area_id=area_id, request_id=request_id)
            return cached["value"], with_area_context({
                "status": STALE,
                "count": count,
                "error": error,
                "duration_ms": duration_ms,
                "cache": "STALE",
                "cache_key": key,
                "cache_digest": cache_digest(key),
                "cache_age_seconds": cache_age_seconds(cached, now),
            }, area_id, source_id, request_id)
        set_source_status(source_id, "timeout" if status == TIMEOUT else "error", duration_ms, None, "MISS", error, area_id=area_id, request_id=request_id)
        return None, with_area_context({"status": status, "count": None, "error": error, "duration_ms": duration_ms, "cache": "MISS"}, area_id, source_id, request_id)


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
    location = area.get("search_location")
    if location:
        add_location_marker(map_obj, location, area_name=area["name"])
    else:
        folium.CircleMarker(
            [area["lat"], area["lon"]],
            radius=8,
            color="#FFFFFF",
            weight=3,
            fill=True,
            fill_color=color,
            fill_opacity=1,
            tooltip=f"{area['name']} · centro de análisis",
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


def add_location_marker(map_obj: folium.Map, location: dict[str, Any], area_name: str | None = None) -> None:
    precision = location.get("precision") or "unknown"
    label = "Ubicación encontrada" if precision == "EXACT" else "Ubicación aproximada"
    if area_name:
        label = f"{label} · {area_name}"
    folium.Marker(
        [float(location["lat"]), float(location["lon"])],
        icon=marker_icon("selected_location"),
        tooltip=f"{label}: {compact_place_label(location.get('display_name') or location.get('query') or '', 72)}",
        popup=(
            f"<b>{label}</b><br>"
            f"{compact_place_label(location.get('display_name') or '', 120)}<br>"
            f"Precisión: {precision}<br>"
            f"Número coincidente: {'sí' if location.get('house_number_matched') else 'no'}"
        ),
    ).add_to(map_obj)


def render_map_progress_card(area: dict[str, Any] | None) -> None:
    if not area:
        return
    bundle = st.session_state.map_bundle.get(area["id"], {})
    if not bundle:
        return
    summary = progress_summary(bundle)
    if not summary["total"]:
        return
    label = "Análisis completado" if summary["complete"] else f"Analizando {area['name']}"
    warning_text = f"{summary['warnings']} con advertencias" if summary["warnings"] else "sin advertencias"
    st.markdown(
        f"""
        <div class="lf-progress-card">
          <div class="lf-progress-top"><b>{label}</b><span>{summary['done']} / {summary['total']}</span></div>
          <div class="lf-progress-track"><div class="lf-progress-fill" style="width:{summary['ratio'] * 100:.1f}%"></div></div>
          <div class="lf-progress-meta">{summary['total']} fuentes · {summary['duration_ms'] / 1000:.1f} s · {warning_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
    for station in line.get("stations") or []:
        if future:
            folium.Marker(
                [station["lat"], station["lon"]],
                icon=marker_icon("metro_future", 30),
                tooltip=f"{station.get('name')} · {ref}",
            ).add_to(group)
        else:
            folium.CircleMarker(
                [station["lat"], station["lon"]],
                radius=4,
                color="#FFFFFF",
                weight=1.5,
                fill=True,
                fill_color=color,
                fill_opacity=1,
                tooltip=f"Metro {ref} · {station.get('name')}",
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


def legend_html(snapshot: dict[str, Any], dark: bool) -> str:
    items = []
    for asset_type in snapshot.get("built") or []:
        cfg = ASSET_TYPES.get(asset_type)
        if cfg:
            items.append((asset_type, cfg["label"], "icon"))
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
    for color_or_key, label, kind in items[:18]:
        if kind == "line":
            color = color_or_key
            symbol = f"<span style='display:inline-block;width:22px;border-top:4px solid {color};'></span>"
        elif kind == "dash":
            color = color_or_key
            symbol = f"<span style='display:inline-block;width:22px;border-top:4px dashed {color};'></span>"
        elif kind == "poly":
            color = color_or_key
            symbol = f"<span style='display:inline-block;width:14px;height:10px;background:{color}33;border:2px solid {color};'></span>"
        elif kind == "icon":
            symbol = legend_symbol_html(color_or_key)
        else:
            color = color_or_key
            symbol = f"<span style='display:inline-block;width:10px;height:10px;background:{color};border-radius:50%;'></span>"
        rows.append(f"<span style='display:inline-flex;align-items:center;gap:6px;margin:4px 10px 4px 0;'>{symbol}{label}</span>")

    bg = "#0D1726" if dark else "#FFFFFF"
    border = "#24364D" if dark else "#D9E5F2"
    text = "#EAF2FF" if dark else "#123A5F"
    return f"""
    <details open style="position:absolute;left:18px;bottom:18px;z-index:9999;background:{bg};
                border:1px solid {border};border-radius:8px;padding:8px 10px;
                box-shadow:0 8px 24px rgba(9,33,59,.18);font-size:12px;color:{text};
                max-width:min(520px,calc(100% - 44px));max-height:168px;overflow:auto;">
      <summary style="cursor:pointer;font-weight:850;margin-bottom:4px;color:{text};">Leyenda</summary>
      <div style="display:flex;flex-wrap:wrap;align-items:center;">{''.join(rows)}</div>
    </details>
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
    if result.get("pipeline"):
        state["pipeline"] = result.get("pipeline")
    return state


def planned_source_ids(source_plan: dict[str, Any]) -> list[str]:
    ids = [f"built_{asset_type}" for asset_type in source_plan["built_query_types"]]
    if source_plan["metro_current"]:
        ids.append("metro_current")
    if source_plan["metro_future"]:
        ids.append("metro_future")
    if source_plan["osm_construction"]:
        ids.append("osm_construction")
    ids.extend(source_plan["future_gis"])
    ids.extend(source_plan["territory_sources"])
    ids.extend(source_plan["risk_sources"])
    return list(dict.fromkeys(ids))


def area_source_plan(
    snapshot: dict[str, Any],
    terrain_filters: dict[str, Any],
    summary: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    requested_snapshot = merged_layer_snapshot(snapshot, BASIC_SUMMARY_LAYERS) if summary else snapshot
    source_plan = build_source_plan(requested_snapshot, terrain_filters)
    source_plan["built_visual_types"] = sorted(set(snapshot.get("built") or []))
    source_plan["risk_visual_sources"] = list(snapshot.get("risks") or [])
    return requested_snapshot, source_plan


def empty_area_bundle(
    area: dict[str, Any],
    snapshot: dict[str, Any],
    requested_snapshot: dict[str, Any],
    terrain_filters: dict[str, Any],
    source_plan: dict[str, Any],
    request_id: str | None,
    summary: bool,
) -> dict[str, Any]:
    return {
        **make_area_bundle(area, request_id),
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
        "requested_layers": requested_snapshot,
        "summary": bool(summary),
        "loading_started_at": runtime_now(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def source_pending_state(area: dict[str, Any], source_id: str, request_id: str | None, status: str = NOT_REQUESTED) -> dict[str, Any]:
    state = with_area_context(
        {
            "status": status,
            "count": None,
            "error": None,
            "duration_ms": 0,
            "cache": "MISS",
            "lastUpdated": datetime.now().isoformat(timespec="seconds"),
        },
        str(area.get("id")),
        source_id,
        request_id,
    )
    st.session_state.source_status_by_area.setdefault(str(area.get("id")), {})[source_id] = state
    if status == LOADING:
        st.session_state.source_status[source_id] = state
    return state


def refresh_derived_bundle(area: dict[str, Any], bundle: dict[str, Any]) -> None:
    visual_types = set((bundle.get("source_plan") or {}).get("built_visual_types") or [])
    bundle["visual_assets"] = [
        item for item in (bundle.get("assets") or [])
        if item.get("type") in visual_types
    ]
    if bundle.get("metro_current") or bundle.get("metro_future"):
        bundle["metro_summary"] = metro_area_summary(
            bundle.get("metro_current") or {},
            bundle.get("metro_future") or {},
            area["lat"],
            area["lon"],
            area["radius_m"],
            nearby_threshold_m=float((bundle.get("filters") or {}).get("near_metro_distance", 1000) or 1000),
        )
    bundle["updated_at"] = datetime.now().isoformat(timespec="seconds")


def run_planned_source(
    area: dict[str, Any],
    bundle: dict[str, Any],
    source_id: str,
    request_id: str | None = None,
) -> None:
    source_plan = bundle["source_plan"]
    overpass_cfg = source_config("osm_overpass")
    overpass_timeout = int(overpass_cfg["timeout"])
    metro_cfg = source_config("metro_static")

    if source_id.startswith("built_"):
        asset_type = source_id.removeprefix("built_")
        if asset_type not in source_plan["built_query_types"]:
            return
        result, state = run_source(
            source_id,
            {"type": asset_type},
            area,
            lambda asset_type=asset_type: query_built_assets_with_audit(
                area["lat"],
                area["lon"],
                area["radius_m"],
                [asset_type],
                timeout=overpass_timeout,
            ),
            overpass_cfg,
            request_id=request_id,
        )
        items = (result or {}).get("items") if isinstance(result, dict) else (result or [])
        existing_ids = {
            (item.get("osm_type"), item.get("osm_id"), item.get("type"))
            for item in bundle.get("assets") or []
        }
        for item in items or []:
            item_key = (item.get("osm_type"), item.get("osm_id"), item.get("type"))
            if item_key not in existing_ids:
                bundle["assets"].append(item)
                existing_ids.add(item_key)
        pipeline = dict((state.get("pipeline") or {}))
        pipeline["rendered"] = len(items or []) if asset_type in source_plan["built_visual_types"] else 0
        bundle["layer_states"][source_id] = {**state, "pipeline": pipeline}
        refresh_derived_bundle(area, bundle)
        print(
            f"[SOURCE: OSM_POI] stored={len(bundle['assets'])} "
            f"rendered={len(bundle['visual_assets'])} visual_types={','.join(sorted(source_plan['built_visual_types'])) or 'none'}"
        )
        return

    if source_id == "metro_current" and source_plan["metro_current"]:
        result, state = run_source(
            "metro_current",
            {"dataset": "local_geojson"},
            area,
            lambda: metro_current_for_area(area["lat"], area["lon"], area["radius_m"], timeout=int(metro_cfg["timeout"])),
            metro_cfg,
            request_id=request_id,
        )
        bundle["metro_current"] = result or {}
        bundle["layer_states"]["metro_current"] = state
        refresh_derived_bundle(area, bundle)
        return

    if source_id == "metro_future" and source_plan["metro_future"]:
        future_dataset = metro_dataset_status("future")
        if future_dataset["status"] == MISSING_DATA:
            bundle["metro_future"] = {}
            bundle["layer_states"]["metro_future"] = with_area_context(
                {
                    "status": MISSING_DATA,
                    "count": None,
                    "error": future_dataset.get("error"),
                    "duration_ms": 0,
                    "cache": "MISS",
                    "dataset": future_dataset,
                },
                str(area.get("id")),
                "metro_future",
                request_id,
            )
        else:
            result, state = run_source(
                "metro_future",
                {"dataset": "local_geojson"},
                area,
                lambda: metro_future_for_area(area["lat"], area["lon"], area["radius_m"], timeout=int(metro_cfg["timeout"])),
                metro_cfg,
                request_id=request_id,
            )
            bundle["metro_future"] = result or {}
            available = sum(1 for line in bundle["metro_future"].values() if line.get("geometry_available"))
            bundle["layer_states"]["metro_future"] = {
                **state,
                "status": SUCCESS_DATA if available else SUCCESS_EMPTY,
                "count": available,
                "dataset": future_dataset,
            }
        refresh_derived_bundle(area, bundle)
        return

    if source_id == "osm_construction" and source_plan["osm_construction"]:
        result, state = run_source(
            "osm_construction",
            {"enabled": True},
            area,
            lambda: query_osm_construction(area["lat"], area["lon"], area["radius_m"], timeout=overpass_timeout),
            overpass_cfg,
            request_id=request_id,
        )
        bundle["construction"] = result or []
        bundle["future_records"] = [
            record for record in bundle.get("future_records", [])
            if record.get("Fuente") != "OpenStreetMap" or record.get("Estado") != "Construcción mapeada"
        ]
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
        refresh_derived_bundle(area, bundle)
        return

    if source_id in source_plan["future_gis"]:
        source = SOURCE_BY_ID.get(source_id)
        if not source:
            return
        cfg = source_config(source)
        result, state = run_source(
            source_id,
            {"kind": "future_gis"},
            area,
            lambda source=source, cfg=cfg: load_map_source(source, area["lat"], area["lon"], area["radius_m"], cfg["timeout"], 500),
            cfg,
            request_id=request_id,
        )
        result = result or {"status": state.get("status", ERROR), "type": None, "layers": [], "records": [], "count": None, "error": state.get("error")}
        bundle["future_gis"][source_id] = result
        bundle["future_records"] = [
            record for record in bundle.get("future_records", [])
            if record.get("Fuente") != source_label(source_id)
        ]
        for record in result.get("records") or []:
            bundle["future_records"].append(
                {
                    "Fuente": record.get("Fuente") or source_label(source_id),
                    "Elemento": record.get("Elemento"),
                    "Estado": "Registro de fuente",
                    "Distancia_m": record.get("Distancia_m"),
                }
            )
        bundle["layer_states"][source_id] = state_from_map_result(result, state)
        refresh_derived_bundle(area, bundle)
        return

    if source_id in source_plan["territory_sources"]:
        source = SOURCE_BY_ID.get(source_id)
        if not source:
            return
        cfg = source_config(source)
        result, state = run_source(
            source_id,
            {"kind": "territory"},
            area,
            lambda source=source, cfg=cfg: load_map_source(source, area["lat"], area["lon"], area["radius_m"], cfg["timeout"], 500),
            cfg,
            request_id=request_id,
        )
        result = result or {"status": state.get("status", ERROR), "type": None, "layers": [], "records": [], "count": None, "error": state.get("error")}
        bundle["technical"][source_id] = result
        bundle["layer_states"][source_id] = state_from_map_result(result, state)
        refresh_derived_bundle(area, bundle)
        return

    if source_id in source_plan["risk_sources"]:
        source = SOURCE_BY_ID.get(source_id)
        if not source:
            return
        cfg = source_config(source)
        result, state = run_source(
            source_id,
            {"kind": "risks"},
            area,
            lambda source=source, cfg=cfg: load_map_source(source, area["lat"], area["lon"], area["radius_m"], cfg["timeout"], 500),
            cfg,
            request_id=request_id,
        )
        result = result or {"status": state.get("status", ERROR), "type": None, "layers": [], "records": [], "count": None, "error": state.get("error")}
        bundle["restriction_data"][source_id] = result
        if source_id in source_plan["risk_visual_sources"]:
            bundle["risks"][source_id] = result
        bundle["layer_states"][source_id] = state_from_map_result(result, state)
        refresh_derived_bundle(area, bundle)


def query_area(
    area: dict[str, Any],
    snapshot: dict[str, Any],
    request_id: str | None = None,
    summary: bool = False,
) -> dict[str, Any]:
    terrain_filters = dict(st.session_state.filters)
    requested_snapshot, source_plan = area_source_plan(snapshot, terrain_filters, summary)
    bundle = empty_area_bundle(area, snapshot, requested_snapshot, terrain_filters, source_plan, request_id, summary)
    for source_id in planned_source_ids(source_plan):
        run_planned_source(area, bundle, source_id, request_id)
    return bundle


def start_area_source_job(area: dict[str, Any], summary: bool = False) -> None:
    snapshot = selected_layer_snapshot()
    terrain_filters = dict(st.session_state.filters)
    requested_snapshot, source_plan = area_source_plan(snapshot, terrain_filters, summary)
    request_id = f"{runtime_now():.6f}"
    st.session_state.active_request_id = request_id
    if not summary:
        st.session_state.last_applied_layers = snapshot

    fresh_bundle = empty_area_bundle(area, snapshot, requested_snapshot, terrain_filters, source_plan, request_id, summary)
    existing_bundle = st.session_state.map_bundle.get(area["id"]) or {}
    bundle = existing_bundle if existing_bundle.get("area_id") == area["id"] else fresh_bundle
    for key, value in fresh_bundle.items():
        if key in {
            "assets",
            "visual_assets",
            "metro_current",
            "metro_future",
            "construction",
            "future_records",
            "future_gis",
            "technical",
            "risks",
            "restriction_data",
            "layer_states",
        }:
            bundle.setdefault(key, value)
        else:
            bundle[key] = value
    bundle["risks"] = {
        source_id: result
        for source_id, result in (bundle.get("restriction_data") or {}).items()
        if source_id in source_plan["risk_visual_sources"]
    }
    refresh_derived_bundle(area, bundle)
    source_ids = planned_source_ids(source_plan)
    for source_id in source_ids:
        state = (bundle.get("layer_states") or {}).get(source_id) or {}
        if normalize_status(state.get("status"), state.get("count")) not in TERMINAL_STATES:
            bundle["layer_states"][source_id] = source_pending_state(area, source_id, request_id)
    store_area_bundle(st.session_state.map_bundle, area["id"], bundle)
    st.session_state.active_source_job = {
        "area_id": area["id"],
        "request_id": request_id,
        "source_ids": source_ids,
        "cursor": 0,
        "summary": bool(summary),
        "started_at": runtime_now(),
    }
    st.session_state.pending_filter_apply = False
    st.session_state.pending_layer_apply = False
    st.session_state.pending_summary_apply = False


def advance_active_source_job() -> bool:
    job = st.session_state.get("active_source_job")
    if not job:
        return False
    area = get_area(job.get("area_id"))
    if not area:
        st.session_state.active_source_job = None
        return False
    request_id = job.get("request_id")
    if st.session_state.get("active_request_id") != request_id:
        st.session_state.active_source_job = None
        return False
    bundle = st.session_state.map_bundle.get(area["id"])
    if not bundle or bundle.get("request_id") != request_id:
        st.session_state.active_source_job = None
        return False

    source_ids = list(job.get("source_ids") or [])
    cursor = int(job.get("cursor") or 0)
    loading_source_id = job.get("loading_source_id")
    if loading_source_id:
        run_planned_source(area, bundle, loading_source_id, request_id)
        if loading_source_id in source_ids:
            cursor = max(cursor, source_ids.index(loading_source_id) + 1)
        job["cursor"] = cursor
        job.pop("loading_source_id", None)
        store_area_bundle(st.session_state.map_bundle, area["id"], bundle)
        st.session_state.active_source_job = job
        return True

    while cursor < len(source_ids):
        source_id = source_ids[cursor]
        state = (bundle.get("layer_states") or {}).get(source_id) or {}
        if normalize_status(state.get("status"), state.get("count")) in TERMINAL_STATES:
            cursor += 1
            job["cursor"] = cursor
            continue
        bundle["layer_states"][source_id] = source_pending_state(area, source_id, request_id, LOADING)
        job["loading_source_id"] = source_id
        store_area_bundle(st.session_state.map_bundle, area["id"], bundle)
        st.session_state.active_source_job = job
        return True

    st.session_state.active_source_job = None
    st.session_state.last_apply_message = datetime.now().isoformat(timespec="seconds")
    st.session_state.pending_filter_apply = False
    st.session_state.pending_layer_apply = False
    st.session_state.pending_summary_apply = False
    return False


def apply_filters_to_targets(target_areas: list[dict[str, Any]], progress_slot=None, summary: bool = False) -> None:
    snapshot = selected_layer_snapshot()
    if not summary:
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
        bundle = query_area(area, snapshot, request_id, summary=summary)
        store_area_bundle(st.session_state.map_bundle, area["id"], bundle)
        if progress:
            progress.progress(index / len(target_areas), text=f"{area['name']} listo")
    if status:
        status.success("Filtros aplicados. Las fuentes con error quedaron aisladas del resto.")
    st.session_state.last_apply_message = datetime.now().isoformat(timespec="seconds")
    st.session_state.pending_filter_apply = False
    st.session_state.pending_layer_apply = False
    st.session_state.pending_summary_apply = False


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
            clear_terrain_filters()
            st.rerun()
        return c2.button("Buscar terrenos", type="primary", use_container_width=True)


def render_left_panel(area: dict[str, Any] | None) -> None:
    apply_clicked = False
    layer_snapshot_before = selected_layer_snapshot()

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
                    if area_needs_visible_layers(selected_id, selected_layer_snapshot()):
                        st.session_state.pending_layer_apply = True
                    elif area_needs_basic_summary(selected_id):
                        st.session_state.pending_summary_apply = True
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
                    resolved_area = resolve_search_structured(address) if address.strip() else None
                    if not resolved_area and not address.strip() and st.session_state.get("last_search_location"):
                        candidate_location = st.session_state.last_search_location
                        if (
                            candidate_location.get("lat") is not None
                            and candidate_location.get("lon") is not None
                            and abs(float(lat) - float(candidate_location["lat"])) < 0.00001
                            and abs(float(lon) - float(candidate_location["lon"])) < 0.00001
                        ):
                            resolved_area = dict(candidate_location)
                    if address.strip() and not resolved_area:
                        st.warning("No pude resolver esa dirección. Agrega comuna/ciudad, por ejemplo `Santa Raquel 8204, La Florida, Santiago`, o usa lat,lng.")
                        return
                    if resolved_area:
                        lat = resolved_area["lat"]
                        lon = resolved_area["lon"]
                        sector = compact_place_label(resolved_area["display_name"], 72)
                        if resolved_area["precision"] != "EXACT" and resolved_area.get("house_number_requested"):
                            st.warning(f"Ubicación aproximada: no fue posible localizar exactamente el número {resolved_area['house_number_requested']}.")
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
                            "search_location": resolved_area,
                        }
                    )
                    st.session_state.active_area_id = new_id
                    st.session_state.map_center = (float(lat), float(lon))
                    st.session_state.map_zoom = 13
                    st.session_state.fit_all_areas_once = len(st.session_state.areas) > 1
                    if layer_snapshot_has_active_layers(selected_layer_snapshot()):
                        st.session_state.pending_layer_apply = True
                    else:
                        st.session_state.pending_summary_apply = True
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
                    if area_needs_visible_layers(area_item["id"], selected_layer_snapshot()):
                        st.session_state.pending_layer_apply = True
                    elif area_needs_basic_summary(area_item["id"]):
                        st.session_state.pending_summary_apply = True
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
                    active_job = st.session_state.get("active_source_job") or {}
                    if active_job.get("area_id") == area_item["id"]:
                        st.session_state.active_source_job = None
                        st.session_state.active_request_id = None
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
            clear_map_layers()
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

        layer_snapshot_after = selected_layer_snapshot()
        if layer_snapshot_changed(layer_snapshot_before, layer_snapshot_after):
            st.session_state.last_applied_layers = layer_snapshot_after
            if area:
                st.session_state.pending_layer_apply = True

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
    visible_layers = selected_layer_snapshot()
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
            .leaflet-tile-pane {{
              filter: {basemap.css_filter if basemap.css_filter else 'none'};
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

    for area_item in renderable_area_geometries(st.session_state.areas):
        add_area_circle(map_obj, area_item, active=area_item["id"] == st.session_state.active_area_id)

    last_location = st.session_state.get("last_search_location")
    if last_location and not any(
        (area.get("search_location") or {}).get("query") == last_location.get("query")
        for area in st.session_state.areas
    ):
        add_location_marker(map_obj, last_location)

    if st.session_state.get("fit_all_areas_once"):
        bounds = combined_area_bounds(st.session_state.areas)
        if bounds:
            map_obj.fit_bounds(bounds, padding=(32, 32))
        st.session_state.fit_all_areas_once = False

    active = active_area()
    result_areas = (
        [area for area in st.session_state.areas if area.get("visible", True)]
        if st.session_state.get("mode") == "Comparar"
        else ([active] if active and active.get("visible", True) else [])
    )
    for area_item in result_areas:
        if not area_item.get("visible", True):
            continue
        bundle = st.session_state.map_bundle.get(area_item["id"], {})
        map_layers = visible_layers

        if bundle.get("visual_assets"):
            cluster = MarkerCluster(name=f"Equipamientos · {area_item['name']}")
            for item in bundle.get("visual_assets") or []:
                distance = haversine_m(area_item["lat"], area_item["lon"], item["lat"], item["lon"])
                folium.Marker(
                    [item["lat"], item["lon"]],
                    icon=marker_icon(item.get("type") or "terrain", 34),
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
                folium.Marker(
                    [item["lat"], item["lon"]],
                    icon=marker_icon("construction", 34),
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

    legend = legend_html(visible_layers, dark=dark_controls)
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

    if st.session_state.get("adjusting_search_location") and plain_click:
        click_key = f"{plain_click['lat']:.6f},{plain_click['lng']:.6f}"
        if click_key != st.session_state.last_area_click_key:
            st.session_state.pending_adjusted_location = plain_click
            st.session_state.map_center = (float(plain_click["lat"]), float(plain_click["lng"]))
            st.session_state.last_area_click_key = click_key
            st.rerun()
    elif st.session_state.adding_area and plain_click:
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
        active_job = st.session_state.get("active_source_job") or {}
        pending_for_area = (
            area["id"] == st.session_state.active_area_id
            and bool(
                st.session_state.pending_filter_apply
                or st.session_state.pending_layer_apply
                or st.session_state.pending_summary_apply
                or active_job.get("area_id") == area["id"]
            )
        )
        pending_text = "Consultando..." if pending_for_area else "No consultado"
        metro_value = pending_text
        if bundle:
            metro_value = format_metro_summary(bundle.get("metro_summary"))
        risk_value = risk_summary_value(bundle) if bundle else pending_text
        rows = [
            ("Área", f"{area['name']} · {compact_place_label(area['sector'], 34)}"),
            ("Superficie", f"{area_surface_km2(area):.1f} km2"),
            ("Uso de suelo", land_use_summary_value(bundle) if bundle else pending_text),
            ("Metro cercano", metro_value),
            ("Riesgos", risk_value),
            ("Equipamiento", count_summary_value(bundle, "assets", [f"built_{asset_type}" for asset_type in ASSET_TYPES]) if bundle else pending_text),
            ("Proyectos futuros", count_summary_value(bundle, "future_records", list(FUTURE_GIS_IDS.values()) + ["osm_construction"]) if bundle else pending_text),
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
            st.caption("Activa una capa para cargar fuentes, o usa Buscar terrenos para filtros prediales.")
        else:
            summary = progress_summary(bundle)
            if summary["total"]:
                label = "Análisis completado" if summary["complete"] else f"Analizando {area['name']}"
                warning_text = f"{summary['warnings']} con advertencias" if summary["warnings"] else "sin advertencias"
                st.markdown(
                    f"""
                    <div class="lf-progress-card">
                      <div class="lf-progress-top"><b>{label}</b><span>{summary['done']} / {summary['total']}</span></div>
                      <div class="lf-progress-track"><div class="lf-progress-fill" style="width:{summary['ratio'] * 100:.1f}%"></div></div>
                      <div class="lf-progress-meta">{summary['total']} fuentes · {summary['duration_ms'] / 1000:.1f} s · {warning_text}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            retryable = []
            retry_options = []
            for layer_id, result in (bundle.get("layer_states") or {}).items():
                label = display_label_for_source(layer_id)
                status = normalize_status(result.get("status"), result.get("count"))
                if status in FAILURE_STATES:
                    retryable.append(layer_id)
                retry_options.append((layer_id, label))
                pipeline = result.get("pipeline") or {}
                cache_bits = []
                if result.get("cache_digest"):
                    cache_bits.append(f"cache {str(result.get('cache_digest'))[:10]}")
                if isinstance(result.get("cache_age_seconds"), (int, float)):
                    cache_bits.append(f"{result['cache_age_seconds'] / 60:.0f} min")
                pipeline_text = ""
                if pipeline:
                    pipeline_text = (
                        f"<span class='lf-source-pipeline'>raw={pipeline.get('raw', 0)} · "
                        f"norm={pipeline.get('normalized', 0)} · match={pipeline.get('matching', result.get('count') or 0)} · "
                        f"render={pipeline.get('rendered', 0)}</span>"
                    )
                cache_text = f"<span class='lf-source-pipeline'>{' · '.join(cache_bits)}</span>" if cache_bits else ""
                expanded = status == LOADING or status in FAILURE_STATES
                with st.expander(f"{label} · {status_text(result)}", expanded=expanded):
                    meta_bits = [
                        f"Estado: {status_text(result)}",
                        f"Tiempo: {source_duration_text(result)}",
                    ]
                    if result.get("cache"):
                        meta_bits.append(f"Cache: {result.get('cache')}")
                    if result.get("area_id"):
                        meta_bits.append(f"Área: {result.get('area_id')}")
                    fill_width = source_state_ratio(result) * 100
                    css_class = source_state_class(result)
                    st.markdown(
                        f"""
                        <div class="lf-source-detail {css_class}">
                          <div class="lf-progress-track lf-source-track">
                            <div class="lf-progress-fill" style="width:{fill_width:.1f}%"></div>
                          </div>
                          <div class="lf-progress-meta">{html.escape(' · '.join(meta_bits))}</div>
                          {pipeline_text}
                          {cache_text}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                if result.get("error") and st.session_state.get("mode") == "Admin/API":
                    st.caption(clean_source_error(result.get("error")))
            if retryable and st.button("Reintentar fallidas", use_container_width=True):
                for layer_id in retryable:
                    (bundle.get("layer_states") or {}).pop(layer_id, None)
                    matching = [key for key in st.session_state.source_cache if f'"source": "{layer_id}"' in key]
                    for key in matching:
                        st.session_state.source_cache.pop(key, None)
                        delete_persistent_cache(key)
                    circuit_key = provider_key_for(layer_id, SOURCE_BY_ID)
                    st.session_state.source_circuits.pop(circuit_key, None)
                st.session_state.pending_filter_apply = True
                st.rerun()
            if retry_options:
                option_ids = [item[0] for item in retry_options]
                selected_retry = st.selectbox(
                    "Fuente a reintentar",
                    option_ids,
                    format_func=lambda item_id: dict(retry_options).get(item_id, item_id),
                )
                if st.button("Reintentar fuente seleccionada", use_container_width=True):
                    state = (bundle.get("layer_states") or {}).get(selected_retry) or {}
                    key = state.get("cache_key")
                    (bundle.get("layer_states") or {}).pop(selected_retry, None)
                    if key:
                        st.session_state.source_cache.pop(key, None)
                        delete_persistent_cache(key)
                    circuit_key = provider_key_for(selected_retry, SOURCE_BY_ID)
                    st.session_state.source_circuits.pop(circuit_key, None)
                    st.session_state.pending_filter_apply = True
                    st.rerun()


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
            resolved = resolve_search_structured(query)
        if resolved:
            st.session_state.map_center = (resolved["lat"], resolved["lon"])
            st.session_state.map_zoom = resolved["zoom"]
            st.session_state.last_search_location = resolved
            st.session_state.geocoder_candidates = resolved.get("candidates") or []
            message = f"Mapa centrado en {compact_place_label(resolved['display_name'])}."
            if hasattr(st, "toast"):
                st.toast(message)
            else:
                st.success(message)
            if resolved["precision"] != "EXACT" and resolved.get("house_number_requested"):
                st.warning(f"Ubicación aproximada: no fue posible localizar exactamente el número {resolved['house_number_requested']}.")
        else:
            st.session_state.geocoder_candidates = []
            st.warning("No encontré esa ubicación. Prueba agregar comuna/ciudad, por ejemplo `Av. Irarrázaval 2401, Ñuñoa`, o usa coordenadas `lat,lng`.")
    candidates = st.session_state.get("geocoder_candidates") or []
    if len(candidates) > 1:
        picked = st.selectbox(
            "Ubicaciones encontradas",
            list(range(len(candidates))),
            format_func=lambda index: compact_place_label(candidates[index].get("display_name") or candidates[index].get("query") or "", 74),
        )
        if st.button("Usar ubicación", use_container_width=True):
            selected = dict(candidates[picked])
            st.session_state.map_center = (selected["lat"], selected["lon"])
            st.session_state.map_zoom = selected["zoom"]
            st.session_state.last_search_location = selected
            st.rerun()
    last_location = st.session_state.get("last_search_location")
    if last_location and last_location.get("precision") != "EXACT":
        c1, c2 = st.columns([0.48, 0.52], gap="small")
        if c1.button("Ajustar ubicación", use_container_width=True):
            st.session_state.adjusting_search_location = True
            st.session_state.pending_adjusted_location = None
            st.toast("Haz clic en el mapa y luego confirma la ubicación.")
        pending_adjusted = st.session_state.get("pending_adjusted_location")
        if pending_adjusted and c2.button("Usar esta ubicación", use_container_width=True):
            adjusted = dict(last_location)
            adjusted.update(
                {
                    "lat": float(pending_adjusted["lat"]),
                    "lon": float(pending_adjusted["lng"]),
                    "precision": "APPROXIMATE",
                    "confidence": "manual",
                    "source": "manual_adjustment",
                }
            )
            st.session_state.last_search_location = adjusted
            st.session_state.map_center = (adjusted["lat"], adjusted["lon"])
            st.session_state.adjusting_search_location = False
            st.session_state.pending_adjusted_location = None
            st.rerun()
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
    render_map_progress_card(current_area)
    render_map()

with right:
    render_right_panel(active_area())

if (
    current_area
    and not st.session_state.pending_filter_apply
    and not st.session_state.pending_layer_apply
    and not st.session_state.pending_summary_apply
    and not st.session_state.get("active_source_job")
    and area_needs_basic_summary(current_area["id"])
):
    st.session_state.pending_summary_apply = True

if st.session_state.pending_filter_apply or st.session_state.pending_layer_apply or st.session_state.pending_summary_apply:
    current = active_area()
    if current:
        st.session_state.active_source_job = None
        summary_run = bool(st.session_state.pending_summary_apply and not st.session_state.pending_filter_apply and not st.session_state.pending_layer_apply)
        start_area_source_job(current, summary=summary_run)
        st.rerun()

if st.session_state.get("active_source_job"):
    if advance_active_source_job():
        st.rerun()
    if st.session_state.get("active_source_job"):
        st.rerun()

st.caption(
    "Landfinder Chile MVP · Prefactibilidad territorial. Las fuentes externas pertenecen a sus proveedores y pueden requerir validación legal, credenciales o estabilidad adicional."
)
