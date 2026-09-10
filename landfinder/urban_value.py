from __future__ import annotations

import math
import re
import time
from typing import Any, Dict, List, Tuple

import requests
from pyproj import CRS, Transformer
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import transform as shp_transform

from .config import USER_AGENT, source_config


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Caja amplia de la red metropolitana de Santiago.
SANTIAGO_BBOX = (-34.25, -71.35, -32.75, -69.65)  # south, west, north, east


METRO_COLORS = {
    "L1": "#E31B23",   # rojo
    "L2": "#F5C400",   # amarillo
    "L3": "#8B5A2B",   # café
    "L4": "#1261A0",   # azul
    "L4A": "#19A7CE",  # celeste
    "L5": "#169B45",   # verde
    "L6": "#7F3F98",   # morado
    "L7": "#777777",   # gris
    "L8": "#F58220",   # naranjo
    "L9": "#EC77A8",   # rosado
    "EL6-P": "#7F3F98",
    "EL6-O": "#7F3F98",
}

CURRENT_LINE_ORDER = ["L1","L2","L3","L4","L4A","L5","L6"]
FUTURE_LINE_ORDER = ["EL6-P","EL6-O","L7","L8","L9"]


CURRENT_METRO_META = {
    "L1": {"name": "Línea 1", "terminals": "San Pablo ↔ Los Dominicos"},
    "L2": {"name": "Línea 2", "terminals": "Vespucio Norte ↔ Hospital El Pino"},
    "L3": {"name": "Línea 3", "terminals": "Los Libertadores ↔ Fernando Castillo Velasco"},
    "L4": {"name": "Línea 4", "terminals": "Tobalaba ↔ Plaza de Puente Alto"},
    "L4A": {"name": "Línea 4A", "terminals": "Vicuña Mackenna ↔ La Cisterna"},
    "L5": {"name": "Línea 5", "terminals": "Plaza de Maipú ↔ Vicente Valdés"},
    "L6": {"name": "Línea 6", "terminals": "Cerrillos ↔ Los Leones"},
}


FUTURE_METRO_META = {
    "EL6-P": {
        "name": "Extensión L6 Poniente",
        "status": "EN CONSTRUCCIÓN",
        "service": "2028 (referencial vigente en 2026)",
        "length": "≈ 3 km / 1 nueva estación",
        "route": "Cerrillos → Av. Suiza → Av. Salvador Allende → Lo Errázuriz",
        "terminals": "Cerrillos ↔ Lo Errázuriz",
        "official_note": "Conectará con el futuro Tren Alameda–Melipilla.",
    },
    "EL6-O": {
        "name": "Extensión L6 Oriente",
        "status": "EN DESARROLLO COMO PARTE DE L7",
        "service": "junto al proyecto Línea 7",
        "length": "≈ 1 km / 1 nueva estación",
        "route": "Los Leones → sector Isidora Goyenechea / Av. Vitacura",
        "terminals": "Los Leones ↔ futura combinación L7",
        "official_note": "Extensión oriental vinculada a la combinación con Línea 7.",
    },
    "L7": {
        "name": "Línea 7",
        "status": "EN CONSTRUCCIÓN",
        "service": "fines de 2028",
        "length": "≈ 26 km / 19 estaciones",
        "route": (
            "Renca → Cerro Navia → Quinta Normal → Santiago → Providencia → "
            "Vitacura / Las Condes. Ejes de referencia: Vicuña Mackenna (Renca), "
            "Rolando Petersen, Mapocho, Cardenal José María Caro, Providencia / "
            "Andrés Bello, Vitacura, Alonso de Córdova, Cerro Colorado y Kennedy."
        ),
        "terminals": "Renca ↔ Vitacura / Las Condes",
        "official_note": "Nueva línea transversal; operación proyectada para fines de 2028.",
    },
    "L8": {
        "name": "Línea 8",
        "status": "PROYECTO",
        "service": "2032 / 2033",
        "length": "≈ 19 km / 14 estaciones",
        "route": (
            "Los Leones → Chile España → José Pedro Alessandri → Macul → "
            "La Florida → Camilo Henríquez → sector Cerro Punta Negra, Puente Alto."
        ),
        "terminals": "Los Leones ↔ Puente Alto (Camilo Henríquez / Cerro Punta Negra)",
        "official_note": "Trazado subterráneo con combinaciones L6/L1, L3 y L4.",
    },
    "L9": {
        "name": "Línea 9",
        "status": "EN CONSTRUCCIÓN / POR ETAPAS",
        "service": "2030 / 2032 / 2033",
        "length": "≈ 27 km / 19 estaciones",
        "route": (
            "Puente Cal y Canto → eje Av. Santa Rosa → Bío Bío → La Legua → "
            "La Granja → San Ramón → Plaza La Pintana → Bajos de Mena → "
            "Plaza de Puente Alto."
        ),
        "terminals": "Puente Cal y Canto ↔ Plaza de Puente Alto",
        "official_note": "Se habilitará en tres etapas.",
    },
}


