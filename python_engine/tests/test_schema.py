from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path


class SchemaTest(unittest.TestCase):
    def test_sqlite_schema_executes(self) -> None:
        schema_path = Path(__file__).parents[1] / "src" / "landfinder" / "storage" / "schema.sql"
        schema = schema_path.read_text(encoding="utf-8")
        with sqlite3.connect(":memory:") as connection:
            connection.executescript(schema)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

        self.assertIn("property_candidates", tables)
        self.assertIn("evidence_records", tables)
        self.assertIn("data_provenance", tables)
        self.assertIn("source_run_status", tables)
        self.assertIn("rule_evaluations", tables)
        self.assertIn("source_health", tables)


if __name__ == "__main__":
    unittest.main()
