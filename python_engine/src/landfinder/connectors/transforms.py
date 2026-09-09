from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from landfinder.models.enums import SourceType
from landfinder.models.records import RawSourceRecord


def mercadolibre_item_to_raw(item: dict[str, Any]) -> RawSourceRecord:
    location = item.get("location") or {}
    address_line = location.get("address_line")
    city = location.get("city") or {}
    state = location.get("state") or {}
    attributes = item.get("attributes") or []
    area_raw = _mercadolibre_land_area(attributes)
    built_area_raw = _mercadolibre_built_area(attributes)
    property_land_type = _mercadolibre_property_land_type(item, area_raw)

    currency_id = str(item.get("currency_id") or "").upper()
    currency = "UF" if currency_id in {"CLF", "UF"} else currency_id or None
    price_raw = None
    if item.get("price") is not None and currency:
        price_raw = f"{currency} {item['price']}"

    image_urls = []
    thumbnail = item.get("thumbnail")
    if thumbnail:
        image_urls.append(str(thumbnail))
    for picture in item.get("pictures") or []:
        if picture.get("secure_url") or picture.get("url"):
            image_urls.append(str(picture.get("secure_url") or picture.get("url")))

    geo_information = location.get("geo_information") if isinstance(location, dict) else None
    geo_location = (
        geo_information.get("location")
        if isinstance(geo_information, dict)
        and isinstance(geo_information.get("location"), dict)
        else {}
    )
    latitude = _safe_float(location.get("latitude") or geo_location.get("latitude"))
    longitude = _safe_float(location.get("longitude") or geo_location.get("longitude"))
    location_precision = (
        "APPROXIMATE_PROPERTY" if latitude is not None and longitude is not None else None
    )
    publication_date = _parse_date(
        item.get("date_created") or item.get("start_time") or item.get("last_updated")
    )
    raw_payload = {
        **item,
        "landfinder": {
            "item_id": item.get("id"),
            "seller_id": item.get("seller_id"),
            "official_store_id": item.get("official_store_id"),
            "location_precision": location_precision,
            "surface_context": "PARCEL_AREA" if area_raw else "UNKNOWN",
            "built_surface_raw": built_area_raw,
            "built_surface_m2": _area_to_float(built_area_raw),
            "property_land_type": property_land_type,
            "original_permalink": item.get("permalink"),
            "site_id": item.get("site_id"),
            "seller_registry": item.get("landfinder_seller"),
            "seller_expansion": item.get("landfinder_seller_expansion"),
            "api_diagnostics": item.get("landfinder_api_diagnostics"),
        },
    }

    return RawSourceRecord(
        source_id="mercadolibre_real_estate",
        source_type=SourceType.MARKETPLACE,
        external_id=item.get("id"),
        canonical_url=item.get("permalink"),
        title=item.get("title"),
        description=item.get("subtitle") or item.get("description"),
        publication_date=publication_date,
        price_raw=price_raw,
        area_raw=area_raw,
        region_raw=state.get("name") if isinstance(state, dict) else None,
        commune_raw=city.get("name") if isinstance(city, dict) else None,
        address_raw=address_line,
        latitude=latitude,
        longitude=longitude,
        image_urls=list(dict.fromkeys(image_urls)),
        raw_payload=raw_payload,
    )


def mercado_publico_tender_to_raw(item: dict[str, Any]) -> RawSourceRecord:
    code = item.get("CodigoExterno") or item.get("Codigo") or item.get("code")
    title = item.get("Nombre") or item.get("name")
    dates = item.get("Fechas") or {}
    published = _parse_date(
        dates.get("FechaCreacion")
        or dates.get("FechaPublicacion")
        or item.get("FechaPublicacion")
        or item.get("FechaCreacion")
    )
    buyer = item.get("Comprador") if isinstance(item.get("Comprador"), dict) else {}
    raw_payload = _mercado_publico_payload_with_metadata(item, buyer)
    return RawSourceRecord(
        source_id="mercado_publico",
        source_type=SourceType.PUBLIC_PROCUREMENT,
        external_id=code,
        canonical_url=_first_text(
            item,
            "Url",
            "URL",
            "Link",
            "link",
            "Enlace",
            "Ficha",
            "canonical_url",
        ),
        title=title,
        description=" ".join(
            str(part)
            for part in [
                item.get("Descripcion"),
                item.get("Nombre"),
                item.get("CodigoExterno"),
                item.get("Estado"),
                buyer.get("NombreOrganismo"),
                buyer.get("NombreUnidad"),
                _items_text(item),
            ]
            if part
        ),
        publication_date=published,
        price_raw=_mercado_publico_amount(item),
        area_raw=_mercado_publico_area(item),
        region_raw=_first_text(item, "RegionTerreno", "RegionPredio", "RegionPropiedad"),
        commune_raw=_first_text(item, "ComunaTerreno", "ComunaPredio", "ComunaPropiedad"),
        address_raw=_first_text(item, "DireccionTerreno", "DireccionPredio", "DireccionPropiedad"),
        image_urls=[],
        raw_payload=raw_payload,
    )


