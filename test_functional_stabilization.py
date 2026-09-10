from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from landfinder.icons import ICON_REGISTRY, marker_svg
from landfinder.metro_adapter import METRO_FILES, _feature_collection, metro_dataset_status
from landfinder.registry import load_sources
from landfinder.runtime_sources import provider_key_for, source_uses_overpass
from landfinder.source_states import (
    ERROR,
    MISSING_DATA,
    STALE,
    SUCCESS_DATA,
    SUCCESS_EMPTY,
    TIMEOUT,
    classify_runtime_error,
    normalize_status,
)


class SourceRoutingTests(unittest.TestCase):
    def setUp(self):
        self.sources = {source["id"]: source for source in load_sources()}

    def test_official_sources_do_not_depend_on_overpass(self):
        official = [
            "minvu_limites_urbanos",
            "minvu_prms_uso_suelo",
            "minvu_area_riesgo",
            "mma_humedales",
            "mma_areas_protegidas",
            "mop_contratos_obras",
            "mop_red_vial",
            "dga_derechos",
            "senapred_tsunami",
            "sernageomin_relaves",
            "sea_proyectos",
        ]
        for source_id in official:
            with self.subTest(source_id=source_id):
                self.assertFalse(source_uses_overpass(source_id, self.sources))
                self.assertNotEqual(provider_key_for(source_id, self.sources), "provider:overpass")

    def test_only_osm_runtime_sources_share_overpass_breaker(self):
        self.assertEqual(provider_key_for("built_hospital", self.sources), "provider:overpass")
        self.assertEqual(provider_key_for("osm_construction", self.sources), "provider:overpass")
        self.assertNotEqual(provider_key_for("metro_current", self.sources), "provider:overpass")


class SemanticStateTests(unittest.TestCase):
    def test_legacy_statuses_normalize_to_explicit_states(self):
        self.assertEqual(normalize_status("OK", 3), SUCCESS_DATA)
        self.assertEqual(normalize_status("OK", 0), SUCCESS_EMPTY)
        self.assertEqual(normalize_status("OK_SIN_COINCIDENCIAS", 0), SUCCESS_EMPTY)
        self.assertEqual(normalize_status("STALE_CACHE", 4), STALE)
        self.assertEqual(normalize_status("SOURCE_ERROR", None), ERROR)

    def test_runtime_errors_distinguish_timeout(self):
        self.assertEqual(classify_runtime_error("Read timed out"), TIMEOUT)
        self.assertEqual(classify_runtime_error("ConnectionError"), ERROR)


class MetroFutureDatasetTests(unittest.TestCase):
    def test_future_dataset_with_empty_files_is_missing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            files = {
                "current_lines": tmp_path / "metro_lines_current.geojson",
                "current_stations": tmp_path / "metro_stations_current.geojson",
                "future_lines": tmp_path / "metro_lines_future.geojson",
                "future_stations": tmp_path / "metro_stations_future.geojson",
            }
            for key, path in files.items():
                path.write_text(json.dumps(_feature_collection([], key)), encoding="utf-8")
            with patch("landfinder.metro_adapter.METRO_FILES", files):
                self.assertEqual(metro_dataset_status("future")["status"], MISSING_DATA)


class IconRegistryTests(unittest.TestCase):
    def test_visible_categories_have_local_svg_icons(self):
        required = [
            "metro_current",
            "metro_future",
            "metro_station",
            "home",
            "building",
            "hospital",
            "pharmacy",
            "supermarket",
            "park",
            "education",
            "school",
            "terrain",
            "risk",
            "wetland",
            "protected",
            "mop",
            "seia",
            "health",
            "mall",
            "fuel",
            "water",
            "industrial",
            "selected_location",
        ]
        for key in required:
            with self.subTest(key=key):
                self.assertIn(key, ICON_REGISTRY)
                self.assertTrue(ICON_REGISTRY[key]["label"])
                self.assertIn("<svg", marker_svg(key))


if __name__ == "__main__":
    unittest.main()
