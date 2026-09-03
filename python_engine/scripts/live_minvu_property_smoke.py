from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from landfinder.geospatial.minvu import MinvuArcGisConnector
from landfinder.geospatial.territorial import TerritorialAnalyzer
from landfinder.models.enums import SourceType
from landfinder.models.records import NormalizedPropertyRecord
from landfinder.storage.repositories import (
    Database,
    GeospatialCacheRepository,
    PropertyRepository,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Live IDE MINVU persisted property smoke test.")
    parser.add_argument("--lat", type=float, default=-33.4489)
    parser.add_argument("--lon", type=float, default=-70.6693)
    args = parser.parse_args()

    with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        database = Database(Path(temp_dir) / "landfinder_minvu_smoke.sqlite")
        property_id = PropertyRepository(database).upsert(
            NormalizedPropertyRecord(
                source_id="manual_smoke",
                source_type=SourceType.MANUAL,
                external_id="minvu-smoke",
                title="Coordenada manual temporal para prueba MINVU",
                latitude=args.lat,
                longitude=args.lon,
            )
        )
        analyzer = TerritorialAnalyzer(
            database=database,
            minvu=MinvuArcGisConnector(cache=GeospatialCacheRepository(database)),
        )
        result = await analyzer.refresh_property(property_id, force_refresh=True)
        print(
            json.dumps(
                {
                    "property_id": property_id,
                    "coordinate": {"latitude": args.lat, "longitude": args.lon},
                    "urban_limit": _compact_urban_limit(result.get("urban_limit")),
                    "risk_intersection": _compact_risk(result.get("risk_intersection")),
                    "evidence_count": len(result.get("evidence") or []),
                    "geometry_metrics": _compact_geometry_metrics(result.get("geometry_metrics")),
                    "database": "temporary",
                },
                ensure_ascii=True,
                indent=2,
            )
        )


def _compact_urban_limit(value: object) -> dict[str, object]:
    payload = value if isinstance(value, dict) else {}
    return {
        "status": payload.get("status"),
        "service": payload.get("service"),
        "layer": payload.get("layer"),
        "feature_count": payload.get("feature_count"),
        "confidence": payload.get("confidence"),
        "matched_attributes": payload.get("matched_attributes"),
    }


def _compact_risk(value: object) -> dict[str, object]:
    payload = value if isinstance(value, dict) else {}
    return {
        "status": payload.get("status"),
        "risk_types": payload.get("risk_types"),
        "layers": payload.get("layers"),
        "confidence": payload.get("confidence"),
        "analysis_precision": payload.get("analysis_precision"),
    }


def _compact_geometry_metrics(value: object) -> dict[str, object]:
    payload = value if isinstance(value, dict) else {}
    return {
        "geometry_status": payload.get("geometry_status"),
        "geometry_type": payload.get("geometry_type"),
        "geometry_source": payload.get("geometry_source"),
        "geometry_confidence": payload.get("geometry_confidence"),
        "geometric_area_m2": payload.get("geometric_area_m2"),
        "perimeter_m": payload.get("perimeter_m"),
        "centroid_latitude": payload.get("centroid_latitude"),
        "centroid_longitude": payload.get("centroid_longitude"),
        "shape_warnings_json": payload.get("shape_warnings_json"),
    }


if __name__ == "__main__":
    asyncio.run(main())