def _attribute_value(attributes: list[dict[str, Any]], ids: set[str]) -> str | None:
    for attribute in attributes:
        if attribute.get("id") in ids:
            if attribute.get("value_name"):
                return str(attribute["value_name"])
            struct = attribute.get("value_struct")
            if isinstance(struct, dict) and struct.get("number") is not None and struct.get("unit"):
                return f"{struct['number']} {struct['unit']}"
    return None


def _mercadolibre_land_area(attributes: list[dict[str, Any]]) -> str | None:
    land_ids = {
        "LAND_AREA",
        "PLOT_AREA",
        "LOT_AREA",
        "TOTAL_AREA",
        "ITEM_TOTAL_AREA",
        "SURFACE_TOTAL",
    }
    built_terms = ("constru", "cubierta", "built", "covered", "util", "interior")
    land_terms = (
        "terreno",
        "predio",
        "parcela",
        "lote",
        "sitio",
        "superficie total",
        "total area",
        "land area",
        "plot area",
    )
    for attribute in attributes:
        attr_id = str(attribute.get("id") or "").upper()
        name = _normalize_text(str(attribute.get("name") or ""))
        if any(term in name for term in built_terms):
            continue
        if attr_id in land_ids or any(term in name for term in land_terms):
            value = _attribute_value([attribute], {attr_id})
            if value:
                return value
    return None


def _mercadolibre_built_area(attributes: list[dict[str, Any]]) -> str | None:
    built_ids = {"COVERED_AREA", "BUILT_AREA", "CONSTRUCTED_AREA"}
    built_terms = ("constru", "cubierta", "built", "covered")
    for attribute in attributes:
        attr_id = str(attribute.get("id") or "").upper()
        name = _normalize_text(str(attribute.get("name") or ""))
        if attr_id in built_ids or any(term in name for term in built_terms):
            value = _attribute_value([attribute], {attr_id})
            if value:
                return value
    return None


def _area_to_float(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"(\d{1,3}(?:[.\s]\d{3})+|\d+(?:[,.]\d+)?)", value)
    if not match:
        return None
    number = match.group(1).replace(".", "").replace(" ", "").replace(",", ".")
    try:
        parsed = float(number)
    except ValueError:
        return None
    unit = _normalize_text(value)
    if "ha" in unit or "hectarea" in unit:
        return parsed * 10000
    return parsed


