from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from landfinder.basemaps import basemap_for_theme, looks_like_empty_esri_tile
from landfinder.config import source_config
from landfinder.filter_model import apply_terrain_filters, build_source_plan, overlay_signature, renderable_area_geometries, visible_area_ids
from landfinder.geocoder import address_components, candidate_score
from landfinder.map_engine import _get
from landfinder.metro_adapter import (
    METRO_FILES,
    _feature_collection,
    metro_area_summary,
    metro_current_for_area,
)
from landfinder.probes import health_state, probe_unconfigured, probe_web
from landfinder.progress import source_progress
from landfinder.persistent_cache import cache_payload_is_valid
from landfinder.summaries import land_use_summary_value
from landfinder.urban_value import _overpass, built_asset_pipeline_from_payload


class BasemapTests(unittest.TestCase):
    def test_dark_basemap_uses_no_key_watermark_config(self):
        basemap = basemap_for_theme("Oscuro")
        self.assertEqual(basemap.max_zoom, 19)
        self.assertEqual(basemap.max_native_zoom, 19)
        self.assertNotIn("cartocdn.com", basemap.tiles)
        self.assertNotIn("API_KEY", basemap.tiles.upper())
        self.assertNotIn("key=", basemap.tiles.lower())
        self.assertIn("openstreetmap.org", basemap.tiles)

    def test_light_basemap_uses_same_provider_family(self):
        light = basemap_for_theme("Claro")
        dark = basemap_for_theme("Oscuro")
        self.assertEqual(light.tiles, dark.tiles)
        self.assertEqual(light.provider, dark.provider)
        self.assertEqual(light.max_native_zoom, dark.max_native_zoom)
        self.assertIn("OpenStreetMap", light.provider)
        self.assertTrue(dark.css_filter)

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
        self.assertEqual(source_config("osm_overpass")["timeout"], 16)


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

    def test_multi_area_render_model_keeps_two_geometries(self):
        areas = [
            {"id": "A", "name": "Área A", "sector": "La Florida", "lat": -33.56, "lon": -70.60, "radius_m": 2000, "visible": True},
            {"id": "B", "name": "Área B", "sector": "Ñuñoa", "lat": -33.45, "lon": -70.59, "radius_m": 1000, "visible": True},
        ]
        geometries = renderable_area_geometries(areas)
        self.assertEqual(len(geometries), 2)
        self.assertEqual([item["id"] for item in geometries], ["A", "B"])

    def test_theme_switch_keeps_same_overlay_signature(self):
        snapshot = {"built": ["hospital"], "metro_current": True, "territory": ["minvu_prms_uso_suelo"], "risks": []}
        self.assertEqual(overlay_signature(snapshot), overlay_signature(dict(snapshot)))


class GeocoderTests(unittest.TestCase):
    def test_geocoder_address_components_preserve_santa_raquel_number(self):
        components = address_components("Sta Raquel 8204, La Florida, Santiago")
        self.assertEqual(components["house_number"], "8204")
        self.assertEqual(components["street"], "santa raquel")
        self.assertEqual(components["commune"], "La Florida")
        self.assertEqual(components["normalized_query"], "Santa Raquel 8204, La Florida, Región Metropolitana, Chile")

    def test_geocoder_precision_requires_house_number_match(self):
        components = address_components("Santa Raquel 8204, La Florida")
        score = candidate_score(
            components,
            {
                "display_name": "Avenida Santa Raquel, La Florida, Santiago, Chile",
                "type": "road",
                "address": {"road": "Avenida Santa Raquel", "city": "La Florida", "country": "Chile"},
            },
        )

        self.assertNotEqual(score["precision"], "EXACT")
        self.assertFalse(score["house_number_matched"])

    def test_geocoder_precision_accepts_confirmed_house_number(self):
        components = address_components("Santa Raquel 8204, La Florida")
        score = candidate_score(
            components,
            {
                "display_name": "Santa Raquel 8204, La Florida, Chile",
                "type": "house",
                "address": {"house_number": "8204", "road": "Santa Raquel", "city": "La Florida", "country": "Chile"},
            },
        )

        self.assertEqual(score["precision"], "EXACT")


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
    def test_overpass_retries_mirrors_with_per_endpoint_timeout(self, post, sleep):
        post.side_effect = requests.exceptions.Timeout("slow")

        with self.assertRaises(RuntimeError):
            _overpass("[out:json];node(0,0,0,0);out;", timeout=3)

        self.assertEqual(post.call_count, 3)
        for call in post.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 3)

    @patch("landfinder.urban_value.requests.post")
    def test_overpass_can_reject_suspicious_empty_mirror(self, post):
        empty = Mock()
        empty.raise_for_status.return_value = None
        empty.json.return_value = {"elements": []}
        populated = Mock()
        populated.raise_for_status.return_value = None
        populated.json.return_value = {"elements": [{"id": 1}]}
        post.side_effect = [empty, populated]

        payload = _overpass("[out:json];node(0,0,0,0);out;", timeout=3, require_nonempty=True)

        self.assertEqual(payload["elements"], [{"id": 1}])
        self.assertEqual(post.call_count, 2)

    @patch("landfinder.urban_value.time.sleep")
    @patch("landfinder.urban_value.requests.post")
    def test_overpass_does_not_accept_empty_when_other_mirrors_fail(self, post, sleep):
        empty = Mock()
        empty.raise_for_status.return_value = None
        empty.json.return_value = {"elements": []}
        post.side_effect = [requests.exceptions.Timeout("slow"), empty, requests.exceptions.Timeout("slow")]

        with self.assertRaises(RuntimeError):
            _overpass("[out:json];node(0,0,0,0);out;", timeout=3, require_nonempty=True)


