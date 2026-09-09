from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from landfinder.connectors.auctions.bienes_nacionales import (
    BienesNacionalesProvider,
    _parsed_to_raw,
)
from landfinder.normalization.records import normalize_raw_record
from landfinder.storage.database import connect
from landfinder.storage.repositories import Database, PropertyRepository

DB_PATH = ROOT.parent / "data" / "landfinder.sqlite"


def _targets(external_ids: list[str]) -> list[dict[str, Any]]:
    with connect(DB_PATH) as connection:
        rows = connection.execute(
            f"""
            SELECT internal_id, external_id, canonical_url
            FROM property_candidates
            WHERE source = 'bienes_nacionales'
              AND external_id IN ({",".join("?" for _ in external_ids)})
            ORDER BY external_id
            """,
            external_ids,
        ).fetchall()
    return [dict(row) for row in rows]


async def main() -> None:
    external_ids = sys.argv[1:]
    if not external_ids:
        raise SystemExit("Usage: refresh_bienes_records.py L-2026-S1-016 [...]")

    db = Database(DB_PATH)
    repo = PropertyRepository(db)
    provider = BienesNacionalesProvider()
    refreshed = []
    for target in _targets(external_ids):
        html = await provider._get_text(target["canonical_url"])
        parsed = await provider._parse_detail(target["canonical_url"], html, True)
        normalized = normalize_raw_record(_parsed_to_raw(parsed))
        internal_id = repo.upsert(normalized)
        updated = repo.get(internal_id)
        refreshed.append(
            {
                "internal_id": internal_id,
                "external_id": target["external_id"],
                "source_url": target["canonical_url"],
                "title": updated.get("publication_title") if updated else None,
                "cadastral_id": parsed.get("cadastral_id"),
                "bienes_id": parsed.get("bienes_id"),
                "geometry_source": updated.get("geometry_source") if updated else None,
                "latitude": updated.get("latitude") if updated else None,
                "longitude": updated.get("longitude") if updated else None,
            }
        )
    print(json.dumps(refreshed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