ASSET_TYPES = {
    "mall": {"label": "Mall / centro comercial", "query": '["shop"="mall"]', "color": "#EC407A"},
    "supermarket": {"label": "Supermercado", "query": '["shop"="supermarket"]', "color": "#FF7A1A"},
    "hospital": {"label": "Hospital / clínica", "query": '["amenity"~"hospital|clinic"]', "color": "#FF3F4A"},
    "education": {"label": "Universidad / educación superior", "query": '["amenity"~"university|college"]', "color": "#7C3AED"},
    "park": {"label": "Parque", "query": '["leisure"="park"]', "color": "#10B981"},
    "pharmacy": {"label": "Farmacia", "query": '["amenity"="pharmacy"]', "color": "#10B981"},
}


def _overpass(query: str, timeout: int = 50, require_nonempty: bool = False) -> Dict[str, Any]:
    errors = []
    empty_payload = None
    deadline = time.perf_counter() + max(float(timeout), 1.0)
    for index, endpoint in enumerate(OVERPASS_ENDPOINTS):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        endpoints_left = len(OVERPASS_ENDPOINTS) - index
        request_timeout = max(1.0, min(remaining, remaining / endpoints_left))
        try:
            r = requests.post(
                endpoint,
                data={"data": query},
                timeout=request_timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            r.raise_for_status()
            payload = r.json()
            if require_nonempty and not payload.get("elements"):
                empty_payload = payload
                errors.append(f"{host}: empty")
                continue
            return payload
        except Exception as exc:
            host = endpoint.split("/")[2]
            errors.append(f"{host}: {type(exc).__name__}")
            if deadline - time.perf_counter() > 0.3:
                time.sleep(0.2)
    if empty_payload is not None:
        return empty_payload
    raise RuntimeError(
        "OpenStreetMap/Overpass no respondió a tiempo. "
        "Las demás fuentes pueden seguir funcionando. "
        f"Intentos: {', '.join(errors)}"
    )


def normalize_line_ref(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).upper().replace("Í", "I").replace(" ", "")
    replacements = {
        "1":"L1","2":"L2","3":"L3","4":"L4","4A":"L4A","5":"L5","6":"L6",
        "7":"L7","8":"L8","9":"L9",
        "L1":"L1","L2":"L2","L3":"L3","L4":"L4","L4A":"L4A","L5":"L5",
        "L6":"L6","L7":"L7","L8":"L8","L9":"L9",
    }
    return replacements.get(text)


def _line_ref_from_tags(tags: Dict[str, Any]) -> str | None:
    ref = normalize_line_ref(tags.get("ref"))
    if ref:
        return ref
    name = str(tags.get("name") or "")
    m = re.search(r"(?:L[ií]nea|Linea|Metro)\s*(4A|[1-9])", name, re.I)
    return normalize_line_ref(m.group(1)) if m else None


def _element_coords(el: Dict[str, Any]) -> List[List[float]]:
    coords = []
    for p in el.get("geometry") or []:
        if "lat" in p and "lon" in p:
            coords.append([float(p["lat"]), float(p["lon"])])
    return coords


def _member_geometry(member: Dict[str, Any]) -> List[List[float]]:
    coords = []
    for p in member.get("geometry") or []:
        if "lat" in p and "lon" in p:
            coords.append([float(p["lat"]), float(p["lon"])])
    return coords


def _local_projector(lat: float, lon: float):
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs"
    )
    wgs = CRS.from_epsg(4326)
    return Transformer.from_crs(wgs, local, always_xy=True).transform