class CacheTests(unittest.TestCase):
    def test_cache_error_not_empty(self):
        self.assertFalse(cache_payload_is_valid({"value": [], "count": 0, "error": "timeout"}))

    def test_poi_cache_invalidation_rejects_legacy_empty(self):
        self.assertFalse(cache_payload_is_valid({"value": [], "stored_at": 1, "count": 0}))
        self.assertTrue(cache_payload_is_valid({"value": [{"id": 1}], "stored_at": 1, "count": 1}))


class PoiPipelineTests(unittest.TestCase):
    def test_poi_pipeline_counts_and_icon_types(self):
        payload = {
            "elements": [
                {"type": "node", "id": 1, "lat": -33.1, "lon": -70.1, "tags": {"amenity": "hospital", "name": "Hospital"}},
                {"type": "node", "id": 2, "lat": -33.2, "lon": -70.2, "tags": {"amenity": "pharmacy", "name": "Farmacia"}},
                {"type": "node", "id": 3, "lat": -33.3, "lon": -70.3, "tags": {"leisure": "park", "name": "Parque"}},
                {"type": "node", "id": 4, "lat": -33.4, "lon": -70.4, "tags": {"shop": "supermarket", "name": "Supermercado"}},
            ]
        }
        result = built_asset_pipeline_from_payload(payload, ["hospital", "pharmacy", "park", "supermarket"])

        self.assertEqual(result["pipeline"]["raw"], 4)
        self.assertEqual(result["pipeline"]["matching"], 4)
        self.assertEqual(len(result["items"]), 4)
        self.assertEqual({item["type"] for item in result["items"]}, {"hospital", "pharmacy", "park", "supermarket"})


class SummaryTests(unittest.TestCase):
    def test_prms_summary_not_pending_when_source_has_intersection(self):
        bundle = {
            "technical": {"minvu_prms_uso_suelo": {"records": [{"Elemento": "Zona Habitacional Mixta"}]}},
            "layer_states": {"minvu_prms_uso_suelo": {"status": "SUCCESS_DATA", "count": 1}},
        }

        self.assertNotIn("Pendiente", land_use_summary_value(bundle))
        self.assertIn("Zona Habitacional Mixta", land_use_summary_value(bundle))


class ProgressTests(unittest.TestCase):
    def test_progress_counts_terminal_sources(self):
        half_states = {f"s{i}": {"status": "SUCCESS_DATA", "count": 1} for i in range(11)}
        half_states.update({f"l{i}": {"status": "LOADING", "count": None} for i in range(11)})
        done, total, ratio = source_progress({"layer_states": half_states})
        self.assertEqual((done, total), (11, 22))
        self.assertEqual(ratio, 0.5)

        terminal_states = {f"s{i}": {"status": "SUCCESS_EMPTY", "count": 0} for i in range(22)}
        done, total, ratio = source_progress({"layer_states": terminal_states})
        self.assertEqual((done, total, ratio), (22, 22, 1.0))


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
