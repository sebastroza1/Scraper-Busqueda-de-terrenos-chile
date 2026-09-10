from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from landfinder.basemaps import basemap_for_theme, looks_like_empty_esri_tile
from landfinder.config import source_config
from landfinder.filter_model import apply_terrain_filters, build_source_plan, visible_area_ids
from landfinder.map_engine import _get
from landfinder.metro_adapter import (
    METRO_FILES,
    _feature_collection,
    metro_area_summary,
    metro_current_for_area,
)
from landfinder.probes import health_state, probe_unconfigured, probe_web
from landfinder.urban_value import _overpass


class BasemapTests(unittest.TestCase):
    def test_dark_basemap_uses_native_zoom_16(self):
        basemap = basemap_for_theme("Oscuro")
        self.assertEqual(basemap.max_zoom, 19)
        self.assertEqual(basemap.max_native_zoom, 16)
        self.assertIn("arcgisonline.com", basemap.tiles)

    def test_light_basemap_uses_osm_to_zoom_19(self):
        basemap = basemap_for_theme("Claro")
        self.assertEqual(basemap.max_native_zoom, 19)
        self.assertIn("openstreetmap.org", basemap.tiles)

    def test_esri_empty_tile_detector_only_matches_high_zoom_small_tiles(self):
        self.assertTrue(looks_like_empty_esri_tile(200, 2521, 17))
        self.assertFalse(looks_like_empty_esri_tile(200, 2521, 16))
        self.assertFalse(looks_like_empty_esri_tile(404, 2521, 18))
        self.assertFalse(looks_like_empty_esri_tile(200, 9000, 18))


class SourceConfigTests(unittest.TestCase):
    def test_mop_sources_use_short_timeout(self):
        source = {"id": "mop_contratos_obras", "provider": "MOP", "kind": "download_catalog"}
        self.assertEqual(source_config(source)["timeout"], 8)

    def test_unconfigured_sources_do_not_probe(self):
        source = {"id": "gap_portal_inmobiliario", "provider": "Portal", "kind": "unconfigured"}
        self.assertEqual(source_config(source)["timeout"], 0)

    def test_osm_sources_use_overpass_policy(self):
        self.assertEqual(source_config("osm_overpass")["timeout"], 10)


class SourcePlanTests(unittest.TestCase):
    def test_humedales_visible_and_exclusion_uses_one_source(self):
        plan = build_source_plan(
            {"risks": ["mma_humedales"], "built": []},
            {"exclude_wetlands": True},
        )

        self.assertEqual(plan["risk_sources"].count("mma_humedales"), 1)
        self.assertIn("mma_humedales", plan["risk_visual_sources"])
        self.assertIn("mma_humedales", plan["exclusion_sources"])

    def test_proximity_filter_adds_poi_without_visual_layer(self):
        plan = build_source_plan(
            {"built": []},
            {"near_supermarket": True},
        )

        self.assertEqual(plan["built_query_types"], ["supermarket"])
        self.assertEqual(plan["built_visual_types"], [])

    def test_multi_area_visibility_does_not_depend_on_active_area(self):
        areas = [{"id": "A", "visible": True}, {"id": "B", "visible": True}]
        self.assertEqual(visible_area_ids(areas), ["A", "B"])


class HealthStateTests(unittest.TestCase):
    def test_health_parser_distinguishes_not_configured(self):
        health = health_state({
            "source_id": "gap",
            "technical_status": "NOT_CONFIGURED",
            "error_type": None,
            "http_status": None,
            "latency_ms": None,
            "checked_at": "now",
            "error": "missing credentials",
        })
        self.assertEqual(health["status"], "not_configured")

    def test_health_parser_detects_rate_limit(self):
        health = health_state({
            "source_id": "source",
            "technical_status": "SOURCE_ERROR",
            "error_type": "HTTP_429",
            "http_status": 429,
            "latency_ms": 120,
            "checked_at": "now",
            "error": "Too Many Requests",
        })
        self.assertEqual(health["status"], "rate_limited")

    def test_health_parser_marks_slow_success(self):
        health = health_state({
            "source_id": "source",
            "technical_status": "OK",
            "error_type": None,
            "http_status": 200,
            "latency_ms": 6800,
            "checked_at": "now",
            "error": None,
        })
        self.assertEqual(health["status"], "slow")

    def test_probe_unconfigured_is_not_down(self):
        result = probe_unconfigured({
            "id": "gap",
            "provider": "Portal",
            "name": "Portal",
            "category": "Terrenos",
            "priority": "P3",
            "kind": "unconfigured",
            "audit_status": "PENDING",
            "runtime_policy": "OFF",
            "legal_gate": "REQUIRES_CONTRACT",
            "note": "Sin API oficial",
        })
        self.assertEqual(health_state(result)["status"], "not_configured")

    @patch("landfinder.probes.request_get")
    def test_empty_web_response_is_degraded(self, request_get):
        response = Mock()
        response.status_code = 200
        response.headers = {"content-type": "text/html"}
        response.raise_for_status.return_value = None
        response.iter_content.return_value = iter([b""])
        request_get.return_value = (response, 55)
        source = {
            "id": "web",
            "provider": "Provider",
            "name": "Web",
            "category": "Catálogo",
            "priority": "P1",
            "kind": "web_page",
            "audit_status": "OK",
            "runtime_policy": "CANARY",
            "legal_gate": "PUBLIC",
            "url": "https://example.test",
        }

        result = probe_web(source, 4)

        self.assertEqual(result.technical_status, "DEGRADED")