def _mercadolibre_property_land_type(item: dict[str, Any], area_raw: str | None) -> str:
    attributes = item.get("attributes") or []
    text = _normalize_text(
        " ".join(
            str(part)
            for part in [
                item.get("title"),
                item.get("subtitle"),
                item.get("category_id"),
                (item.get("landfinder_category") or {}).get("name")
                if isinstance(item.get("landfinder_category"), dict)
                else None,
                (item.get("landfinder_category") or {}).get("path")
                if isinstance(item.get("landfinder_category"), dict)
                else None,
                *[
                    attribute.get("name")
                    for attribute in attributes
                    if isinstance(attribute, dict)
                ],
            ]
            if part
        )
    )
    land_terms = (
        "terreno",
        "sitio",
        "parcela",
        "lote",
        "loteo",
        "macrolote",
        "eriazo",
        "predio",
        "suelo",
    )
    structure_terms = (
        "casa",
        "galpon",
        "bodega",
        "construccion",
        "construida",
        "edificada",
    )
    non_land_terms = (
        "departamento",
        "depto",
        "oficina",
        "estacionamiento",
        "box",
    )
    has_land_signal = any(term in text for term in land_terms)
    has_structure_signal = any(term in text for term in structure_terms)
    if any(term in text for term in non_land_terms) and not has_land_signal:
        return "NON_LAND_PROPERTY"
    if area_raw and has_structure_signal:
        return "LAND_WITH_STRUCTURE"
    if has_land_signal and not has_structure_signal:
        return "VACANT_LAND"
    if area_raw and has_land_signal:
        return "VACANT_LAND"
    return "UNKNOWN"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_number_text(value: Any) -> float | None:
    text = str(value or "").strip().replace(".", "").replace(",", ".")
    return _safe_float(text)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _first_text(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _mercado_publico_amount(item: dict[str, Any]) -> str | None:
    for key in ("MontoEstimado", "Monto", "Estimacion"):
        value = item.get(key)
        if value not in (None, "", 0):
            numeric = _safe_float(value)
            if numeric is not None and numeric <= 1000:
                continue
            return f"CLP {value}"
    return None


def _mercado_publico_payload_with_metadata(
    item: dict[str, Any],
    buyer: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(item)
    landfinder = dict(payload.get("landfinder") or {})
    amount = _mercado_publico_amount_metadata(item)
    surface = _mercado_publico_surface_metadata(item)
    property_location = {
        "property_region": _first_text(item, "RegionTerreno", "RegionPredio", "RegionPropiedad"),
        "property_commune": _first_text(item, "ComunaTerreno", "ComunaPredio", "ComunaPropiedad"),
        "property_address": _first_text(
            item,
            "DireccionTerreno",
            "DireccionPredio",
            "DireccionPropiedad",
        ),
        "location_precision": "UNKNOWN",
    }
    organization = {
        "organization_name": buyer.get("NombreOrganismo") or buyer.get("NombreUnidad"),
        "organization_region": _first_text(buyer, "RegionUnidad", "Region", "region"),
        "organization_commune": _first_text(buyer, "ComunaUnidad", "Comuna", "comuna"),
        "organization_address": _first_text(buyer, "DireccionUnidad", "Direccion", "direccion"),
    }
    fields_extracted = [
        field
        for field, value in {
            "title": item.get("Nombre") or item.get("name"),
            "description": item.get("Descripcion") or item.get("description"),
            "amount": amount.get("amount_raw"),
            "surface": surface.get("surface_raw"),
            "property_region": property_location["property_region"],
            "property_commune": property_location["property_commune"],
            "property_address": property_location["property_address"],
            "url": _first_text(
                item,
                "Url",
                "URL",
                "Link",
                "link",
                "Enlace",
                "Ficha",
                "canonical_url",
            ),
        }.items()
        if value not in (None, "")
    ]
    expected_fields = [
        "title",
        "description",
        "amount",
        "surface",
        "property_region",
        "property_commune",
        "property_address",
        "url",
    ]
    fields_missing = [field for field in expected_fields if field not in fields_extracted]
    landfinder.update(
        {
            **organization,
            **property_location,
            **amount,
            **surface,
            "fields_extracted": fields_extracted,
            "fields_missing": fields_missing,
            "extraction_reasons": _mercado_publico_extraction_reasons(fields_missing),
            "data_completeness_score": _data_completeness_score(fields_extracted),
        }
    )
    payload["landfinder"] = landfinder
    return payload


def _mercado_publico_amount_metadata(item: dict[str, Any]) -> dict[str, Any]:
    amount_raw = _mercado_publico_amount(item)
    classification = str((item.get("landfinder") or {}).get("procurement_classification") or "")
    amount_type = "UNKNOWN"
    if amount_raw:
        if classification in {"LAND_DEMAND", "PROPERTY_DEMAND"}:
            amount_type = "PROCUREMENT_BUDGET"
        elif classification in {"LAND_SALE_PROCESS", "PROPERTY_FOR_SALE"}:
            amount_type = "MINIMUM_SALE_PRICE"
        elif classification == "PROPERTY_FOR_LEASE":
            amount_type = "LEASE_PRICE"
        elif classification == "PROPERTY_FOR_CONCESSION":
            amount_type = "CONCESSION_FEE"
        else:
            amount_type = "UNKNOWN_AMOUNT"
    return {
        "amount_raw": amount_raw,
        "amount_clp": _safe_number_text(amount_raw.replace("CLP", "").strip())
        if amount_raw
        else None,
        "amount_type": amount_type,
        "amount_source": (
            "MontoEstimado" if item.get("MontoEstimado") not in (None, "", 0) else None
        ),
        "amount_confidence": 0.7 if amount_raw else 0.0,
    }


def _mercado_publico_surface_metadata(item: dict[str, Any]) -> dict[str, Any]:
    surface_raw, surface_context = _mercado_publico_area_with_context(item)
    return {
        "surface_raw": surface_raw,
        "surface_context": surface_context,
        "surface_source": "public_api_text" if surface_raw else None,
        "surface_confidence": 0.85
        if surface_raw and surface_context == "PARCEL_AREA"
        else 0.0,
    }


def _mercado_publico_area(item: dict[str, Any]) -> str | None:
    surface_raw, surface_context = _mercado_publico_area_with_context(item)
    return surface_raw if surface_context == "PARCEL_AREA" else None


def _mercado_publico_area_with_context(item: dict[str, Any]) -> tuple[str | None, str]:
    candidates: list[str] = []
    for key in ("Superficie", "Area", "MetrosCuadrados"):
        value = item.get(key)
        if value not in (None, ""):
            candidates.append(f"superficie del terreno {value}")
    for entry in _item_entries(item):
        for key in ("Descripcion", "NombreProducto", "Categoria"):
            value = entry.get(key)
            if value:
                candidates.append(str(value))
    for value in (item.get("Descripcion"), item.get("Nombre")):
        if value:
            candidates.append(str(value))

    for text in candidates:
        area_pattern = (
            r"(?<!\w)(\d{1,3}(?:[.\s]\d{3})+|\d+(?:[,.]\d+)?)\s*"
            r"(?:m2|m\u00b2|mts2|metros cuadrados|ha|has|hectareas|hectarea|"
            r"hect\u00e1reas|hect\u00e1rea)\b"
        )
        match = re.search(
            area_pattern,
            text,
            flags=re.IGNORECASE,
        )
        if match:
            context = _area_context(text, match.start(), match.end())
            return match.group(0), context
    return None, "UNKNOWN_AREA"


def _area_context(text: str, start: int, end: int) -> str:
    window = text[max(0, start - 80) : min(len(text), end + 80)]
    normalized = _normalize_text(window)
    if any(token in normalized for token in ("cesped", "cubre suelo", "jardin", "area verde")):
        return "LAWN_AREA"
    if any(
        token in normalized for token in ("obra", "intervenir", "rehabilitacion", "recuperacion")
    ):
        return "WORKS_AREA"
    if any(token in normalized for token in ("construida", "edificada", "edificio")):
        return "BUILDING_AREA"
    if any(token in normalized for token in ("calzada", "camino", "ruta", "vereda")):
        return "ROAD_AREA"
    parcel_terms = (
        "superficie predial",
        "superficie del predio",
        "superficie terreno",
        "superficie del terreno",
        "superficie lote",
        "superficie del lote",
        "predio",
        "terreno",
        "lote",
        "pano",
        "inmueble",
    )
    if any(token in normalized for token in parcel_terms):
        return "PARCEL_AREA"
    return "UNKNOWN_AREA"


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.replace("\ufffd", " ").lower())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(without_accents.split())


def _items_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for entry in _item_entries(item)[:20]:
        for key in ("NombreProducto", "Descripcion", "Producto", "Categoria"):
            value = entry.get(key)
            if value:
                parts.append(str(value))
    return " ".join(parts)


def _item_entries(item: dict[str, Any]) -> list[dict[str, Any]]:
    items = item.get("Items")
    if not isinstance(items, dict):
        return []
    listing = items.get("Listado")
    if not isinstance(listing, list):
        return []
    return [entry for entry in listing if isinstance(entry, dict)]


def _mercado_publico_extraction_reasons(fields_missing: list[str]) -> dict[str, str]:
    reasons = {
        "surface": "No public field/text with compatible unit was found.",
        "property_region": "Buyer region is not treated as property location.",
        "property_commune": "Buyer commune is not treated as property location.",
        "property_address": "Buyer address is not treated as property address.",
        "url": "Public API did not expose a web ficha URL.",
    }
    return {field: reasons[field] for field in fields_missing if field in reasons}


def _data_completeness_score(fields_extracted: list[str]) -> int:
    weights = {
        "title": 15,
        "description": 15,
        "amount": 15,
        "surface": 15,
        "property_region": 10,
        "property_commune": 10,
        "property_address": 10,
        "url": 10,
    }
    return min(100, sum(weights[field] for field in fields_extracted if field in weights))
