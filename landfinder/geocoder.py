from __future__ import annotations

import re
import unicodedata
from typing import Any

import requests

from .config import USER_AGENT


RM_BOUNDS = {
    "south": -33.95,
    "north": -33.05,
    "west": -71.25,
    "east": -70.10,
}

COMMUNE_CENTERS = {
    "santiago": (-33.4489, -70.6693, 12),
    "nunoa": (-33.4569, -70.5978, 13),
    "providencia": (-33.4263, -70.6170, 13),
    "las condes": (-33.4088, -70.5674, 12),
    "vitacura": (-33.4001, -70.5980, 12),
    "la reina": (-33.4478, -70.5345, 12),
    "macul": (-33.4850, -70.5992, 12),
    "san miguel": (-33.5007, -70.6514, 13),
    "estacion central": (-33.4628, -70.6998, 13),
    "quinta normal": (-33.4297, -70.6992, 13),
    "renca": (-33.4066, -70.7283, 12),
    "cerrillos": (-33.5024, -70.7163, 12),
    "maipu": (-33.5108, -70.7562, 12),
    "la florida": (-33.5227, -70.5982, 12),
    "puente alto": (-33.6117, -70.5758, 12),
}

STREET_ALIASES = {
    "sta": "santa",
    "sta.": "santa",
    "av": "",
    "av.": "",
    "avenida": "",
    "calle": "",
}


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", without_marks).strip()


def requested_house_number(text: str) -> str | None:
    match = re.search(r"\b(\d{2,6})\b", text)
    return match.group(1) if match else None


def normalize_street(text: str) -> str:
    tokens = []
    for raw in re.split(r"[\s,]+", normalize_text(text)):
        token = STREET_ALIASES.get(raw, raw)
        if token and not token.isdigit() and token not in {"region", "metropolitana", "chile"}:
            tokens.append(token)
    return " ".join(tokens)


def address_components(query: str) -> dict[str, Any]:
    normalized = normalize_text(query)
    house_number = requested_house_number(query)
    commune = None
    for name in sorted(COMMUNE_CENTERS, key=len, reverse=True):
        if name in normalized:
            commune = "Ñuñoa" if name == "nunoa" else "Maipú" if name == "maipu" else name.title()
            break
    street_part = query.split(",")[0]
    if house_number:
        street_part = re.sub(rf"\b{re.escape(house_number)}\b", "", street_part)
    return {
        "house_number": house_number,
        "street": normalize_street(street_part),
        "commune": commune,
        "region": "Región Metropolitana" if "metropolitana" in normalized or "santiago" in normalized else None,
        "country": "Chile",
        "normalized_query": canonical_query(query),
    }


def canonical_query(query: str) -> str:
    components = address_components_without_canonical(query)
    pieces = []
    street = components["street"]
    if street:
        title_street = " ".join(part.capitalize() for part in street.split())
        pieces.append(f"{title_street} {components['house_number']}".strip())
    if components.get("commune"):
        pieces.append(components["commune"])
    pieces.extend(["Región Metropolitana", "Chile"])
    return ", ".join(dict.fromkeys(part for part in pieces if part))


def address_components_without_canonical(query: str) -> dict[str, Any]:
    normalized = normalize_text(query)
    house_number = requested_house_number(query)
    commune = None
    for name in sorted(COMMUNE_CENTERS, key=len, reverse=True):
        if name in normalized:
            commune = "Ñuñoa" if name == "nunoa" else "Maipú" if name == "maipu" else name.title()
            break
    street_part = query.split(",")[0]
    if house_number:
        street_part = re.sub(rf"\b{re.escape(house_number)}\b", "", street_part)
    return {
        "house_number": house_number,
        "street": normalize_street(street_part),
        "commune": commune,
        "region": "Región Metropolitana" if "metropolitana" in normalized or "santiago" in normalized else None,
        "country": "Chile",
    }