def _segments_shape(segments: List[List[List[float]]]):
    lines = []
    for seg in segments:
        if len(seg) < 2:
            continue
        try:
            lines.append(LineString([(lon, lat) for lat, lon in seg]))
        except Exception:
            pass
    if not lines:
        return None
    if len(lines) == 1:
        return lines[0]
    return MultiLineString(lines)


def analyze_line_in_aoi(
    segments: List[List[List[float]]],
    lat: float,
    lon: float,
    radius_m: float,
) -> Dict[str, Any]:
    geom = _segments_shape(segments)
    if geom is None:
        return {
            "passes_area": None,
            "distance_m": None,
            "inside_segments": [],
        }

    to_local = _local_projector(lat, lon)
    local_geom = shp_transform(to_local, geom)
    center = Point(0, 0)
    circle = center.buffer(radius_m, quad_segs=48)

    distance = float(local_geom.distance(center))
    intersects = bool(local_geom.intersects(circle))

    inside_segments = []
    if intersects:
        clipped = local_geom.intersection(circle)
        # Para el resaltado usamos los segmentos originales que intersectan AOI.
        # Así evitamos una reproyección inversa extra y mantenemos la forma OSM.
        for seg in segments:
            try:
                line = LineString([(lon_, lat_) for lat_, lon_ in seg])
                local_line = shp_transform(to_local, line)
                if local_line.intersects(circle):
                    inside_segments.append(seg)
            except Exception:
                pass

    return {
        "passes_area": intersects,
        "distance_m": round(distance, 1),
        "inside_segments": inside_segments,
    }


