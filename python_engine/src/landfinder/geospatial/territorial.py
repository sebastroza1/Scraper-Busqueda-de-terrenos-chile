from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from landfinder.classification.preliminary import (
    evaluate_preliminary_territorial_status,
    insufficient_location_assessment,
)
from landfinder.geospatial.geometry import calculate_parcel_metrics, point_geojson
from landfinder.geospatial.ipt_catalog import MinvuIptCatalog
from landfinder.geospatial.minvu import (
    RISK_AREA_LAYERS,
    URBAN_LIMIT_LAYERS,
    ArcGisLayerConfig,
    MinvuArcGisConnector,
    arcgis_geometry_to_geojson,
)
from landfinder.models.enums import (
    ConnectorStrategy,
    GeometryStatus,
    GeometryType,
    SourceRole,
    UrbanLimitStatus,
)
from landfinder.models.property import DataProvenance, EvidenceRecord, GeometryMetrics
from landfinder.storage.repositories import (
    Database,
    DataProvenanceRepository,
    EvidenceRepository,
    GeometryMetricsRepository,
    PropertyRepository,
    TerritorialCriteriaRepository,
)


class TerritorialAnalyzer:
    def __init__(
        self,
        *,
        database: Database,
        minvu: MinvuArcGisConnector,
        ipt_catalog: MinvuIptCatalog | None = None,
    ) -> None:
        self.database = database
        self.minvu = minvu
        self.ipt_catalog = ipt_catalog or MinvuIptCatalog(minvu=minvu)
        self.properties = PropertyRepository(database)
        self.geometry_metrics = GeometryMetricsRepository(database)
        self.evidence = EvidenceRepository(database)
        self.provenance = DataProvenanceRepository(database)
        self.criteria = TerritorialCriteriaRepository(database)

    async def refresh_property(
        self,
        internal_id: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        property_record = self.properties.get(internal_id)
        if property_record is None:
            raise KeyError(internal_id)

        geometry, geometry_kind, geometry_metrics = _geometry_from_property(property_record)
        if geometry_metrics:
            self.geometry_metrics.upsert(internal_id, geometry_metrics)

        evidence_records: list[EvidenceRecord] = []
        if geometry is None or geometry_kind == GeometryType.UNKNOWN:
            assessment = insufficient_location_assessment(property_record)
            evidence_records.append(
                _evidence(
                    internal_id,
                    category="geometry",
                    field="geometry_status",
                    value="UNKNOWN",
                    confidence=0,
                    raw_metadata={"reason": "No coordinates or parcel geometry available"},
                )
            )
            self.evidence.add_many(internal_id, evidence_records)
            self.provenance.add_many(_provenance_from_evidence(evidence_records))
            self.criteria.replace_for_property(internal_id, assessment.criteria)
            self.properties.update_territorial_status(
                internal_id,
                status=assessment.status,
                summary=assessment.as_dict(),
            )
            return self.summary(
                internal_id,
                extra={
                    "warnings": ["NO_GEOMETRY_AVAILABLE"],
                    "preliminary_assessment": assessment.as_dict(),
                },
            )

        urban_limit = await self._analyze_urban_limit(
            internal_id,
            geometry=geometry,
            geometry_kind=geometry_kind,
            force_refresh=force_refresh,
        )
        risk = await self._analyze_risk(
            internal_id,
            geometry=geometry,
            geometry_kind=geometry_kind,
            force_refresh=force_refresh,
        )
        prc = await self._explore_prc(
            property_record,
            geometry=geometry,
            force_refresh=force_refresh,
        )

        evidence_records.extend(urban_limit.pop("evidence"))
        evidence_records.extend(risk.pop("evidence"))
        evidence_records.extend(prc.pop("evidence"))
        self.evidence.add_many(internal_id, evidence_records)
        self.provenance.add_many(_provenance_from_evidence(evidence_records))
        assessment = evaluate_preliminary_territorial_status(
            property_record=self.properties.get(internal_id) or property_record,
            urban_limit=urban_limit,
            risk=risk,
            prc=prc,
        )
        self.criteria.replace_for_property(internal_id, assessment.criteria)
        self.properties.update_territorial_status(
            internal_id,
            status=assessment.status,
            summary=assessment.as_dict(),
        )

        return self.summary(
            internal_id,
            extra={
                "urban_limit": urban_limit,
                "risk_intersection": risk,
                "prc": prc,
                "preliminary_assessment": assessment.as_dict(),
            },
        )

    def summary(self, internal_id: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        property_record = self.properties.get(internal_id)
        if property_record is None:
            raise KeyError(internal_id)
        result = {
            "property_id": internal_id,
            "property": property_record,
            "geometry_metrics": self.geometry_metrics.get(internal_id),
            "evidence": self.evidence.list_for_property(internal_id),
            "data_provenance": self.provenance.list_for_property(internal_id),
            "territorial_criteria": self.criteria.list_for_property(internal_id),
        }
        if extra:
            result.update(extra)
        return result

    async def _analyze_urban_limit(
        self,
        internal_id: str,
        *,
        geometry: dict[str, Any],
        geometry_kind: GeometryType,
        force_refresh: bool,
    ) -> dict[str, Any]:
        query_geometry_type = _arcgis_query_geometry_type(geometry_kind)
        inspected_layers = []
        for layer in URBAN_LIMIT_LAYERS:
            payload = await self.minvu.query_layer(
                layer,
                geometry=geometry,
                geometry_type=query_geometry_type,
                return_geometry=True,
                force_refresh=force_refresh,
            )
            features = payload.get("features") or []
            inspected_layers.append(_layer_result(layer, payload, len(features)))
            if features:
                first = features[0] if isinstance(features[0], dict) else {}
                return {
                    "status": UrbanLimitStatus.YES.value,
                    "source": layer.source_name,
                    "service": layer.service_url,
                    "layer": layer.layer_name,
                    "feature_count": len(features),
                    "confidence": 0.9,
                    "retrieved_at": _now_iso(),
                    "inspected_layers": inspected_layers,
                    "matched_attributes": first.get("attributes")
                    if isinstance(first, dict)
                    else {},
                    "matched_geometries": _feature_geometries(features),
                    "matched_geojson": _feature_geojsons(features),
                    "evidence": [
                        _layer_evidence(
                            internal_id,
                            layer,
                            category="urbanism",
                            field="inside_urban_limit",
                            value=UrbanLimitStatus.YES.value,
                            confidence=0.9,
                            payload=payload,
                        )
                    ],
                }
        return {
            "status": UrbanLimitStatus.NO.value,
            "source": "IDE MINVU ArcGIS REST",
            "service": URBAN_LIMIT_LAYERS[0].service_url,
            "layer": ",".join(layer.layer_name for layer in URBAN_LIMIT_LAYERS),
            "feature_count": 0,
            "confidence": 0.7,
            "retrieved_at": _now_iso(),
            "inspected_layers": inspected_layers,
            "matched_attributes": {},
            "matched_geometries": [],
            "matched_geojson": [],
            "evidence": [
                _layer_evidence(
                    internal_id,
                    URBAN_LIMIT_LAYERS[0],
                    category="urbanism",
                    field="inside_urban_limit",
                    value=UrbanLimitStatus.NO.value,
                    confidence=0.7,
                    payload={"inspected_layers": inspected_layers},
                )
            ],
        }

    async def _analyze_risk(
        self,
        internal_id: str,
        *,
        geometry: dict[str, Any],
        geometry_kind: GeometryType,
        force_refresh: bool,
    ) -> dict[str, Any]:
        query_geometry_type = _arcgis_query_geometry_type(geometry_kind)
        risk_types: set[str] = set()
        inspected_layers = []
        source_layers = []
        for layer in RISK_AREA_LAYERS:
            payload = await self.minvu.query_layer(
                layer,
                geometry=geometry,
                geometry_type=query_geometry_type,
                return_geometry=True,
                force_refresh=force_refresh,
            )
            features = payload.get("features") or []
            inspected_layers.append(_layer_result(layer, payload, len(features)))
            if features:
                source_layers.append(layer.layer_name)
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                attributes = feature.get("attributes") or {}
                for key in ("CAT", "ZONA", "TIPO", "TIPO_RIESGO", "OBS"):
                    value = attributes.get(key)
                    if value:
                        risk_types.add(str(value))

        has_intersection = bool(risk_types or source_layers)
        point_only = geometry_kind == GeometryType.POINT
        if has_intersection:
            status = "INTERSECTION_DETECTED"
        else:
            status = "NO_INTERSECTION_DETECTED"
        if has_intersection and point_only:
            confidence = 0.65
        elif has_intersection:
            confidence = 0.85
        elif point_only:
            confidence = 0.55
        else:
            confidence = 0.75
        analysis_precision = "POINT_QUERY" if point_only else "POLYGON_INTERSECTION"
        return {
            "status": status,
            "risk_types": sorted(risk_types),
            "source": "IDE MINVU ArcGIS REST",
            "layers": source_layers or [layer.layer_name for layer in RISK_AREA_LAYERS],
            "confidence": confidence,
            "retrieved_at": _now_iso(),
            "analysis_precision": analysis_precision,
            "inspected_layers": inspected_layers,
            "matched_geometries": _feature_geometries(
                [
                    feature
                    for layer_result in inspected_layers
                    for feature in layer_result.get("features", [])
                ]
            ),
            "matched_geojson": _feature_geojsons(
                [
                    feature
                    for layer_result in inspected_layers
                    for feature in layer_result.get("features", [])
                ]
            ),
            "evidence": [
                _layer_evidence(
                    internal_id,
                    RISK_AREA_LAYERS[0],
                    category="risk",
                    field="risk_intersection",
                    value={
                        "status": status,
                        "risk_types": sorted(risk_types),
                        "analysis_precision": analysis_precision,
                    },
                    confidence=confidence,
                    payload={"inspected_layers": inspected_layers},
                )
            ],
        }

    async def _explore_prc(
        self,
        property_record: dict[str, Any],
        *,
        geometry: dict[str, Any],
        force_refresh: bool,
    ) -> dict[str, Any]:
        region = property_record.get("region")
        commune = property_record.get("commune")
        try:
            result = await self.ipt_catalog.determine_prc_zone(
                geometry=geometry,
                region_hint=str(region) if region else None,
                commune_hint=str(commune) if commune else None,
                force_refresh=force_refresh,
            )
        except Exception as exc:  # noqa: BLE001 - PRC is exploratory for this iteration.
            return {
                "status": "UNKNOWN",
                "applicable_service": None,
                "zone": None,
                "candidate_services": [],
                "warning": f"{type(exc).__name__}: {exc}",
                "evidence": [
                    _evidence(
                        property_record["internal_id"],
                        category="urbanism",
                        field="prc_applicable",
                        value="UNKNOWN",
                        confidence=0.1,
                        raw_metadata={"error": f"{type(exc).__name__}: {exc}"},
                    )
                ],
            }
        confidence = 0.75 if result.get("status") == "FOUND" else 0.2
        evidence = [
            _evidence(
                property_record["internal_id"],
                category="urbanism",
                field="prc_applicable",
                value=result.get("applicable_service") or "UNKNOWN",
                confidence=confidence,
                source_url=str(
                    result.get("source_url") or "https://geoide.minvu.cl/server/rest/services"
                ),
                layer_name=result.get("applicable_layer"),
                raw_metadata=result,
            )
        ]
        if result.get("zone"):
            evidence.append(
                _evidence(
                    property_record["internal_id"],
                    category="urbanism",
                    field="urban_zone",
                    value=result["zone"],
                    confidence=confidence,
                    source_url=str(
                        result.get("source_url") or "https://geoide.minvu.cl/server/rest/services"
                    ),
                    layer_name=result.get("applicable_layer"),
                    raw_metadata=result,
                )
            )
        return {
            **result,
            "evidence": evidence,
        }


def _geometry_from_property(
    property_record: dict[str, Any],
) -> tuple[dict[str, Any] | None, GeometryType, GeometryMetrics | None]:
    advertised_area = _safe_float(
        property_record.get("advertised_area_m2") or property_record.get("gross_area_m2")
    )
    official_area = _safe_float(property_record.get("official_area_m2"))
    parcel_geometry = _decode_json(property_record.get("parcel_geometry"))
    if isinstance(parcel_geometry, dict) and parcel_geometry.get("type"):
        metrics = calculate_parcel_metrics(
            parcel_geometry,
            advertised_area_m2=advertised_area,
            official_area_m2=official_area,
            source_name=str(property_record.get("geometry_source") or "parcel_geometry"),
        )
        metrics.geometry_retrieved_at = datetime.now(UTC)
        return parcel_geometry, metrics.geometry_type, metrics

    latitude = _safe_float(property_record.get("latitude"))
    longitude = _safe_float(property_record.get("longitude"))
    if latitude is None or longitude is None:
        return None, GeometryType.UNKNOWN, None

    geometry = point_geojson(longitude, latitude)
    metrics = GeometryMetrics(
        geometry_status=GeometryStatus.APPROXIMATE_LOCATION,
        geometry_type=GeometryType.POINT,
        geometry_source=str(property_record.get("geocoding_source") or "source_coordinates"),
        geometry_retrieved_at=datetime.now(UTC),
        geometry_confidence=_safe_float(property_record.get("geocoding_confidence")) or 0.4,
        parcel_geometry=geometry,
        centroid_latitude=latitude,
        centroid_longitude=longitude,
        shape_quality_score=30,
        shape_warnings=["APPROXIMATE_POINT_NOT_PARCEL_GEOMETRY"],
    )
    return geometry, GeometryType.POINT, metrics


def _arcgis_query_geometry_type(geometry_kind: GeometryType) -> str:
    if geometry_kind == GeometryType.POINT:
        return "esriGeometryPoint"
    if geometry_kind in {GeometryType.POLYGON, GeometryType.MULTIPOLYGON}:
        return "esriGeometryPolygon"
    raise ValueError(f"Unsupported geometry type for ArcGIS query: {geometry_kind}")


def _layer_result(
    layer: ArcGisLayerConfig,
    payload: dict[str, Any],
    feature_count: int,
) -> dict[str, Any]:
    features = payload.get("features") or []
    return {
        "service": layer.service_url,
        "layer_id": layer.layer_id,
        "layer_name": layer.layer_name,
        "feature_count": feature_count,
        "cache": payload.get("landfinder_cache", {}).get("status"),
        "features": [
            {
                "attributes": feature.get("attributes"),
                "geometry": feature.get("geometry"),
            }
            for feature in features
            if isinstance(feature, dict)
        ],
    }


def _feature_geometries(features: list[Any]) -> list[dict[str, Any]]:
    geometries = []
    for feature in features:
        if isinstance(feature, dict) and isinstance(feature.get("geometry"), dict):
            geometries.append(feature["geometry"])
    return geometries


def _feature_geojsons(features: list[Any]) -> list[dict[str, Any]]:
    geometries = []
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
            continue
        geojson = arcgis_geometry_to_geojson(feature["geometry"])
        if geojson:
            geometries.append(geojson)
    return geometries


def _layer_evidence(
    internal_id: str,
    layer: ArcGisLayerConfig,
    *,
    category: str,
    field: str,
    value: Any,
    confidence: float,
    payload: dict[str, Any],
) -> EvidenceRecord:
    return _evidence(
        internal_id,
        category=category,
        field=field,
        value=value,
        source_name=layer.source_name,
        source_url=layer.service_url,
        layer_name=layer.layer_name,
        confidence=confidence,
        raw_metadata=payload,
    )


def _evidence(
    internal_id: str,
    *,
    category: str,
    field: str,
    value: Any,
    confidence: float,
    source_name: str = "IDE MINVU ArcGIS REST",
    source_url: str = "https://geoide.minvu.cl/server/rest/services",
    layer_name: str | None = None,
    raw_metadata: dict[str, Any] | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        property_id=internal_id,
        category=category,
        field=field,
        value=value,
        raw_value=value,
        normalized_value=value,
        source=source_name,
        source_name=source_name,
        source_url=source_url,
        url=source_url,
        layer_name=layer_name,
        method=ConnectorStrategy.ARCGIS_REST,
        confidence=confidence,
        raw_metadata=raw_metadata or {},
    )


def _provenance_from_evidence(records: list[EvidenceRecord]) -> list[DataProvenance]:
    result: list[DataProvenance] = []
    for record in records:
        if not record.property_id:
            continue
        result.append(
            DataProvenance(
                property_id=record.property_id,
                field_name=record.field,
                value=record.value,
                source_id="minvu",
                source_type=SourceRole.ENRICHMENT.value,
                method=record.method,
                retrieved_at=record.retrieved_at,
                confidence=record.confidence,
                source_url=record.source_url or record.url,
            )
        )
    return result


def _decode_json(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
