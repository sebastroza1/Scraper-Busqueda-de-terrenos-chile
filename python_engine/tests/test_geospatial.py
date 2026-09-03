from datetime import timedelta

import pytest

from landfinder.geospatial.geometry import calculate_parcel_metrics, local_metric_epsg
from landfinder.geospatial.ipt_catalog import MinvuIptCatalog
from landfinder.geospatial.minvu import ArcGisLayerConfig, arcgis_geometry_from_geojson
from landfinder.geospatial.territorial import TerritorialAnalyzer
from landfinder.models.enums import GeometryType, SourceType
from landfinder.models.property import EvidenceRecord
from landfinder.models.records import NormalizedPropertyRecord
from landfinder.storage.repositories import (
    Database,
    EvidenceRepository,
    GeometryMetricsRepository,
    GeospatialCacheRepository,
    PropertyRepository,
    utc_now,
)


def test_parcel_metrics_use_projected_crs_for_chile() -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [-70.7000, -33.5000],
                [-70.6990, -33.5000],
                [-70.6990, -33.4990],
                [-70.7000, -33.4990],
                [-70.7000, -33.5000],
            ]
        ],
    }

    metrics = calculate_parcel_metrics(polygon, advertised_area_m2=10000)

    assert local_metric_epsg(-70.7, -33.5) == 32719
    assert metrics.geometry_type == GeometryType.POLYGON
    assert metrics.geometric_area_m2 is not None
    assert metrics.geometric_area_m2 > 9000
    assert metrics.perimeter_m is not None
    assert metrics.perimeter_m > 350
    assert metrics.estimated_width_m is not None
    assert metrics.estimated_depth_m is not None
    assert metrics.verified_street_frontage_m is None


def test_arcgis_point_geometry_includes_spatial_reference() -> None:
    geometry = arcgis_geometry_from_geojson(
        {"type": "Point", "coordinates": [-70.7, -33.5]},
        4326,
    )

    assert geometry == {"x": -70.7, "y": -33.5, "spatialReference": {"wkid": 4326}}


def test_geospatial_repositories_persist_evidence_metrics_and_cache(tmp_path) -> None:
    database = Database(tmp_path / "landfinder.sqlite")
    property_id = PropertyRepository(database).upsert(
        NormalizedPropertyRecord(
            source_id="manual",
            source_type=SourceType.MANUAL,
            external_id="manual-1",
            title="Propiedad con poligono",
            latitude=-33.5,
            longitude=-70.7,
            gross_area_m2=10000,
        )
    )
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [-70.7000, -33.5000],
                [-70.6990, -33.5000],
                [-70.6990, -33.4990],
                [-70.7000, -33.4990],
                [-70.7000, -33.5000],
            ]
        ],
    }
    metrics = calculate_parcel_metrics(polygon, source_name="test")
    GeometryMetricsRepository(database).upsert(property_id, metrics)

    stored_metrics = GeometryMetricsRepository(database).get(property_id)
    assert stored_metrics is not None
    assert stored_metrics["geometry_type"] == "POLYGON"
    assert stored_metrics["geometric_area_m2"] > 9000

    evidence = EvidenceRecord(
        property_id=property_id,
        category="urbanism",
        field="inside_urban_limit",
        value="YES",
        source="IDE MINVU ArcGIS REST",
        source_name="IDE MINVU ArcGIS REST",
        source_url="https://geoide.minvu.cl/server/rest/services",
        confidence=0.9,
    )
    evidence_id = EvidenceRepository(database).add(property_id, evidence)
    assert evidence_id > 0
    assert EvidenceRepository(database).list_for_property(property_id)[0]["value"] == '"YES"'

    layer = ArcGisLayerConfig(
        service_url="https://geoide.minvu.cl/server/rest/services/IPT/Test/FeatureServer",
        layer_id=0,
        layer_name="Test",
    )
    cache = GeospatialCacheRepository(database)
    cache.set(
        cache_key="cache-1",
        service_url=layer.service_url,
        layer_id=str(layer.layer_id),
        geometry_hash="geo",
        query_hash="query",
        spatial_reference="4326",
        response={"features": []},
        expires_at=utc_now() + timedelta(days=1),
    )
    assert cache.get("cache-1") == {"features": []}


@pytest.mark.asyncio
async def test_territorial_analyzer_persists_point_query_evidence(tmp_path) -> None:
    database = Database(tmp_path / "territorial.sqlite")
    property_id = PropertyRepository(database).upsert(
        NormalizedPropertyRecord(
            source_id="manual",
            source_type=SourceType.MANUAL,
            external_id="manual-2",
            title="Propiedad con coordenadas",
            latitude=-33.5,
            longitude=-70.7,
            gross_area_m2=10000,
        )
    )
    analyzer = TerritorialAnalyzer(database=database, minvu=_FakeMinvu())

    result = await analyzer.refresh_property(property_id)

    assert result["urban_limit"]["status"] == "YES"
    assert result["risk_intersection"]["status"] == "INTERSECTION_DETECTED"
    assert result["risk_intersection"]["analysis_precision"] == "POINT_QUERY"
    evidence_fields = {
        item["field"] for item in EvidenceRepository(database).list_for_property(property_id)
    }
    assert {"inside_urban_limit", "risk_intersection", "prc_applicable"} <= evidence_fields


