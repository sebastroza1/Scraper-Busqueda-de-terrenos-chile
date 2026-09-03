from __future__ import annotations

import argparse
import asyncio
import json

from landfinder.geospatial.minvu import (
    RISK_AREA_LAYERS,
    URBAN_LIMIT_LAYERS,
    MinvuArcGisConnector,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Live IDE MINVU ArcGIS smoke test.")
    parser.add_argument("--lat", type=float, default=-33.4489)
    parser.add_argument("--lon", type=float, default=-70.6693)
    parser.add_argument("--region", default="Metropolitana de Santiago")
    args = parser.parse_args()

    connector = MinvuArcGisConnector()
    geometry = {"type": "Point", "coordinates": [args.lon, args.lat]}
    urban = await connector.query_layer(
        URBAN_LIMIT_LAYERS[0],
        geometry=geometry,
        geometry_type="esriGeometryPoint",
        return_geometry=False,
    )
    risk = await connector.query_layer(
        RISK_AREA_LAYERS[0],
        geometry=geometry,
        geometry_type="esriGeometryPoint",
        return_geometry=False,
    )
    prc = await connector.discover_prc_services(args.region)
    print(
        json.dumps(
            {
                "coordinate": {"latitude": args.lat, "longitude": args.lon},
                "urban_service": URBAN_LIMIT_LAYERS[0].service_url,
                "urban_layer": URBAN_LIMIT_LAYERS[0].layer_name,
                "urban_features": len(urban.get("features") or []),
                "risk_service": RISK_AREA_LAYERS[0].service_url,
                "risk_layer": RISK_AREA_LAYERS[0].layer_name,
                "risk_features": len(risk.get("features") or []),
                "prc_candidates": [item.get("name") for item in prc[:20]],
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
