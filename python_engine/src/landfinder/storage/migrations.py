from __future__ import annotations

import sqlite3
from pathlib import Path

from landfinder.storage.database import SCHEMA_PATH

CURRENT_SCHEMA_VERSION = 6


def migrate_database(database_path: str | Path) -> None:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }

        if 1 not in applied:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)")

        if 2 not in applied:
            _apply_v2(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (2)")

        if 3 not in applied:
            _apply_v3(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (3)")

        if 4 not in applied:
            _apply_v4(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (4)")

        if 5 not in applied:
            _apply_v5(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (5)")

        if 6 not in applied:
            _apply_v6(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (6)")


def _apply_v2(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS uf_values (
          date TEXT PRIMARY KEY,
          value NUMERIC NOT NULL,
          source TEXT NOT NULL,
          retrieved_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scraping_runs (
          run_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          filters_json TEXT NOT NULL,
          sources_json TEXT NOT NULL DEFAULT '[]',
          found_count INTEGER NOT NULL DEFAULT 0,
          processed_count INTEGER NOT NULL DEFAULT 0,
          discarded_count INTEGER NOT NULL DEFAULT 0,
          started_at TEXT,
          finished_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scraping_errors (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT REFERENCES scraping_runs(run_id) ON DELETE SET NULL,
          source_id TEXT,
          stage TEXT,
          property_id TEXT,
          message TEXT NOT NULL,
          exception TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS app_settings (
          key TEXT PRIMARY KEY,
          value_json TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _apply_v3(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(
        connection,
        "property_candidates",
        "geometry_status",
        "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    )
    _add_column_if_missing(connection, "property_candidates", "geometry_source", "TEXT")
    _add_column_if_missing(
        connection,
        "property_candidates",
        "geometry_type",
        "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    )
    _add_column_if_missing(connection, "property_candidates", "parcel_geometry", "TEXT")
    _add_column_if_missing(connection, "property_candidates", "geometry_area_m2", "REAL")
    _add_column_if_missing(connection, "property_candidates", "geometry_perimeter_m", "REAL")
    _add_column_if_missing(connection, "property_candidates", "official_area_m2", "REAL")
    _add_column_if_missing(connection, "property_candidates", "area_difference_percent", "REAL")

    _add_column_if_missing(
        connection,
        "geometry_metrics",
        "geometry_status",
        "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    )
    _add_column_if_missing(
        connection,
        "geometry_metrics",
        "geometry_type",
        "TEXT NOT NULL DEFAULT 'UNKNOWN'",
    )
    _add_column_if_missing(connection, "geometry_metrics", "parcel_geometry", "TEXT")
    _add_column_if_missing(connection, "geometry_metrics", "official_area_m2", "REAL")
    _add_column_if_missing(connection, "geometry_metrics", "area_difference_percent", "REAL")
    _add_column_if_missing(connection, "geometry_metrics", "estimated_width_m", "REAL")
    _add_column_if_missing(connection, "geometry_metrics", "estimated_depth_m", "REAL")
    _add_column_if_missing(connection, "geometry_metrics", "width_depth_ratio", "REAL")
    _add_column_if_missing(connection, "geometry_metrics", "verified_street_frontage_m", "REAL")

    _add_column_if_missing(connection, "evidence_records", "property_id", "TEXT")
    _add_column_if_missing(connection, "evidence_records", "category", "TEXT")
    _add_column_if_missing(connection, "evidence_records", "value", "TEXT")
    _add_column_if_missing(connection, "evidence_records", "source_name", "TEXT")
    _add_column_if_missing(connection, "evidence_records", "source_url", "TEXT")
    _add_column_if_missing(connection, "evidence_records", "layer_name", "TEXT")
    _add_column_if_missing(connection, "evidence_records", "source_record_id", "TEXT")
    _add_column_if_missing(
        connection,
        "evidence_records",
        "raw_metadata",
        "TEXT NOT NULL DEFAULT '{}'",
    )

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS geospatial_cache (
          cache_key TEXT PRIMARY KEY,
          service_url TEXT NOT NULL,
          layer_id TEXT NOT NULL,
          geometry_hash TEXT NOT NULL,
          query_hash TEXT NOT NULL,
          spatial_reference TEXT NOT NULL,
          response_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL
        );
        """
    )


def _apply_v4(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(connection, "property_candidates", "uf_rate", "NUMERIC")
    _add_column_if_missing(connection, "property_candidates", "uf_rate_date", "TEXT")
    _add_column_if_missing(connection, "property_candidates", "uf_source", "TEXT")
    _add_column_if_missing(connection, "property_candidates", "uf_retrieved_at", "TEXT")
    _add_column_if_missing(connection, "property_candidates", "uf_cache_hit", "INTEGER")

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_provenance (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          property_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
          field_name TEXT NOT NULL,
          value TEXT,
          source_id TEXT NOT NULL,
          source_type TEXT NOT NULL,
          method TEXT,
          retrieved_at TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0,
          source_url TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_data_provenance_field
          ON data_provenance (property_id, field_name, source_id, method);

        CREATE TABLE IF NOT EXISTS source_run_status (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          job_id TEXT NOT NULL,
          source_id TEXT NOT NULL,
          source_type TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0,
          configured INTEGER NOT NULL DEFAULT 0,
          attempted INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          records_received INTEGER NOT NULL DEFAULT 0,
          records_accepted INTEGER NOT NULL DEFAULT 0,
          records_rejected INTEGER NOT NULL DEFAULT 0,
          warnings TEXT NOT NULL DEFAULT '[]',
          errors TEXT NOT NULL DEFAULT '[]',
          queries_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_run_status_job_source
          ON source_run_status (job_id, source_id);
        """
    )


def _apply_v5(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_records (
          source_record_id TEXT PRIMARY KEY,
          job_id TEXT NOT NULL,
          source TEXT NOT NULL,
          source_type TEXT NOT NULL,
          external_id TEXT,
          title TEXT,
          description TEXT,
          organization TEXT,
          publication_date TEXT,
          closing_date TEXT,
          status TEXT,
          region TEXT,
          commune TEXT,
          amount NUMERIC,
          currency TEXT,
          source_url TEXT,
          raw_payload_json TEXT NOT NULL DEFAULT '{}',
          automatic_classification TEXT NOT NULL,
          automatic_confidence REAL NOT NULL DEFAULT 0,
          automatic_score INTEGER NOT NULL DEFAULT 0,
          classification_reason TEXT,
          positive_terms_json TEXT NOT NULL DEFAULT '[]',
          negative_terms_json TEXT NOT NULL DEFAULT '[]',
          rules_triggered_json TEXT NOT NULL DEFAULT '[]',
          manual_classification TEXT NOT NULL DEFAULT 'UNREVIEWED',
          manual_review_status TEXT NOT NULL DEFAULT 'UNREVIEWED',
          property_id TEXT REFERENCES property_candidates(internal_id) ON DELETE SET NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_source_records_job_classification
          ON source_records (job_id, automatic_classification, manual_classification);

        CREATE INDEX IF NOT EXISTS idx_source_records_source_external
          ON source_records (source, external_id);

        CREATE TABLE IF NOT EXISTS classifier_feedback (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_record_id TEXT NOT NULL
            REFERENCES source_records(source_record_id) ON DELETE CASCADE,
          job_id TEXT NOT NULL,
          automatic_classification TEXT NOT NULL,
          automatic_confidence REAL NOT NULL DEFAULT 0,
          automatic_score INTEGER NOT NULL DEFAULT 0,
          manual_classification TEXT NOT NULL,
          positive_terms_json TEXT NOT NULL DEFAULT '[]',
          negative_terms_json TEXT NOT NULL DEFAULT '[]',
          classification_reason TEXT,
          reviewed_at TEXT NOT NULL
        );
        """
    )


def _apply_v6(connection: sqlite3.Connection) -> None:
    source_record_columns = {
        "organization_region": "TEXT",
        "organization_commune": "TEXT",
        "organization_address": "TEXT",
        "property_region": "TEXT",
        "property_commune": "TEXT",
        "property_address": "TEXT",
        "amount_raw": "TEXT",
        "amount_type": "TEXT",
        "amount_source": "TEXT",
        "amount_confidence": "REAL NOT NULL DEFAULT 0",
        "surface_raw": "TEXT",
        "surface_m2": "REAL",
        "surface_source": "TEXT",
        "surface_confidence": "REAL NOT NULL DEFAULT 0",
        "detail_fetched": "INTEGER NOT NULL DEFAULT 0",
        "detail_attempts": "INTEGER NOT NULL DEFAULT 0",
        "detail_http_status": "INTEGER",
        "fields_extracted_json": "TEXT NOT NULL DEFAULT '[]'",
        "fields_missing_json": "TEXT NOT NULL DEFAULT '[]'",
        "extraction_reasons_json": "TEXT NOT NULL DEFAULT '{}'",
        "data_completeness_score": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in source_record_columns.items():
        _add_column_if_missing(connection, "source_records", column, definition)


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
