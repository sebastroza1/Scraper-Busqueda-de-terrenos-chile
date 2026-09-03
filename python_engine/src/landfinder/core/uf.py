from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field


class UFUnavailableError(RuntimeError):
    pass


class UFValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal
    date: date
    source: str = "CMF"
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cache_hit: bool = False


class UFService:
    source_url = "https://api.cmfchile.cl/api-sbifv3/recursos_api/uf"

    def __init__(self, database_path: str | Path, api_key: str | None) -> None:
        self.database_path = Path(database_path)
        self.api_key = api_key
        self._ensure_table()

    async def get_uf(self, target_date: date) -> UFValue:
        cached = self._get_cached(target_date)
        if cached:
            return cached
        if not self.api_key:
            raise UFUnavailableError("CMF_API_KEY or UF_CMF_API_KEY is required to fetch UF")

        url = f"{self.source_url}/{target_date:%Y/%m}/dias/{target_date:%d}"
        params = {"apikey": self.api_key, "formato": "json"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        items = payload.get("UFs") or []
        if not items:
            raise UFUnavailableError(f"UF value not found for {target_date.isoformat()}")

        raw_value = str(items[0]["Valor"])
        value = Decimal(raw_value.replace(".", "").replace(",", "."))
        uf = UFValue(value=value, date=target_date)
        self._cache(uf)
        return uf

    def _ensure_table(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uf_values (
                  date TEXT PRIMARY KEY,
                  value NUMERIC NOT NULL,
                  source TEXT NOT NULL,
                  retrieved_at TEXT NOT NULL
                )
                """
            )

    def _get_cached(self, target_date: date) -> UFValue | None:
        if not self.database_path.exists():
            return None
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT date, value, source, retrieved_at FROM uf_values WHERE date = ?",
                (target_date.isoformat(),),
            ).fetchone()
        if row is None:
            return None
        return UFValue(
            date=date.fromisoformat(row[0]),
            value=Decimal(str(row[1])),
            source=row[2],
            retrieved_at=datetime.fromisoformat(row[3]),
            cache_hit=True,
        )

    def _cache(self, uf: UFValue) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO uf_values(date, value, source, retrieved_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                  value = excluded.value,
                  source = excluded.source,
                  retrieved_at = excluded.retrieved_at
                """,
                (
                    uf.date.isoformat(),
                    str(uf.value),
                    uf.source,
                    uf.retrieved_at.isoformat(),
                ),
            )


def calculate_price_fields(
    *,
    amount: Decimal | None,
    currency: str | None,
    area_m2: Decimal | None,
    uf: UFValue | None,
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    if amount is None or currency is None:
        return None, None, None
    price_clp: Decimal | None = None
    price_uf: Decimal | None = None
    if currency == "CLP":
        price_clp = amount
        if uf:
            price_uf = (amount / uf.value).quantize(Decimal("0.01"))
    elif currency == "UF":
        price_uf = amount
        if uf:
            price_clp = (amount * uf.value).quantize(Decimal("1"))

    price_uf_m2 = None
    if price_uf is not None and area_m2 and area_m2 > 0:
        price_uf_m2 = (price_uf / area_m2).quantize(Decimal("0.01"))
    return price_clp, price_uf, price_uf_m2
