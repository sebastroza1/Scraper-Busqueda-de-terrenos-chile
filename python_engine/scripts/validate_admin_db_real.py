from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from landfinder.geospatial.admin_validator import AdministrativeLocationValidator
from landfinder.storage.database import connect
from landfinder.storage.repositories import (
    Database,
    GeospatialCacheRepository,
    PropertyRepository,
)

DB_PATH = ROOT.parent / "data" / "landfinder.sqlite"
REPORT_STATUSES = (
    "MATCH",
    "COMMUNE_MISMATCH",
    "REGION_MISMATCH",
    "COMMUNE_AND_REGION_MISMATCH",
    "OUTSIDE_CHILE",
    "GEOMETRY_INVALID",
    "GEOMETRY_UNKNOWN",
    "SOURCE_ADMIN_UNKNOWN",
)
MISMATCH_STATUSES = {
    "COMMUNE_MISMATCH",
    "REGION_MISMATCH",
    "COMMUNE_AND_REGION_MISMATCH",
    "OUTSIDE_CHILE",
    "GEOMETRY_INVALID",
}


def _has_location(row: dict[str, Any]) -> bool:
    return bool(row.get("parcel_geometry")) or (
        row.get("latitude") is not None and row.get("longitude") is not None
    )


def _pick(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: row.get(key) for key in keys}


async def main() -> None:
    db = Database(DB_PATH)
    repo = PropertyRepository(db)
    validator = AdministrativeLocationValidator(cache=GeospatialCacheRepository(db))
    rows = repo.list(limit=10_000)

    counts: Counter[str] = Counter()
    mismatches: list[dict[str, Any]] = []
    validated = 0
    with_location = 0

    for row in rows:
        if _has_location(row):
            with_location += 1
        result = await validator.validate_property(row)
        updated = repo.update_admin_validation(row["internal_id"], result.as_dict())
        status = str(updated.get("admin_validation_status") or result.admin_validation_status)
        counts[status] += 1
        validated += 1
        if status in MISMATCH_STATUSES:
            mismatches.append(
                _pick(
                    updated,
                    "internal_id",
                    "source",
                    "external_id",
                    "publication_title",
                    "source_region",
                    "source_commune",
                    "calculated_region",
                    "calculated_commune",
                    "latitude",
                    "longitude",
                    "geometry_source",
                    "admin_validation_status",
                    "admin_validation_reason",
                )
            )

    with connect(DB_PATH) as connection:
        blocked = connection.execute(
            """
            SELECT COUNT(*)
            FROM property_candidates
            WHERE candidate_status = 'ACTIVE'
              AND territorial_status = 'BLOCKED_LOCATION_CONFLICT'
            """
        ).fetchone()[0]

    report = {
        "database": str(DB_PATH),
        "total_active": len(rows),
        "total_validated": validated,
        "total_with_location": with_location,
        "counts": {status: counts.get(status, 0) for status in REPORT_STATUSES},
        "blocked_location_conflict": int(blocked),
        "mismatches": mismatches,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