def query_current_metro_detailed(
    lat: float,
    lon: float,
    radius_m: float,
    timeout: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    timeout = timeout or source_config("osm_overpass")["timeout"]
    started = time.perf_counter()
    s, w, n, e = SANTIAGO_BBOX

    # relation + geometría de miembros. Esto es deliberadamente citywide:
    # el usuario pidió ver TODA la red y después saber qué líneas pasan por AOI.
    query = f"""
    [out:json][timeout:{timeout}];
    relation["type"="route"]["route"="subway"]({s},{w},{n},{e});
    out body geom;
    """
    payload = _overpass(query, timeout=timeout, require_nonempty=True)

    grouped = {
        ref: {
            "ref": ref,
            "name": CURRENT_METRO_META[ref]["name"],
            "terminals": CURRENT_METRO_META[ref]["terminals"],
            "color": METRO_COLORS[ref],
            "segments": [],
            "stations": [],
            "station_sequences": [],
        }
        for ref in CURRENT_LINE_ORDER
    }

    for rel in payload.get("elements") or []:
        if rel.get("type") != "relation":
            continue
        tags = rel.get("tags") or {}
        ref = _line_ref_from_tags(tags)
        if ref not in grouped:
            continue

        relation_segments = []
        sequence = []

        for member in rel.get("members") or []:
            geom = _member_geometry(member)
            if len(geom) >= 2 and member.get("type") == "way":
                relation_segments.append(geom)

            role = str(member.get("role") or "").lower()
            if "stop" in role or "platform" in role:
                # A veces member incluye lat/lon y tags en out geom; si no,
                # al menos preservamos role/ref.
                name = None
                if member.get("tags"):
                    name = member["tags"].get("name")
                if name:
                    sequence.append(name)

        grouped[ref]["segments"].extend(relation_segments)
        if sequence:
            grouped[ref]["station_sequences"].append(sequence)

    # Segunda consulta: estaciones, para poder mostrarlas aunque la relación
    # no incluya tags en sus miembros.
    remaining_timeout = max(1, int(timeout - (time.perf_counter() - started)))
    station_query = f"""
    [out:json][timeout:{remaining_timeout}];
    (
      nwr["railway"="station"]["station"="subway"]({s},{w},{n},{e});
      nwr["public_transport"="station"]["subway"="yes"]({s},{w},{n},{e});
      nwr["railway"="station"]["network"~"Metro",i]({s},{w},{n},{e});
    );
    out center tags;
    """
    try:
        stations_payload = _overpass(station_query, timeout=remaining_timeout)
    except Exception:
        stations_payload = {"elements": []}

    station_candidates = []
    for el in stations_payload.get("elements") or []:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        if "lat" in el and "lon" in el:
            plat, plon = el["lat"], el["lon"]
        else:
            center = el.get("center") or {}
            plat, plon = center.get("lat"), center.get("lon")
        if plat is None or plon is None:
            continue
        station_candidates.append({
            "name": name,
            "lat": float(plat),
            "lon": float(plon),
            "tags": tags,
        })

    # Asignación espacial de estaciones a líneas.
    for ref, line in grouped.items():
        geom = _segments_shape(line["segments"])
        if geom is None:
            continue
        to_local = _local_projector(lat, lon)
        local_line = shp_transform(to_local, geom)

        for st in station_candidates:
            p = shp_transform(to_local, Point(st["lon"], st["lat"]))
            d = float(local_line.distance(p))
            if d <= 120:
                line["stations"].append({
                    **st,
                    "distance_to_line_m": round(d, 1),
                })

        # deduplicar estaciones
        seen = set()
        uniq = []
        for st in line["stations"]:
            key = st["name"].strip().lower()
            if key not in seen:
                seen.add(key)
                uniq.append(st)
        line["stations"] = uniq

        analysis = analyze_line_in_aoi(line["segments"], lat, lon, radius_m)
        line.update(analysis)
        line["stations_in_area"] = [
            st for st in line["stations"]
            if haversine_m(lat, lon, st["lat"], st["lon"]) <= radius_m
        ]

        # Si OSM no nos entrega secuencia, lista alfabética es fallback visual.
        if line["station_sequences"]:
            line["route_stations"] = max(line["station_sequences"], key=len)
        else:
            line["route_stations"] = [st["name"] for st in line["stations"]]

    return grouped


def _future_ref(tags: Dict[str, Any], el_id: int | None = None) -> str | None:
    name = str(tags.get("name") or "").lower().replace("í","i")
    ref = _line_ref_from_tags(tags)

    # IDs históricos usados como respaldo para geometrías L8/L9 si siguen vigentes.
    if el_id == 1167227779:
        return "L8"
    if el_id == 1168813782:
        return "L9"

    if "linea 7" in name or ref == "L7":
        return "L7"
    if "linea 8" in name or ref == "L8":
        return "L8"
    if "linea 9" in name or ref == "L9":
        return "L9"

    if ("linea 6" in name or ref == "L6") and (
        "lo errazuriz" in name or "lo errázuriz" in name or "extension" in name or "extensión" in name
    ):
        if "oriente" in name or "isidora" in name or "vitacura" in name:
            return "EL6-O"
        return "EL6-P"

    return None


def query_future_metro_detailed(
    lat: float,
    lon: float,
    radius_m: float,
    timeout: int | None = None,
) -> Dict[str, Dict[str, Any]]:
    timeout = timeout or source_config("osm_overpass")["timeout"]
    s, w, n, e = SANTIAGO_BBOX

    query = f"""
    [out:json][timeout:{timeout}];
    (
      relation["route"="subway"]["ref"~"^(7|8|9|L7|L8|L9)$"]({s},{w},{n},{e});
      relation["name"~"L[ií]nea (6|7|8|9)|Linea (6|7|8|9)",i]({s},{w},{n},{e});
      way["name"~"L[ií]nea (6|7|8|9)|Linea (6|7|8|9)",i]({s},{w},{n},{e});
      way["railway"~"construction|proposed"]["ref"~"^(6|7|8|9|L6|L7|L8|L9)$"]({s},{w},{n},{e});
      way(1167227779);
      way(1168813782);
    );
    out body geom;
    """
    payload = _overpass(query, timeout=timeout, require_nonempty=True)

    grouped = {}
    for ref in FUTURE_LINE_ORDER:
        meta = FUTURE_METRO_META[ref]
        grouped[ref] = {
            "ref": ref,
            **meta,
            "color": METRO_COLORS[ref],
            "segments": [],
            "stations": [],
        }

    for el in payload.get("elements") or []:
        tags = el.get("tags") or {}
        ref = _future_ref(tags, el.get("id"))
        if ref not in grouped:
            continue

        if el.get("type") == "relation":
            for member in el.get("members") or []:
                geom = _member_geometry(member)
                if len(geom) >= 2 and member.get("type") == "way":
                    grouped[ref]["segments"].append(geom)
        else:
            geom = _element_coords(el)
            if len(geom) >= 2:
                grouped[ref]["segments"].append(geom)

    for ref, line in grouped.items():
        analysis = analyze_line_in_aoi(line["segments"], lat, lon, radius_m)
        line.update(analysis)
        line["geometry_available"] = bool(line["segments"])

    return grouped


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))


