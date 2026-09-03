from __future__ import annotations

import re
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
    area_raw = _attribute_value(attributes, {"TOTAL_AREA", "ITEM_TOTAL_AREA", "LAND_AREA"})

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

    latitude = _safe_float(location.get("latitude"))
    longitude = _safe_float(location.get("longitude"))

    return RawSourceRecord(
        source_id="mercadolibre_real_estate",
        source_type=SourceType.MARKETPLACE,
        external_id=item.get("id"),
        canonical_url=item.get("permalink"),
        title=item.get("title"),
        description=item.get("subtitle") or item.get("description"),
        price_raw=price_raw,
        area_raw=area_raw,
        region_raw=state.get("name") if isinstance(state, dict) else None,
        commune_raw=city.get("name") if isinstance(city, dict) else None,
        address_raw=address_line,
        latitude=latitude,
        longitude=longitude,
        image_urls=list(dict.fromkeys(image_urls)),
        raw_payload=item,
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
    return {
        "amount_raw": amount_raw,
        "amount_clp": _safe_number_text(amount_raw.replace("CLP", "").strip())
        if amount_raw
        else None,
        "amount_type": "ESTIMATED_AMOUNT" if amount_raw else "UNKNOWN",
        "amount_source": (
            "MontoEstimado" if item.get("MontoEstimado") not in (None, "", 0) else None
        ),
        "amount_confidence": 0.7 if amount_raw else 0.0,
    }


def _mercado_publico_surface_metadata(item: dict[str, Any]) -> dict[str, Any]:
    surface_raw = _mercado_publico_area(item)
    return {
        "surface_raw": surface_raw,
        "surface_source": "public_api_text" if surface_raw else None,
        "surface_confidence": 0.85 if surface_raw else 0.0,
    }


def _mercado_publico_area(item: dict[str, Any]) -> str | None:
    candidates: list[str] = []
    for key in ("Superficie", "Area", "MetrosCuadrados"):
        value = item.get(key)
        if value not in (None, ""):
            candidates.append(str(value))
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
            return match.group(0)
    return None


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