def in_rm_bounds(lat: float, lon: float) -> bool:
    return (
        RM_BOUNDS["south"] <= lat <= RM_BOUNDS["north"]
        and RM_BOUNDS["west"] <= lon <= RM_BOUNDS["east"]
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
    key = normalize_text(text)
    return any(char.isdigit() for char in key) or any(token in key for token in ("av.", "avenida", "calle", "pasaje", "camino", "ruta"))


def candidate_score(query_components: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    address = result.get("address") or {}
    display = normalize_text(result.get("display_name") or "")
    house_requested = query_components.get("house_number")
    house_found = str(address.get("house_number") or "")
    street_found = normalize_street(" ".join(str(address.get(key) or "") for key in ("road", "pedestrian", "footway")))
    commune_found = normalize_text(str(address.get("city") or address.get("town") or address.get("municipality") or address.get("county") or ""))
    street_query = query_components.get("street") or ""
    commune_query = normalize_text(query_components.get("commune") or "")

    house_number_matched = bool(house_requested and house_found == house_requested)
    street_matched = bool(street_query and (street_query in street_found or street_query in display))
    commune_matched = bool(commune_query and (commune_query in commune_found or commune_query in display))
    country_matched = "chile" in display or normalize_text(str(address.get("country") or "")) == "chile"

    score = 0
    score += 80 if house_number_matched else 0
    score += 35 if street_matched else 0
    score += 20 if commune_matched else 0
    score += 10 if country_matched else 0

    if house_requested and house_number_matched and street_matched and commune_matched:
        precision = "EXACT"
    elif house_requested and street_matched and commune_matched:
        precision = "INTERPOLATED" if result.get("type") in {"house", "building"} else "STREET"
    elif street_matched:
        precision = "STREET"
    elif commune_matched:
        precision = "COMMUNE"
    else:
        precision = "APPROXIMATE"

    return {
        "score": score,
        "precision": precision,
        "house_number_matched": house_number_matched,
        "street_matched": street_matched,
        "commune_matched": commune_matched,
        "country_matched": country_matched,
        "house_number_found": house_found or None,
        "street_found": street_found or None,
        "commune_found": commune_found or None,
    }


def record_from_candidate(query: str, result: dict[str, Any], score: dict[str, Any]) -> dict[str, Any] | None:
    try:
        lat = float(result["lat"])
        lon = float(result["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not in_rm_bounds(lat, lon):
        return None
    confidence = "alta" if score["precision"] == "EXACT" else "media" if score["precision"] in {"INTERPOLATED", "STREET", "COMMUNE"} else "baja"
    return {
        "query": query,
        "display_name": result.get("display_name") or query,
        "lat": lat,
        "lon": lon,
        "zoom": 17 if score["precision"] == "EXACT" else 15 if score["precision"] in {"INTERPOLATED", "STREET"} else 13,
        "precision": score["precision"],
        "confidence": confidence,
        "source": "nominatim",
        "house_number_requested": requested_house_number(query),
        **score,
        "raw": result,
    }


def geocode_address(query: str, timeout: int = 8) -> dict[str, Any] | None:
    raw_query = query.strip()
    if not raw_query:
        return None
    coords = parse_coordinates(raw_query)
    if coords:
        return {
            "query": raw_query,
            "display_name": "coordenadas",
            "lat": coords[0],
            "lon": coords[1],
            "zoom": 15,
            "precision": "EXACT",
            "confidence": "alta",
            "source": "coordinates",
            "house_number_requested": None,
            "house_number_matched": False,
            "street_matched": False,
            "commune_matched": False,
            "score": 100,
            "raw": {},
        }

    components = address_components(raw_query)
    queries = [
        components["normalized_query"],
        raw_query if "chile" in normalize_text(raw_query) else f"{raw_query}, Chile",
    ]
    if looks_like_address(raw_query) and components.get("commune"):
        queries.append(f"{raw_query}, Región Metropolitana, Chile")

    candidates: list[dict[str, Any]] = []
    for q in dict.fromkeys(queries):
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": q,
                "format": "jsonv2",
                "limit": 8,
                "countrycodes": "cl",
                "addressdetails": 1,
                "bounded": 1,
                "viewbox": f"{RM_BOUNDS['west']},{RM_BOUNDS['north']},{RM_BOUNDS['east']},{RM_BOUNDS['south']}",
            },
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        response.raise_for_status()
        for result in response.json():
            score = candidate_score(components, result)
            record = record_from_candidate(raw_query, result, score)
            if record:
                candidates.append(record)

    if not candidates:
        for name, (lat, lon, zoom) in COMMUNE_CENTERS.items():
            if name in normalize_text(raw_query):
                return {
                    "query": raw_query,
                    "display_name": name.title(),
                    "lat": lat,
                    "lon": lon,
                    "zoom": zoom,
                    "precision": "COMMUNE",
                    "confidence": "media",
                    "source": "commune_gazetteer",
                    "score": 20,
                    "house_number_matched": False,
                    "street_matched": False,
                    "commune_matched": True,
                    "raw": {},
                }
        return {
            "query": raw_query,
            "display_name": raw_query,
            "lat": None,
            "lon": None,
            "zoom": 11,
            "precision": "NOT_FOUND",
            "confidence": "baja",
            "source": "nominatim",
            "score": 0,
            "house_number_matched": False,
            "street_matched": False,
            "commune_matched": False,
            "raw": {},
        }

    candidates.sort(key=lambda item: item["score"], reverse=True)
    selected = dict(candidates[0])
    selected["components"] = components
    selected["candidates"] = candidates[:5]
    return selected
