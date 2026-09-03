from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python_engine" / "src"))

from landfinder.geospatial.ipt_catalog import MinvuIptCatalog  # noqa: E402
from landfinder.geospatial.minvu import MinvuArcGisConnector  # noqa: E402
from landfinder.geospatial.territorial import TerritorialAnalyzer  # noqa: E402
from landfinder.models.enums import SourceType  # noqa: E402
from landfinder.models.records import NormalizedPropertyRecord  # noqa: E402
from landfinder.storage.repositories import (  # noqa: E402
    Database,
    GeospatialCacheRepository,
    PropertyRepository,
)


async def main() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="landfinder_minvu_smoke_"))
    database = Database(temp_dir / "landfinder.sqlite")
    property_id = PropertyRepository(database).upsert(
        NormalizedPropertyRecord(
            source_id="manual_live_smoke",
            source_type=SourceType.MANUAL,
            external_id="santiago-centro-smoke",
            title="Coordenada temporal Santiago Centro",
            region="Metropolitana de Santiago",
            commune="Santiago",
            latitude=-33.4489,
            longitude=-70.6693,
            gross_area_m2=1000,
        )
    )

    cache = GeospatialCacheRepository(database)
    minvu = MinvuArcGisConnector(cache=cache)
    ipt_catalog = MinvuIptCatalog(minvu=minvu, cache=cache)
    analyzer = TerritorialAnalyzer(
        database=database,
        minvu=minvu,
        ipt_catalog=ipt_catalog,
    )

    result = await analyzer.refresh_property(property_id, force_refresh=True)
    layer_audit = await ipt_catalog.layer_audit(
        region_hint="Metropolitana de Santiago",
        force_refresh=True,
    )

    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "coordinate": {"latitude": -33.4489, "longitude": -70.6693},
        "urban_limit": _pick(
            result.get("urban_limit"),
            (
                "status",
                "service",
                "layer",
                "feature_count",
                "confidence",
                "matched_attributes",
            ),
        ),
        "risk_intersection": _pick(
            result.get("risk_intersection"),
            (
                "status",
                "risk_types",
                "layers",
                "confidence",
                "analysis_precision",
            ),
        ),
        "prc": _pick(
            result.get("prc"),
            (
                "status",
                "applicable_service",
                "applicable_layer",
                "zone",
                "zone_field",
                "urban_zone",
                "warning",
            ),
        )
        | {
            "candidate_layers": (result.get("prc") or {}).get("candidate_layers", [])[:5],
            "queried_layers": (result.get("prc") or {}).get("queried_layers", [])[:5],
        },
        "ipt_layer_audit": {
            "layer_count": layer_audit.get("layer_count"),
            "layers": [
                _pick(
                    layer,
                    (
                        "service_name",
                        "service_url",
                        "layer_id",
                        "layer_name",
                        "geometry_type",
                        "spatial_reference",
                        "zoning_fields",
                        "has_zoning_fields",
                    ),
                )
                for layer in (layer_audit.get("layers") or [])[:8]
            ],
            "warnings": layer_audit.get("warnings", [])[:5],
        },
        "evidence_count": len(result.get("evidence") or []),
        "geometry_metrics": result.get("geometry_metrics"),
        "database": "temporary",
        "database_path": str(database.database_path),
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2, default=str))


def _pick(value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: value.get(key) for key in keys}


if __name__ == "__main__":
    asyncio.run(main())
