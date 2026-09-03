from decimal import Decimal

import pytest

from landfinder.normalization.locations import normalize_location
from landfinder.normalization.parsers import clean_text, parse_area, parse_price


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.000 m²", Decimal("10000.00")),
        ("10000 m2", Decimal("10000.00")),
        ("10,000 m2", Decimal("10000.00")),
        ("1 ha", Decimal("10000.00")),
        ("1,2 ha", Decimal("12000.00")),
        ("1.2 hectareas", Decimal("12000.00")),
    ],
)
def test_parse_area(raw: str, expected: Decimal) -> None:
    parsed = parse_area(raw)
    assert parsed is not None
    assert parsed.value_m2 == expected


@pytest.mark.parametrize(
    ("raw", "currency", "amount"),
    [
        ("UF 18.500", "UF", Decimal("18500.00")),
        ("$ 250.000.000", "CLP", Decimal("250000000.00")),
        ("CLP 1,2 millones", "CLP", Decimal("1200000.00")),
        ("$ 850 mil", "CLP", Decimal("850000.00")),
    ],
)
def test_parse_price(raw: str, currency: str, amount: Decimal) -> None:
    parsed = parse_price(raw)
    assert parsed is not None
    assert parsed.currency == currency
    assert parsed.amount == amount


def test_parse_price_does_not_infer_ambiguous_currency() -> None:
    assert parse_price("18.500") is None


def test_parse_area_requires_area_unit() -> None:
    assert parse_area("1200 unidades") is None


def test_clean_text() -> None:
    assert clean_text("<b>Terreno&nbsp;urbano</b>") == "Terreno urbano"


def test_normalize_location_commune_region() -> None:
    location = normalize_location(commune="Puente Alto")
    assert location.commune == "Puente Alto"
    assert location.region == "Metropolitana de Santiago"
    assert location.confidence >= 0.8