@pytest.mark.asyncio
async def test_minvu_ipt_catalog_audits_layers_with_zoning_fields(tmp_path) -> None:
    database = Database(tmp_path / "catalog.sqlite")
    catalog = MinvuIptCatalog(
        minvu=_FakeMinvu(),
        cache=GeospatialCacheRepository(database),
    )

    audit = await catalog.layer_audit(
        region_hint="Metropolitana de Santiago",
        include_feature_counts=True,
    )

    assert audit["layer_count"] == 1
    assert audit["layers"][0]["service_name"] == "IPT/PRC_RM_Sur"
    assert audit["layers"][0]["has_zoning_fields"] is True
    assert audit["layers"][0]["zoning_fields"] == ["ZONA"]
    assert audit["layers"][0]["field_aliases"]["ZONA"] == "Zona"
    assert audit["layers"][0]["feature_count"] == 42
    assert audit["layers"][0]["feature_count_status"] == "COUNTED"


@pytest.mark.asyncio
async def test_minvu_ipt_catalog_only_returns_zone_from_intersected_attributes(tmp_path) -> None:
    database = Database(tmp_path / "catalog-zone.sqlite")
    catalog = MinvuIptCatalog(
        minvu=_FakeMinvu(prc_zone="ZU-1"),
        cache=GeospatialCacheRepository(database),
    )

    result = await catalog.determine_prc_zone(
        geometry={"type": "Point", "coordinates": [-70.7, -33.5]},
        region_hint="Metropolitana de Santiago",
        commune_hint="Maipu",
    )

    assert result["status"] == "FOUND"
    assert result["zone"] == "ZU-1"
    assert result["zone_field"] == "ZONA"


class _FakeMinvu:
    def __init__(self, prc_zone=None) -> None:  # noqa: ANN001
        self.root_url = "https://geoide.minvu.cl/server/rest/services"
        self.cache = None
        self.prc_zone = prc_zone

    async def discover_services(self, folder="IPT"):  # noqa: ANN001
        return [{"name": "IPT/PRC_RM_Sur", "type": "MapServer"}]

    async def service_metadata(self, service_url):  # noqa: ANN001
        return {
            "layers": [{"id": 0, "name": "Zonificacion"}],
            "spatialReference": {"wkid": 4326},
            "serviceDescription": "Fake PRC service",
        }

    async def layer_metadata(self, service_url, layer_id):  # noqa: ANN001
        return {
            "name": "Zonificacion",
            "geometryType": "esriGeometryPolygon",
            "capabilities": "Query",
            "fields": [
                {"name": "OBJECTID", "alias": "OBJECTID", "type": "esriFieldTypeOID"},
                {"name": "ZONA", "alias": "Zona", "type": "esriFieldTypeString"},
            ],
            "extent": {"spatialReference": {"wkid": 4326}},
        }

    async def layer_feature_count(self, service_url, layer_id, where="1=1"):  # noqa: ANN001, ARG002
        return 42

    async def query_layer(self, layer, **kwargs):  # noqa: ANN001, ANN003
        if "Limites_Urbanos" in layer.service_url:
            return {
                "features": [
                    {
                        "attributes": {"COM": "Maipu", "NOM": "PRC Maipu"},
                        "geometry": {
                            "rings": [
                                [[-70.8, -33.6], [-70.6, -33.6], [-70.6, -33.4], [-70.8, -33.6]]
                            ]
                        },
                    }
                ],
                "landfinder_cache": {"status": "MISS"},
            }
        if "PRC_RM_Sur" in layer.service_url:
            return {
                "features": [
                    {"attributes": {"ZONA": self.prc_zone}, "geometry": None}
                ]
                if self.prc_zone
                else [],
                "landfinder_cache": {"status": "MISS"},
            }
        return {
            "features": [
                {
                    "attributes": {"CAT": "INUNDACION"},
                    "geometry": {
                        "rings": [
                            [
                                [-70.71, -33.51],
                                [-70.69, -33.51],
                                [-70.69, -33.49],
                                [-70.71, -33.51],
                            ]
                        ]
                    },
                }
            ],
            "landfinder_cache": {"status": "MISS"},
        }

    async def discover_prc_services(self, region_hint=None):  # noqa: ANN001
        return [{"name": "IPT/PRC_RM_Sur", "type": "MapServer", "region_hint": region_hint}]
