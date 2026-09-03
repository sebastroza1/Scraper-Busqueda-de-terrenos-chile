from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import transform

from landfinder.models.enums import GeometryStatus, GeometryType
from landfinder.models.property import GeometryMetrics

WGS84_EPSG = 4326


@dataclass(frozen=True)
class ParcelGeometryMetrics:
    geometry_type: GeometryType
    parcel_geometry: dict[str, Any] | None
    geometry_area_m2: float | None
    geometry_perimeter_m: float | None
    bounding_box: tuple[float, float, float, float] | None
    centroid_latitude: float | None
    centroid_longitude: float | None
    estimated_width_m: float | None
    estimated_depth_m: float | None
    width_depth_ratio: float | None
    compactness: float | None
    elongation: float | None
    verified_street_frontage_m: float | None = None


def calculate_parcel_metrics(
    geometry_geojson: dict[str, Any],
    *,
    input_epsg: int = WGS84_EPSG,
    advertised_area_m2: float | None = None,
    official_area_m2: float | None = None,
    source_name: str | None = None,
) -> GeometryMetrics:
    geometry = shape(geometry_geojson)
    if geometry.is_empty:
        raise ValueError("Geometry is empty")

    geometry_type = _geometry_type(geometry)
    wgs84_geometry = reproject_geometry(geometry, input_epsg=input_epsg, output_epsg=WGS84_EPSG)
    centroid = wgs84_geometry.centroid
    parcel_geojson = mapping(wgs84_geometry)

    area_m2: float | None = None
    perimeter_m: float | None = None
    estimated_width_m: float | None = None
    estimated_depth_m: float | None = None
    width_depth_ratio: float | None = None
    compactness: float | None = None
    elongation: float | None = None

    if geometry_type in {GeometryType.POLYGON, GeometryType.MULTIPOLYGON}:
        metric_epsg = local_metric_epsg(centroid.x, centroid.y)
        metric_geometry = reproject_geometry(
            wgs84_geometry,
            input_epsg=WGS84_EPSG,
            output_epsg=metric_epsg,
        )
        area_m2 = float(metric_geometry.area)
        perimeter_m = float(metric_geometry.length)
        estimated_width_m, estimated_depth_m = _estimated_width_depth(metric_geometry)
        if estimated_width_m and estimated_depth_m:
            width_depth_ratio = estimated_width_m / estimated_depth_m
            elongation = estimated_depth_m / estimated_width_m
        if perimeter_m:
            compactness = 4 * math.pi * area_m2 / (perimeter_m**2)

    chosen_reference_area = official_area_m2 or advertised_area_m2
    area_difference_percent = None
    if area_m2 is not None and chosen_reference_area:
        area_difference_percent = ((area_m2 - chosen_reference_area) / chosen_reference_area) * 100

    return GeometryMetrics(
        geometry_status=GeometryStatus.VERIFIED_POLYGON
        if geometry_type in {GeometryType.POLYGON, GeometryType.MULTIPOLYGON}
        else GeometryStatus.VERIFIED_POINT,
        geometry_type=geometry_type,
        geometry_source=source_name,
        geometry_confidence=0.85 if area_m2 is not None else 0.4,
        parcel_geometry=dict(parcel_geojson),
        polygon_geojson=dict(parcel_geojson)
        if geometry_type in {GeometryType.POLYGON, GeometryType.MULTIPOLYGON}
        else None,
        official_area_m2=official_area_m2,
        area_difference_percent=area_difference_percent,
        geometric_area_m2=area_m2,
        perimeter_m=perimeter_m,
        estimated_width_m=estimated_width_m,
        estimated_depth_m=estimated_depth_m,
        width_depth_ratio=width_depth_ratio,
        verified_street_frontage_m=None,
        estimated_main_frontage_m=estimated_width_m,
        approximate_depth_m=estimated_depth_m,
        frontage_depth_ratio=width_depth_ratio,
        compactness_index=compactness,
        elongation=elongation,
        bounding_box=tuple(float(value) for value in wgs84_geometry.bounds),
        centroid_latitude=float(centroid.y),
        centroid_longitude=float(centroid.x),
        shape_quality_score=80 if area_m2 is not None else 40,
        shape_warnings=[]
        if area_m2 is not None
        else ["POINT_GEOMETRY_HAS_NO_AREA_OR_PERIMETER"],
    )


def point_geojson(longitude: float, latitude: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [longitude, latitude]}


def local_metric_epsg(longitude: float, latitude: float) -> int:
    zone = int((longitude + 180) // 6) + 1
    if latitude < 0:
        return 32700 + zone
    return 32600 + zone


def reproject_geometry(geometry: Any, *, input_epsg: int, output_epsg: int) -> Any:
    if input_epsg == output_epsg:
        return geometry
    transformer = Transformer.from_crs(
        CRS.from_epsg(input_epsg),
        CRS.from_epsg(output_epsg),
        always_xy=True,
    )
    return transform(transformer.transform, geometry)


def stable_geometry_hash(geometry_geojson: dict[str, Any], spatial_reference: str | int) -> str:
    payload = {
        "geometry": geometry_geojson,
        "spatial_reference": str(spatial_reference),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _geometry_type(geometry: Any) -> GeometryType:
    if isinstance(geometry, Point):
        return GeometryType.POINT
    if isinstance(geometry, Polygon):
        return GeometryType.POLYGON
    if isinstance(geometry, MultiPolygon):
        return GeometryType.MULTIPOLYGON
    return GeometryType.UNKNOWN


def _estimated_width_depth(metric_geometry: Any) -> tuple[float | None, float | None]:
    rectangle = metric_geometry.minimum_rotated_rectangle
    coords = list(rectangle.exterior.coords)
    if len(coords) < 5:
        return None, None
    lengths = []
    for index in range(4):
        x1, y1 = coords[index]
        x2, y2 = coords[index + 1]
        lengths.append(math.hypot(x2 - x1, y2 - y1))
    unique_lengths = sorted({round(length, 6) for length in lengths if length > 0})
    if not unique_lengths:
        return None, None
    if len(unique_lengths) == 1:
        return unique_lengths[0], unique_lengths[0]
    return unique_lengths[0], unique_lengths[-1]
