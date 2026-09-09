from __future__ import annotations

import json
import math
from datetime import datetime

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Fullscreen
from streamlit_folium import st_folium

from landfinder.registry import load_sources
from landfinder.probes import probe_source
from landfinder.storage import save_result, load_history
from landfinder.map_engine import load_map_source
from landfinder.urban_value import (
    ASSET_TYPES,
    METRO_COLORS,
    CURRENT_LINE_ORDER,
    FUTURE_LINE_ORDER,
    CURRENT_METRO_META,
    FUTURE_METRO_META,
    query_built_assets,
    query_current_metro_detailed,
    query_future_metro_detailed,
    query_osm_construction,
    haversine_m,
)


SOURCES = load_sources()
SOURCE_BY_ID = {s["id"]: s for s in SOURCES}

AREA_COLORS = ["#1473E6", "#16A36A", "#E74C5B", "#8E44AD", "#F39C12"]

st.set_page_config(
    page_title="Landfinder Chile · MVP v0.8",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# Visual system
# ============================================================================
st.markdown(
    """
<style>
:root {
  --lf-navy:#0B2744;
  --lf-navy-2:#102F50;
  --lf-cyan:#16C5D8;
  --lf-blue:#1473E6;
  --lf-green:#16A36A;
  --lf-orange:#FF8A32;
  --lf-purple:#8E44AD;
  --lf-red:#E74C5B;
  --lf-bg:#F4F8FC;
  --lf-card:#FFFFFF;
  --lf-text:#10243A;
  --lf-muted:#65758B;
}

.stApp {
  background: var(--lf-bg);
  color: var(--lf-text);
}

[data-testid="stHeader"] {
  background: rgba(244,248,252,.92);
}

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0B2744 0%, #102F50 100%);
  border-right: 1px solid rgba(255,255,255,.08);
}

section[data-testid="stSidebar"] * {
  color: #F7FBFF;
}

section[data-testid="stSidebar"] input {
  color: #10243A !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 18px;
  border-color: #DCE7F2 !important;
  background: #FFFFFF;
  box-shadow: 0 8px 24px rgba(22,54,88,.06);
}

.stButton > button {
  border-radius: 12px;
  border: 0;
  font-weight: 700;
}

.stButton > button[kind="primary"] {
  background: linear-gradient(90deg, #1473E6, #16C5D8);
  color: white;
}

div[data-testid="stMetric"] {
  background: #FFFFFF;
  border: 1px solid #E3EDF6;
  padding: 12px 14px;
  border-radius: 15px;
}

div[data-testid="stTabs"] button {
  font-weight: 700;
}

.lf-topbar {
  background: linear-gradient(100deg,#0B2744,#123B62);
  color:white;
  border-radius:18px;
  padding:16px 20px;
  display:flex;
  justify-content:space-between;
  align-items:center;
  box-shadow:0 10px 28px rgba(11,39,68,.18);
  margin-bottom:12px;
}
.lf-brand {
  font-size:25px;
  font-weight:850;
  letter-spacing:-.4px;
}
.lf-tagline {
  color:#BFE8F3;
  font-size:12px;
}
.lf-user {
  background:rgba(255,255,255,.10);
  border:1px solid rgba(255,255,255,.15);
  padding:8px 12px;
  border-radius:14px;
  font-size:13px;
}

.lf-chip {
  display:inline-block;
  color:#fff;
  font-weight:750;
  border-radius:999px;
  padding:7px 12px;
  margin:2px 5px 6px 0;
  box-shadow:0 4px 12px rgba(0,0,0,.10);
}
.lf-card-title {
  font-weight:850;
  color:#0B2744;
  font-size:16px;
}
.lf-caption {
  color:#65758B;
  font-size:12px;
}
.lf-score {
  font-size:31px;
  line-height:1;
  font-weight:900;
  color:#0B2744;
}
.lf-good {
  color:#16A36A;
  font-weight:800;
}
.lf-warning {
  color:#E67E22;
  font-weight:800;
}

#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================================
# State helpers
# ============================================================================
def init_state():
    if "profile" not in st.session_state:
        st.session_state.profile = {
            "name": "Usuario Demo",
            "email": "demo@landfinder.cl",
            "company": "Landfinder Chile",
            "role": "Planificador",
            "plan": "Free",
        }

    if "workspace" not in st.session_state:
        st.session_state.workspace = {
            "name": "Workspace personal",
            "project": "Exploración territorial",
        }

    if "areas" not in st.session_state:
        st.session_state.areas = [
            {
                "id": "A",
                "name": "Área A",
                "sector": "Santiago Centro",
                "lat": -33.448900,
                "lon": -70.669300,
                "radius_m": 2000,
                "color": AREA_COLORS[0],
            }
        ]

    if "active_area_id" not in st.session_state:
        st.session_state.active_area_id = "A"

    if "map_bundle" not in st.session_state:
        st.session_state.map_bundle = {}

    if "alerts" not in st.session_state:
        st.session_state.alerts = []

    if "last_map_click" not in st.session_state:
        st.session_state.last_map_click = None

    if "api_results" not in st.session_state:
        st.session_state.api_results = {}


init_state()


def get_area(area_id: str):
    return next((a for a in st.session_state.areas if a["id"] == area_id), st.session_state.areas[0])


def area_index(area_id: str):
    for i, a in enumerate(st.session_state.areas):
        if a["id"] == area_id:
            return i
    return 0


def next_area_id():
    alphabet = "ABCDE"
    used = {a["id"] for a in st.session_state.areas}
    for letter in alphabet:
        if letter not in used:
            return letter
    return None


def moneyless_score(value):
    return max(0.0, min(10.0, round(value, 1)))


def score_area(bundle):
    if not bundle:
        return {
            "urban": 0.0,
            "connectivity": 0.0,
            "future": 0.0,
            "territorial": 0.0,
            "overall": 0.0,
        }

    assets = bundle.get("assets", [])
    current = bundle.get("metro_current", {})
    future_metro = bundle.get("metro_future", {})
    future_rows = bundle.get("future_records", [])
    technical = bundle.get("technical", {})

    asset_points = len(assets)
    metro_pass = sum(1 for x in current.values() if x.get("passes_area") is True)
    stations = sum(len(x.get("stations_in_area") or []) for x in current.values())
    future_pass = sum(1 for x in future_metro.values() if x.get("passes_area") is True)
    future_projects = len(future_rows)

    technical_alerts = 0
    technical_ok = 0
    for result in technical.values():
        if result.get("status") in {"OK", "OK_SIN_COINCIDENCIAS", "VISUAL_ONLY"}:
            technical_ok += 1
        if result.get("count") not in (None, 0):
            technical_alerts += 1

    urban = moneyless_score(3.8 + min(asset_points, 30) * 0.18)
    connectivity = moneyless_score(3.5 + metro_pass * 1.5 + min(stations, 8) * 0.35)
    future = moneyless_score(3.5 + future_pass * 1.1 + min(future_projects, 15) * 0.22)
    territorial = moneyless_score(8.5 - technical_alerts * 0.6 + min(technical_ok, 6) * 0.1)
    overall = moneyless_score(
        urban * 0.27 + connectivity * 0.30 + future * 0.22 + territorial * 0.21
    )

    return {
        "urban": urban,
        "connectivity": connectivity,
        "future": future,
        "territorial": territorial,
        "overall": overall,
    }


def add_area_circle(m, area, active=False):
    color = area["color"]
    folium.Circle(
        [area["lat"], area["lon"]],
        radius=area["radius_m"],
        color=color,
        weight=5 if active else 3,
        fill=True,
        fill_color=color,
        fill_opacity=0.14 if active else 0.08,
        tooltip=f"{area['name']} · {area['sector']}",
    ).add_to(m)

    folium.Marker(
        [area["lat"], area["lon"]],
        tooltip=f"{area['name']} · {area['sector']}",
        icon=folium.DivIcon(
            html=f"""
            <div style="
                background:{color};color:white;border:3px solid white;
                box-shadow:0 4px 12px rgba(0,0,0,.25);
                border-radius:16px;padding:5px 10px;
                font-weight:800;white-space:nowrap;
                font-size:13px;
            ">{area['name']}</div>
            """
        ),
    ).add_to(m)


def add_metro_line(m, line, future=False):
    color = line.get("color") or "#666666"
    ref = line.get("ref") or "Metro"

    group = folium.FeatureGroup(
        name=f"{'Metro futuro' if future else 'Metro actual'} · {ref}",
        show=True,
    )

    for seg in line.get("segments") or []:
        folium.PolyLine(
            seg,
            color=color,
            weight=5,
            opacity=0.90,
            dash_array="11 8" if future else None,
            tooltip=f"{ref} · {'futuro / en desarrollo' if future else 'operativo'}",
        ).add_to(group)

    group.add_to(m)


def build_area_report(area, bundle):
    score = score_area(bundle)
    assets = bundle.get("assets", [])
    future_rows = bundle.get("future_records", [])

    return {
        "area": area,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "indicator": score,
        "built_assets": [
            {
                "category": x.get("category"),
                "name": x.get("name"),
                "lat": x.get("lat"),
                "lon": x.get("lon"),
            }
            for x in assets
        ],
        "future_elements": future_rows,
        "technical_summary": {
            source_id: {
                "status": result.get("status"),
                "count": result.get("count"),
                "error": result.get("error"),
            }
            for source_id, result in bundle.get("technical", {}).items()
        },
    }


# ============================================================================
# Sidebar: account / workspace
# ============================================================================
profile = st.session_state.profile
workspace = st.session_state.workspace

with st.sidebar:
    st.markdown(
        f"""
        <div style="padding:10px 4px 14px 4px;">
          <div style="font-size:22px;font-weight:900;color:white;">Landfinder Chile</div>
          <div style="font-size:11px;color:#BFE8F3;">Territorio para mejores decisiones</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 👤 Cuenta")
    st.write(f"**{profile['name']}**")
    st.caption(f"{profile['role']} · {profile['plan']}")

    st.markdown("### 🗂️ Workspace")
    workspace_name = st.text_input("Workspace", workspace["name"], label_visibility="collapsed")
    project_name = st.text_input("Proyecto", workspace["project"], label_visibility="collapsed")
    st.session_state.workspace["name"] = workspace_name
    st.session_state.workspace["project"] = project_name

    st.markdown("### 📍 Áreas")
    active_options = {
        f"{a['id']} · {a['name']} · {a['sector']}": a["id"]
        for a in st.session_state.areas
    }
    labels = list(active_options.keys())
    current_label = next(
        (label for label, aid in active_options.items() if aid == st.session_state.active_area_id),
        labels[0],
    )
    selected_label = st.selectbox(
        "Área activa",
        labels,
        index=labels.index(current_label),
    )
    st.session_state.active_area_id = active_options[selected_label]

    with st.expander("➕ Agregar área"):
        new_id = next_area_id()
        if new_id is None:
            st.info("El prototipo admite hasta 5 áreas simultáneas.")
        else:
            new_name = st.text_input("Nombre", f"Área {new_id}", key="new_area_name")
            new_sector = st.text_input("Sector / referencia", "Nueva zona", key="new_area_sector")
            new_lat = st.number_input(
                "Latitud",
                value=float(get_area(st.session_state.active_area_id)["lat"]),
                format="%.6f",
                key="new_area_lat",
            )
            new_lon = st.number_input(
                "Longitud",
                value=float(get_area(st.session_state.active_area_id)["lon"]),
                format="%.6f",
                key="new_area_lon",
            )
            new_radius = st.selectbox(
                "Radio",
                [500, 1000, 2000, 3000, 5000, 10000],
                index=2,
                key="new_area_radius",
            )

            if st.button("Agregar área", use_container_width=True):
                st.session_state.areas.append(
                    {
                        "id": new_id,
                        "name": new_name,
                        "sector": new_sector,
                        "lat": float(new_lat),
                        "lon": float(new_lon),
                        "radius_m": int(new_radius),
                        "color": AREA_COLORS[len(st.session_state.areas) % len(AREA_COLORS)],
                    }
                )
                st.session_state.active_area_id = new_id
                st.rerun()

    active_area = get_area(st.session_state.active_area_id)
    st.markdown(
        f"""
        <div style="margin-top:8px;padding:10px 12px;border-radius:13px;
                    background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);">
          <div style="font-size:11px;color:#A9DDE9;">ÁREA ACTIVA</div>
          <div style="font-weight:850;">{active_area['name']}</div>
          <div style="font-size:12px;color:#D7EEF4;">{active_area['sector']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(st.session_state.areas) > 1:
        with st.expander("Administrar áreas"):
            remove_id = st.selectbox(
                "Eliminar",
                [a["id"] for a in st.session_state.areas if a["id"] != st.session_state.active_area_id],
                format_func=lambda x: get_area(x)["name"],
            )
            if st.button("Eliminar área seleccionada", use_container_width=True):
                st.session_state.areas = [a for a in st.session_state.areas if a["id"] != remove_id]
                st.session_state.map_bundle.pop(remove_id, None)
                st.rerun()


# ============================================================================
# Header
# ============================================================================
st.markdown(
    f"""
    <div class="lf-topbar">
      <div>
        <div class="lf-brand">◢◤ Landfinder Chile</div>
        <div class="lf-tagline">Encuentra, analiza y compara terrenos con inteligencia territorial.</div>
      </div>
      <div class="lf-user">🔔 &nbsp; {profile['name']} · {profile['plan']}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

search_col, action_col = st.columns([0.78, 0.22], gap="small")
with search_col:
    search = st.text_input(
        "Buscar",
        placeholder="Buscar coordenadas, comuna, sector o dirección...",
        label_visibility="collapsed",
    )
with action_col:
    if st.button("＋ Agregar área", use_container_width=True):
        st.info("Usa el panel izquierdo → Agregar área, o haz clic sobre el mapa y crea una zona desde ese punto.")

if search and "," in search:
    try:
        p1, p2 = search.split(",", 1)
        qlat, qlon = float(p1.strip()), float(p2.strip())
        if st.button("Usar coordenadas buscadas"):
            active_area = get_area(st.session_state.active_area_id)
            active_area["lat"] = qlat
            active_area["lon"] = qlon
            st.rerun()
    except Exception:
        pass


# ============================================================================
# Product navigation
# ============================================================================
tabs = st.tabs([
    "🗺️ Explorar",
    "⚖️ Comparar",
    "🔔 Alertas",
    "📄 Reportes",
    "📁 Proyectos",
    "👤 Perfil",
    "🛠️ Admin/API",
])


# ============================================================================
# EXPLORE
# ============================================================================
with tabs[0]:
    area = get_area(st.session_state.active_area_id)

    # Area chips
    chips = ""
    for a in st.session_state.areas:
        chips += (
            f'<span class="lf-chip" style="background:{a["color"]};">'
            f'{a["id"]} · {a["name"]}</span>'
        )
    st.markdown(chips, unsafe_allow_html=True)

    left, center, right = st.columns([0.22, 0.58, 0.20], gap="small")

    with left:
        with st.container(border=True):
            st.markdown('<div class="lf-card-title">🧱 Capas</div>', unsafe_allow_html=True)
            st.caption("Activa varias categorías a la vez.")

            st.markdown("**🏙️ Construido hoy**")
            built_labels = {k: ASSET_TYPES[k]["label"] for k in ASSET_TYPES}
            selected_built = st.multiselect(
                "Construido",
                list(ASSET_TYPES.keys()),
                default=["mall", "supermarket", "hospital", "education", "park"],
                format_func=lambda x: built_labels[x],
                label_visibility="collapsed",
            )

            st.markdown("**🚇 Metro**")
            show_metro_current = st.checkbox("Metro actual", value=True)
            show_metro_future = st.checkbox("Metro futuro", value=True)

            st.markdown("**🚧 Futuro**")
            show_osm_construction = st.checkbox("Construcciones OSM", value=False)
            show_seia = st.checkbox("Proyectos SEIA", value=True)
            show_mop = st.checkbox("Obras / contratos MOP", value=False)

            st.markdown("**🌎 Territorio**")
            territory_sources = [s for s in SOURCES if s.get("map_enabled")]
            territory_labels = {
                s["id"]: s.get("map_label", s["name"])
                for s in territory_sources
            }
            default_territory = [
                "minvu_limites_urbanos",
                "minvu_area_riesgo",
                "mma_humedales",
                "mma_areas_protegidas",
            ]
            selected_territory = st.multiselect(
                "Territorio",
                [s["id"] for s in territory_sources],
                default=[x for x in default_territory if x in territory_labels],
                format_func=lambda x: territory_labels.get(x, x),
                label_visibility="collapsed",
            )

            st.divider()
            query_all_areas = st.checkbox(
                "Consultar todas las áreas",
                value=False,
                help="Puede hacer más llamadas a APIs. Si está apagado, consulta solo el área activa.",
            )

            refresh = st.button(
                "↻ Actualizar mapa",
                type="primary",
                use_container_width=True,
            )

    if refresh:
        target_areas = st.session_state.areas if query_all_areas else [area]
        progress = st.progress(0)
        status = st.empty()

        total_steps = max(len(target_areas), 1)
        for idx, target in enumerate(target_areas, 1):
            status.write(f"Analizando **{target['name']}**...")
            bundle = {
                "assets": [],
                "metro_current": {},
                "metro_future": {},
                "construction": [],
                "future_records": [],
                "future_gis": {},
                "technical": {},
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

            if selected_built:
                try:
                    bundle["assets"] = query_built_assets(
                        target["lat"],
                        target["lon"],
                        target["radius_m"],
                        list(selected_built),
                    )
                except Exception as exc:
                    bundle["assets_error"] = str(exc)

            if show_metro_current:
                try:
                    bundle["metro_current"] = query_current_metro_detailed(
                        target["lat"],
                        target["lon"],
                        target["radius_m"],
                    )
                except Exception as exc:
                    bundle["metro_current_error"] = str(exc)

            if show_metro_future:
                try:
                    bundle["metro_future"] = query_future_metro_detailed(
                        target["lat"],
                        target["lon"],
                        target["radius_m"],
                    )
                except Exception as exc:
                    bundle["metro_future_error"] = str(exc)

            if show_osm_construction:
                try:
                    bundle["construction"] = query_osm_construction(
                        target["lat"],
                        target["lon"],
                        target["radius_m"],
                    )
                    for item in bundle["construction"]:
                        bundle["future_records"].append(
                            {
                                "Fuente": "OpenStreetMap",
                                "Elemento": item.get("name"),
                                "Estado": "CONSTRUCCIÓN MAPEADA",
                                "Distancia_m": round(
                                    haversine_m(
                                        target["lat"],
                                        target["lon"],
                                        item["lat"],
                                        item["lon"],
                                    ),
                                    1,
                                ),
                            }
                        )
                except Exception as exc:
                    bundle["construction_error"] = str(exc)

            future_ids = []
            if show_seia:
                future_ids.append("sea_proyectos")
            if show_mop:
                future_ids.append("mop_contratos_obras")

            for source_id in future_ids:
                source = SOURCE_BY_ID.get(source_id)
                if not source:
                    continue
                try:
                    result = load_map_source(
                        source,
                        target["lat"],
                        target["lon"],
                        target["radius_m"],
                        15,
                        500,
                    )
                    bundle["future_gis"][source_id] = result
                    for record in result.get("records") or []:
                        bundle["future_records"].append(
                            {
                                "Fuente": record.get("Fuente"),
                                "Elemento": record.get("Elemento"),
                                "Estado": "REGISTRO DE PROYECTO / FUENTE",
                                "Distancia_m": record.get("Distancia_m"),
                            }
                        )
                except Exception as exc:
                    bundle["future_gis"][source_id] = {
                        "status": "SOURCE_ERROR",
                        "layers": [],
                        "records": [],
                        "count": None,
                        "error": str(exc),
                    }

            for source_id in selected_territory:
                source = SOURCE_BY_ID.get(source_id)
                if not source:
                    continue
                try:
                    bundle["technical"][source_id] = load_map_source(
                        source,
                        target["lat"],
                        target["lon"],
                        target["radius_m"],
                        15,
                        500,
                    )
                except Exception as exc:
                    bundle["technical"][source_id] = {
                        "status": "SOURCE_ERROR",
                        "layers": [],
                        "records": [],
                        "count": None,
                        "error": str(exc),
                    }

            st.session_state.map_bundle[target["id"]] = bundle
            progress.progress(idx / total_steps)

        status.success("Mapa actualizado.")

    bundle = st.session_state.map_bundle.get(area["id"], {})

    with center:
        with st.container(border=True):
            base_map = folium.Map(
                [area["lat"], area["lon"]],
                zoom_start=12,
                tiles="OpenStreetMap",
                control_scale=True,
            )
            Fullscreen(position="topright").add_to(base_map)

            # Areas
            for a in st.session_state.areas:
                add_area_circle(
                    base_map,
                    a,
                    active=(a["id"] == st.session_state.active_area_id),
                )

            # Built
            built_group = folium.FeatureGroup(name="Construido hoy", show=True)
            for item in bundle.get("assets", []):
                d = haversine_m(area["lat"], area["lon"], item["lat"], item["lon"])
                folium.CircleMarker(
                    [item["lat"], item["lon"]],
                    radius=6,
                    color=item.get("color", "#1473E6"),
                    fill=True,
                    fill_opacity=0.95,
                    tooltip=item.get("name"),
                    popup=(
                        f"<b>{item.get('name')}</b><br>"
                        f"{item.get('category')}<br>"
                        f"Distancia: {d:,.0f} m".replace(",", ".")
                    ),
                ).add_to(built_group)
            built_group.add_to(base_map)

            # Current metro
            for ref in CURRENT_LINE_ORDER:
                line = bundle.get("metro_current", {}).get(ref)
                if line and line.get("segments"):
                    add_metro_line(base_map, line, future=False)

            # Future metro
            for ref in FUTURE_LINE_ORDER:
                line = bundle.get("metro_future", {}).get(ref)
                if line and line.get("segments"):
                    add_metro_line(base_map, line, future=True)

            # OSM construction
            construction_group = folium.FeatureGroup(name="Construcciones OSM", show=True)
            for item in bundle.get("construction", []):
                folium.CircleMarker(
                    [item["lat"], item["lon"]],
                    radius=6,
                    color="#FF8A32",
                    fill=True,
                    fill_opacity=0.90,
                    tooltip=item.get("name"),
                ).add_to(construction_group)
            construction_group.add_to(base_map)

            # Future GIS
            for source_id, result in bundle.get("future_gis", {}).items():
                source = SOURCE_BY_ID.get(source_id, {})
                label = source.get("map_label", source.get("name", source_id))
                group = folium.FeatureGroup(name=label, show=True)
                for layer in result.get("layers") or []:
                    gj = layer.get("geojson")
                    if gj and gj.get("features"):
                        folium.GeoJson(
                            gj,
                            name=label,
                            tooltip=folium.GeoJsonTooltip(
                                fields=["__label", "__distance_m"],
                                aliases=["Elemento", "Distancia (m)"],
                                sticky=False,
                            ),
                        ).add_to(group)
                group.add_to(base_map)

            # Technical GIS
            for source_id, result in bundle.get("technical", {}).items():
                source = SOURCE_BY_ID.get(source_id, {})
                label = source.get("map_label", source.get("name", source_id))

                if result.get("type") == "geojson_layers":
                    group = folium.FeatureGroup(name=label, show=True)
                    for layer in result.get("layers") or []:
                        gj = layer.get("geojson")
                        if gj and gj.get("features"):
                            folium.GeoJson(
                                gj,
                                name=label,
                                style_function=lambda x: {
                                    "weight": 2,
                                    "fillOpacity": 0.10,
                                },
                            ).add_to(group)
                    group.add_to(base_map)

                elif result.get("type") == "wms":
                    for layer_name in result.get("layers") or []:
                        folium.raster_layers.WmsTileLayer(
                            url=source["url"],
                            layers=layer_name,
                            name=label,
                            fmt="image/png",
                            transparent=True,
                            overlay=True,
                        ).add_to(base_map)

            folium.LayerControl(collapsed=True).add_to(base_map)

            map_state = st_folium(
                base_map,
                width=None,
                height=720,
                key=f"main_map_{area['id']}_{len(st.session_state.areas)}",
                returned_objects=["last_clicked"],
            )

            if map_state and map_state.get("last_clicked"):
                st.session_state.last_map_click = map_state["last_clicked"]

            if st.session_state.last_map_click:
                click = st.session_state.last_map_click
                c1, c2 = st.columns([0.68, 0.32])
                with c1:
                    st.caption(
                        f"Último clic: {click['lat']:.6f}, {click['lng']:.6f}"
                    )
                with c2:
                    if st.button("Crear área desde clic", use_container_width=True):
                        new_id = next_area_id()
                        if new_id:
                            st.session_state.areas.append(
                                {
                                    "id": new_id,
                                    "name": f"Área {new_id}",
                                    "sector": "Punto seleccionado",
                                    "lat": float(click["lat"]),
                                    "lon": float(click["lng"]),
                                    "radius_m": 2000,
                                    "color": AREA_COLORS[len(st.session_state.areas) % len(AREA_COLORS)],
                                }
                            )
                            st.session_state.active_area_id = new_id
                            st.rerun()

    with right:
        with st.container(border=True):
            st.markdown('<div class="lf-card-title">📍 Resumen del área</div>', unsafe_allow_html=True)
            st.write(f"**{area['name']}**")
            st.caption(area["sector"])
            st.caption(f"Radio: {area['radius_m'] / 1000:g} km")

        scores = score_area(bundle)

        with st.container(border=True):
            st.markdown('<div class="lf-card-title">📊 Indicador preliminar</div>', unsafe_allow_html=True)
            if bundle:
                st.markdown(f'<div class="lf-score">{scores["overall"]} / 10</div>', unsafe_allow_html=True)
                st.progress(scores["overall"] / 10)
                st.caption("Indicador explicable; no reemplaza evaluación técnica o legal.")
            else:
                st.info("Actualiza el mapa para calcular.")

        with st.container(border=True):
            st.markdown('<div class="lf-card-title">🚇 Conectividad</div>', unsafe_allow_html=True)
            st.metric("Metro", f'{scores["connectivity"]}/10' if bundle else "—")
            current_lines = [
                ref
                for ref, line in bundle.get("metro_current", {}).items()
                if line.get("passes_area") is True
            ]
            future_lines = [
                ref
                for ref, line in bundle.get("metro_future", {}).items()
                if line.get("passes_area") is True
            ]
            st.caption(
                f"Actual: {', '.join(current_lines) if current_lines else 'sin líneas detectadas'}"
            )
            st.caption(
                f"Futuro: {', '.join(future_lines) if future_lines else 'sin líneas detectadas'}"
            )

        with st.container(border=True):
            st.markdown('<div class="lf-card-title">🏗️ Desarrollo futuro</div>', unsafe_allow_html=True)
            st.metric(
                "Elementos cercanos",
                len(bundle.get("future_records", [])) if bundle else "—",
            )
            st.caption("SEIA, OSM construction y MOP según capas activas.")

        with st.container(border=True):
            st.markdown('<div class="lf-card-title">🏙️ Construido hoy</div>', unsafe_allow_html=True)
            st.metric(
                "Equipamientos",
                len(bundle.get("assets", [])) if bundle else "—",
            )

        if st.button("⚖️ Comparar áreas", use_container_width=True):
            st.info("Abre la pestaña Comparar.")


# ============================================================================
# COMPARE
# ============================================================================
with tabs[1]:
    st.subheader("Comparar áreas")
    st.caption(
        "Selecciona varias zonas. El prototipo usa los datos que ya fueron cargados en Explorar."
    )

    compare_ids = st.multiselect(
        "Áreas",
        [a["id"] for a in st.session_state.areas],
        default=[a["id"] for a in st.session_state.areas],
        format_func=lambda aid: f"{get_area(aid)['name']} · {get_area(aid)['sector']}",
    )

    compare_map = folium.Map(
        [
            sum(get_area(aid)["lat"] for aid in compare_ids) / max(len(compare_ids), 1)
            if compare_ids else -33.4489,
            sum(get_area(aid)["lon"] for aid in compare_ids) / max(len(compare_ids), 1)
            if compare_ids else -70.6693,
        ],
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    rows = []
    for aid in compare_ids:
        a = get_area(aid)
        add_area_circle(compare_map, a, active=(aid == st.session_state.active_area_id))
        b = st.session_state.map_bundle.get(aid, {})
        sc = score_area(b)

        rows.append(
            {
                "Área": a["name"],
                "Sector": a["sector"],
                "Radio_m": a["radius_m"],
                "Indicador": sc["overall"] if b else None,
                "Valor urbano": sc["urban"] if b else None,
                "Conectividad": sc["connectivity"] if b else None,
                "Futuro": sc["future"] if b else None,
                "Territorio": sc["territorial"] if b else None,
                "Equipamientos": len(b.get("assets", [])) if b else None,
                "Proyectos futuros": len(b.get("future_records", [])) if b else None,
            }
        )

    st_folium(compare_map, width=None, height=570, key="compare_map")
    df_compare = pd.DataFrame(rows)
    st.dataframe(df_compare, use_container_width=True, hide_index=True)

    if not df_compare.empty:
        st.download_button(
            "Descargar comparación CSV",
            df_compare.to_csv(index=False).encode("utf-8-sig"),
            "landfinder_comparacion_areas.csv",
            "text/csv",
        )


# ============================================================================
# ALERTS
# ============================================================================
with tabs[2]:
    st.subheader("Alertas territoriales")
    st.caption(
        "Prototipo de producto recurrente. Las alertas quedan guardadas en la sesión; "
        "la versión SaaS usará jobs programados."
    )

    alert_area = st.selectbox(
        "Área a seguir",
        [a["id"] for a in st.session_state.areas],
        format_func=lambda aid: f"{get_area(aid)['name']} · {get_area(aid)['sector']}",
        key="alert_area",
    )

    with st.form("alert_form"):
        event_types = st.multiselect(
            "Avísame si aparece o cambia",
            [
                "Nuevo proyecto SEIA",
                "Nueva obra MOP",
                "Cambio en IPT / planificación",
                "Cambio en riesgo territorial",
                "Nuevo proyecto Metro",
                "Nueva construcción relevante",
            ],
            default=["Nuevo proyecto SEIA", "Nueva obra MOP", "Nuevo proyecto Metro"],
        )
        frequency = st.selectbox("Frecuencia futura", ["Diaria", "Semanal"])
        submitted = st.form_submit_button("Crear alerta")

        if submitted:
            st.session_state.alerts.append(
                {
                    "area_id": alert_area,
                    "events": event_types,
                    "frequency": frequency,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            st.success("Alerta de prototipo creada.")

    if st.session_state.alerts:
        alert_rows = []
        for i, alert in enumerate(st.session_state.alerts, 1):
            a = get_area(alert["area_id"])
            alert_rows.append(
                {
                    "#": i,
                    "Área": a["name"],
                    "Eventos": ", ".join(alert["events"]),
                    "Frecuencia": alert["frequency"],
                    "Creada": alert["created_at"],
                }
            )
        st.dataframe(pd.DataFrame(alert_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no tienes alertas.")


# ============================================================================
# REPORTS
# ============================================================================
with tabs[3]:
    st.subheader("Reportes")
    report_area_id = st.selectbox(
        "Área",
        [a["id"] for a in st.session_state.areas],
        format_func=lambda aid: f"{get_area(aid)['name']} · {get_area(aid)['sector']}",
        key="report_area",
    )
    report_area = get_area(report_area_id)
    report_bundle = st.session_state.map_bundle.get(report_area_id, {})

    if not report_bundle:
        st.warning("Primero carga esta área desde Explorar.")
    else:
        report = build_area_report(report_area, report_bundle)
        score = report["indicator"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Indicador", f'{score["overall"]}/10')
        c2.metric("Conectividad", f'{score["connectivity"]}/10')
        c3.metric("Futuro", f'{score["future"]}/10')
        c4.metric("Territorio", f'{score["territorial"]}/10')

        report_json = json.dumps(report, ensure_ascii=False, indent=2)

        html = f"""
        <html>
        <head><meta charset="utf-8"><title>Landfinder - {report_area['name']}</title></head>
        <body style="font-family:Arial,sans-serif;max-width:900px;margin:40px auto;color:#10243A;">
        <h1>Landfinder Chile</h1>
        <h2>{report_area['name']} · {report_area['sector']}</h2>
        <p>Generado: {report['generated_at']}</p>
        <hr>
        <h3>Indicadores preliminares</h3>
        <ul>
          <li>General: {score['overall']}/10</li>
          <li>Valor urbano: {score['urban']}/10</li>
          <li>Conectividad: {score['connectivity']}/10</li>
          <li>Desarrollo futuro: {score['future']}/10</li>
          <li>Territorio: {score['territorial']}/10</li>
        </ul>
        <h3>Resumen</h3>
        <p>Equipamientos cargados: {len(report_bundle.get('assets', []))}</p>
        <p>Elementos futuros cargados: {len(report_bundle.get('future_records', []))}</p>
        <p><b>Nota:</b> este reporte es de prefactibilidad y no reemplaza certificados,
        permisos, estudios de título, CIP, factibilidades ni evaluación profesional.</p>
        </body></html>
        """

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Descargar JSON de evidencia",
                report_json,
                f"landfinder_{report_area_id}_evidencia.json",
                "application/json",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "Descargar informe HTML",
                html,
                f"landfinder_{report_area_id}_informe.html",
                "text/html",
                use_container_width=True,
            )


# ============================================================================
# PROJECTS / WORKSPACES
# ============================================================================
with tabs[4]:
    st.subheader("Proyectos / Workspace")
    st.caption(
        "Estructura pensada para consultoras, inmobiliarias, constructoras y equipos."
    )

    st.markdown(f"### {st.session_state.workspace['name']}")
    st.write(f"Proyecto activo: **{st.session_state.workspace['project']}**")

    project_rows = []
    for a in st.session_state.areas:
        b = st.session_state.map_bundle.get(a["id"], {})
        s = score_area(b)
        project_rows.append(
            {
                "Área": a["name"],
                "Sector": a["sector"],
                "Estado": "Analizada" if b else "Pendiente",
                "Indicador": s["overall"] if b else None,
                "Última actualización": b.get("updated_at") if b else None,
            }
        )
    st.dataframe(pd.DataFrame(project_rows), use_container_width=True, hide_index=True)

    st.info(
        "En la versión Empresa este módulo tendrá miembros, permisos, comentarios, "
        "asignación de responsables y carpetas de proyecto."
    )


# ============================================================================
# PROFILE
# ============================================================================
with tabs[5]:
    st.subheader("Perfil")
    with st.form("profile_form"):
        name = st.text_input("Nombre", profile["name"])
        email = st.text_input("Correo", profile["email"])
        company = st.text_input("Empresa", profile["company"])
        role = st.selectbox(
            "Uso principal",
            [
                "Personal",
                "Planificador",
                "Corredor / consultor",
                "Constructora",
                "Entidad patrocinante",
                "Inmobiliaria",
                "Arquitectura / ingeniería",
                "Otro",
            ],
            index=1 if profile["role"] == "Planificador" else 0,
        )
        plan = st.selectbox("Plan", ["Free", "Pro", "Empresa"], index=["Free", "Pro", "Empresa"].index(profile["plan"]))
        save_profile = st.form_submit_button("Guardar perfil")

        if save_profile:
            st.session_state.profile = {
                "name": name,
                "email": email,
                "company": company,
                "role": role,
                "plan": plan,
            }
            st.success("Perfil actualizado en esta sesión.")

    st.divider()
    st.markdown("### Planes")
    plans = json.loads((__import__("pathlib").Path(__file__).parent / "config" / "business_model.json").read_text(encoding="utf-8"))["plans"]
    cols = st.columns(3)
    for col, (plan_name, cfg) in zip(cols, plans.items()):
        with col:
            with st.container(border=True):
                st.markdown(f"### {plan_name}")
                for feature in cfg["features"]:
                    st.write(f"✓ {feature}")


# ============================================================================
# ADMIN / API
# ============================================================================
with tabs[6]:
    st.subheader("Administración técnica / APIs")
    st.caption("Panel interno del prototipo. En producción quedará separado de usuarios finales.")

    priorities = st.multiselect(
        "Prioridades",
        ["P0", "P1", "P2", "P3"],
        default=["P0", "P1"],
    )
    api_sources = [s for s in SOURCES if s["priority"] in priorities]

    if st.button("Probar APIs", type="primary"):
        progress = st.progress(0)
        for i, source in enumerate(api_sources, 1):
            result = probe_source(source, 15).to_dict()
            st.session_state.api_results[source["id"]] = result
            save_result(result)
            progress.progress(i / len(api_sources))

    api_rows = []
    for source in api_sources:
        r = st.session_state.api_results.get(source["id"])
        api_rows.append(
            {
                "P": source["priority"],
                "Proveedor": source["provider"],
                "Fuente": source["name"],
                "Estado": r["technical_status"] if r else "NO_PROBADA",
                "HTTP": r["http_status"] if r else None,
                "Latencia_ms": r["latency_ms"] if r else None,
                "Gate_legal": source["legal_gate"],
                "Error": r["error"] if r else None,
            }
        )

    st.dataframe(pd.DataFrame(api_rows), use_container_width=True, hide_index=True)

    with st.expander("Historial técnico"):
        history = load_history()
        if history:
            hdf = pd.DataFrame(history)
            cols = [
                "checked_at",
                "priority",
                "provider",
                "name",
                "technical_status",
                "http_status",
                "latency_ms",
                "schema_hash",
                "error_type",
                "error",
            ]
            cols = [c for c in cols if c in hdf.columns]
            st.dataframe(hdf[cols], use_container_width=True, hide_index=True)
        else:
            st.info("Sin historial todavía.")


st.caption(
    "Landfinder Chile MVP v0.8 · Prefactibilidad territorial. "
    "Los datos externos pertenecen a sus respectivos proveedores y están sujetos a sus licencias y condiciones."
)
