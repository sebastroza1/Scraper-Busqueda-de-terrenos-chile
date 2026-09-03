from __future__ import annotations

import html
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from landfinder.models.records import ParsedArea, ParsedPrice

AREA_RE = re.compile(
    r"(?P<number>\d+(?:[.,]\d{1,3})?(?:[.,]\d{3})*)\s*(?P<unit>m2|m²|mt2|mts2|ha|has|hectarea|hectareas|hectárea|hectáreas)\b",
    re.IGNORECASE,
)

PRICE_RE = re.compile(
    r"(?P<currency>UF|CLP|\$)\s*(?P<number>\d+(?:[.,]\d{1,3})?(?:[.,]\d{3})*)\s*(?P<scale>millones|millon|millón|miles|mil)?",
    re.IGNORECASE,
)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(value).lower()).strip()


def parse_area(value: str | None) -> ParsedArea | None:
    text = clean_text(value)
    if not text:
        return None
    match = AREA_RE.search(strip_accents(text))
    if not match:
        return None

    number = _parse_number(match.group("number"), unit_hint=match.group("unit"))
    if number is None:
        return None

    unit = normalize_key(match.group("unit"))
    multiplier = (
        Decimal("10000") if unit in {"ha", "has", "hectarea", "hectareas"} else Decimal("1")
    )
    return ParsedArea(
        raw_value=text,
        value_m2=(number * multiplier).quantize(Decimal("0.01")),
        confidence=0.95,
    )


def parse_price(value: str | None) -> ParsedPrice | None:
    text = clean_text(value)
    if not text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None

    currency_raw = match.group("currency").upper()
    currency = "CLP" if currency_raw in {"$", "CLP"} else "UF"
    number = _parse_number(match.group("number"), unit_hint=currency)
    if number is None:
        return None

    scale = normalize_key(match.group("scale") or "")
    if scale in {"millon", "millones"}:
        number *= Decimal("1000000")
    elif scale in {"mil", "miles"}:
        number *= Decimal("1000")

    return ParsedPrice(
        raw_value=text,
        amount=number.quantize(Decimal("0.01")),
        currency=currency,
        confidence=0.9 if currency_raw in {"UF", "CLP", "$"} else 0.6,
    )


def _parse_number(raw: str, *, unit_hint: str | None = None) -> Decimal | None:
    text = raw.strip()
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in text:
        text = _normalize_single_separator(text, ",", unit_hint=unit_hint)
    elif "." in text:
        text = _normalize_single_separator(text, ".", unit_hint=unit_hint)

    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _normalize_single_separator(text: str, separator: str, *, unit_hint: str | None) -> str:
    before, after = text.rsplit(separator, 1)
    normalized_hint = normalize_key(unit_hint or "")
    if len(after) == 3 and normalized_hint not in {"ha", "has", "hectarea", "hectareas"}:
        return before.replace(separator, "") + after
    return before.replace(separator, "") + "." + after
