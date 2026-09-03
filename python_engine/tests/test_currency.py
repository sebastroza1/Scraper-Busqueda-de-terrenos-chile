from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from landfinder.core.uf import UFService, UFUnavailableError, UFValue, calculate_price_fields


@pytest.mark.asyncio
async def test_uf_cache(tmp_path) -> None:
    db = tmp_path / "uf.sqlite"
    service = UFService(db, api_key=None)
    service._cache(
        UFValue(
            date=date(2026, 8, 30),
            value=Decimal("39841.72"),
            retrieved_at=datetime.now(UTC),
        )
    )

    uf = await service.get_uf(date(2026, 8, 30))
    assert uf.value == Decimal("39841.72")


@pytest.mark.asyncio
async def test_uf_missing_key_is_clear_error(tmp_path) -> None:
    service = UFService(tmp_path / "uf.sqlite", api_key=None)
    with pytest.raises(UFUnavailableError):
        await service.get_uf(date(2026, 8, 31))


def test_calculate_price_fields() -> None:
    uf = UFValue(date=date(2026, 8, 30), value=Decimal("40000"))
    price_clp, price_uf, price_uf_m2 = calculate_price_fields(
        amount=Decimal("80000000"),
        currency="CLP",
        area_m2=Decimal("10000"),
        uf=uf,
    )
    assert price_clp == Decimal("80000000")
    assert price_uf == Decimal("2000.00")
    assert price_uf_m2 == Decimal("0.20")