def query_built_assets(
    lat: float,
    lon: float,
    radius_m: int,
    selected_types: List[str],
    timeout: int | None = None,
) -> List[Dict[str, Any]]:
    timeout = timeout or source_config("osm_overpass")["timeout"]
    clauses = []
    for key in selected_types:
        cfg = ASSET_TYPES.get(key)
        if cfg:
            for osm_type in ("node", "way", "relation"):
                clauses.append(f'{osm_type}{cfg["query"]}(around:{int(radius_m)},{lat},{lon});')

    if not clauses:
        return []

    query = f"[out:json][timeout:{timeout}];(" + "".join(clauses) + ");out center tags;"
    payload = _overpass(query, timeout=timeout, require_nonempty=True)

    results = []
    raw_count = len(payload.get("elements") or [])
    for el in payload.get("elements") or []:
        tags = el.get("tags") or {}
        if "lat" in el and "lon" in el:
            plat, plon = el["lat"], el["lon"]
        else:
            center = el.get("center") or {}
            plat, plon = center.get("lat"), center.get("lon")
        if plat is None or plon is None:
            continue

        asset_type = None
        if tags.get("shop") == "mall":
            asset_type = "mall"
        elif tags.get("shop") == "supermarket":
            asset_type = "supermarket"
        elif tags.get("amenity") in {"hospital","clinic"}:
            asset_type = "hospital"
        elif tags.get("amenity") in {"university","college"}:
            asset_type = "education"
        elif tags.get("leisure") == "park":
            asset_type = "park"
        elif tags.get("amenity") == "pharmacy":
            asset_type = "pharmacy"

        if not asset_type or asset_type not in selected_types:
            continue

        cfg = ASSET_TYPES[asset_type]
        results.append({
            "type": asset_type,
            "category": cfg["label"],
            "color": cfg["color"],
            "name": tags.get("name") or tags.get("brand") or cfg["label"],
            "lat": float(plat),
            "lon": float(plon),
            "tags": tags,
            "osm_type": el.get("type"),
            "osm_id": el.get("id"),
        })

    print(
        f"[SOURCE: OSM_POI] raw={raw_count} normalized={raw_count} "
        f"matching={len(results)} stored={len(results)} requested_types={','.join(selected_types)}"
    )
    return results


def query_osm_construction(lat: float, lon: float, radius_m: int, timeout: int | None = None) -> List[Dict[str, Any]]:
    timeout = timeout or source_config("osm_overpass")["timeout"]
    query = f"""
    [out:json][timeout:{timeout}];
    (
      node["landuse"="construction"](around:{int(radius_m)},{lat},{lon});
      way["landuse"="construction"](around:{int(radius_m)},{lat},{lon});
      relation["landuse"="construction"](around:{int(radius_m)},{lat},{lon});
      node["building"="construction"](around:{int(radius_m)},{lat},{lon});
      way["building"="construction"](around:{int(radius_m)},{lat},{lon});
      relation["building"="construction"](around:{int(radius_m)},{lat},{lon});
      node["construction"](around:{int(radius_m)},{lat},{lon});
      way["construction"](around:{int(radius_m)},{lat},{lon});
      relation["construction"](around:{int(radius_m)},{lat},{lon});
    );
    out center tags;
    """
    payload = _overpass(query, timeout=timeout, require_nonempty=True)

    results = []
    for el in payload.get("elements") or []:
        tags = el.get("tags") or {}
        if "lat" in el and "lon" in el:
            plat, plon = el["lat"], el["lon"]
        else:
            center = el.get("center") or {}
            plat, plon = center.get("lat"), center.get("lon")
        if plat is None or plon is None:
            continue

        results.append({
            "type": "construction",
            "category": "Construcción mapeada en OSM",
            "color": "#E67E22",
            "name": tags.get("name") or tags.get("construction") or "Obra / construcción",
            "lat": float(plat),
            "lon": float(plon),
            "tags": tags,
            "osm_type": el.get("type"),
            "osm_id": el.get("id"),
        })
    return results