class MapEngineTimeoutTests(unittest.TestCase):
    @patch("landfinder.map_engine.requests.get")
    def test_mop_get_clamps_timeout_to_runtime_policy(self, request_get):
        response = Mock()
        request_get.return_value = response

        result = _get("https://rest-sit.mop.gob.cl/example", timeout=25)

        self.assertIs(result, response)
        self.assertEqual(request_get.call_args.kwargs["timeout"], 8)

    @patch("landfinder.urban_value.time.sleep")
    @patch("landfinder.urban_value.requests.post")
    def test_overpass_splits_total_timeout_across_mirrors(self, post, sleep):
        post.side_effect = requests.exceptions.Timeout("slow")

        with self.assertRaises(RuntimeError):
            _overpass("[out:json];node(0,0,0,0);out;", timeout=3)

        self.assertGreaterEqual(post.call_count, 2)
        for call in post.call_args_list:
            self.assertLessEqual(call.kwargs["timeout"], 3)


class MetroAdapterTests(unittest.TestCase):
    def test_metro_cache_loads_lines_and_stations_without_remote_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            files = {
                "current_lines": tmp_path / "metro_lines_current.geojson",
                "current_stations": tmp_path / "metro_stations_current.geojson",
                "future_lines": tmp_path / "metro_lines_future.geojson",
                "future_stations": tmp_path / "metro_stations_future.geojson",
            }
            files["current_lines"].write_text(json.dumps(_feature_collection([
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[-70.61, -33.56], [-70.59, -33.56]]},
                    "properties": {"ref": "L4", "name": "Línea 4", "color": "#1261A0", "future": False},
                }
            ], "metro_lines_current")), encoding="utf-8")
            files["current_stations"].write_text(json.dumps(_feature_collection([
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-70.60, -33.56]},
                    "properties": {"name": "Estación Fixture", "refs": ["L4"], "future": False, "tags": {}},
                }
            ], "metro_stations_current")), encoding="utf-8")
            files["future_lines"].write_text(json.dumps(_feature_collection([], "metro_lines_future")), encoding="utf-8")
            files["future_stations"].write_text(json.dumps(_feature_collection([], "metro_stations_future")), encoding="utf-8")

            with patch("landfinder.metro_adapter.METRO_FILES", files), patch("landfinder.metro_adapter.refresh_metro_cache") as refresh:
                lines = metro_current_for_area(-33.56, -70.60, 500)

        refresh.assert_not_called()
        self.assertGreater(len(lines["L4"]["segments"]), 0)
        self.assertEqual(lines["L4"]["stations"][0]["name"], "Estación Fixture")
        self.assertTrue(lines["L4"]["passes_area"])

    def test_metro_nearest_station_summary(self):
        current = {
            "L4": {
                "ref": "L4",
                "passes_area": False,
                "distance_to_area_m": 700,
                "stations": [{"name": "Cercana", "lat": -33.5600, "lon": -70.6000}],
                "stations_in_area": [],
            }
        }
        summary = metro_area_summary(current, {}, -33.5600, -70.6063, 500, nearby_threshold_m=1000)

        self.assertEqual(summary["nearest_station"]["name"], "Cercana")
        self.assertEqual(summary["current_nearby"][0]["ref"], "L4")


class TerrainFilterTests(unittest.TestCase):
    def test_exclude_wetland_discards_intersecting_terrain(self):
        terrains = [{"id": "inside", "lat": 0, "lon": 0}, {"id": "outside", "lat": 5, "lon": 5}]
        wetland = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]],
                    },
                    "properties": {},
                }
            ],
        }

        kept = apply_terrain_filters(terrains, {"mma_humedales": wetland}, {"exclude_wetlands": True})

        self.assertEqual([terrain["id"] for terrain in kept], ["outside"])

    def test_proximity_filter_uses_explicit_distance(self):
        terrains = [
            {"id": "near", "metro_distance_m": 700},
            {"id": "far", "metro_distance_m": 1500},
        ]

        kept = apply_terrain_filters(terrains, {}, {"near_metro": True, "near_metro_distance": 1000})

        self.assertEqual([terrain["id"] for terrain in kept], ["near"])


if __name__ == "__main__":
    unittest.main()
