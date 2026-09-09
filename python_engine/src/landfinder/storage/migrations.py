from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from landfinder.storage.database import SCHEMA_PATH

CURRENT_SCHEMA_VERSION = 9


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

        if 7 not in applied:
            _apply_v7(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (7)")

        if 8 not in applied:
            _apply_v8(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (8)")

        if 9 not in applied:
            _apply_v9(connection)
            connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (9)")


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


def _apply_v7(connection: sqlite3.Connection) -> None:
    property_columns = {
        "location_source": "TEXT",
        "location_method": "TEXT",
        "geocoded_at": "TEXT",
        "territorial_status": "TEXT NOT NULL DEFAULT 'SIN_INFORMACION_SUFICIENTE'",
        "territorial_checked_at": "TEXT",
        "territorial_summary_json": "TEXT NOT NULL DEFAULT '{}'",
        "candidate_status": "TEXT NOT NULL DEFAULT 'ACTIVE'",
        "manual_notes": "TEXT",
    }
    for column, definition in property_columns.items():
        _add_column_if_missing(connection, "property_candidates", column, definition)

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS geocoding_cache (
          cache_key TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          query_text TEXT NOT NULL,
          normalized_query TEXT NOT NULL,
          request_json TEXT NOT NULL DEFAULT '{}',
          response_json TEXT NOT NULL DEFAULT '{}',
          latitude REAL,
          longitude REAL,
          display_name TEXT,
          location_precision TEXT NOT NULL DEFAULT 'UNKNOWN',
          location_method TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0,
          source_url TEXT,
          created_at TEXT NOT NULL,
          last_used_at TEXT NOT NULL,
          expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS property_location_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
          latitude REAL,
          longitude REAL,
          location_source TEXT,
          location_method TEXT NOT NULL,
          location_precision TEXT NOT NULL DEFAULT 'UNKNOWN',
          location_confidence REAL NOT NULL DEFAULT 0,
          address TEXT,
          region TEXT,
          commune TEXT,
          raw_result_json TEXT NOT NULL DEFAULT '{}',
          assigned_by TEXT NOT NULL DEFAULT 'system',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS minvu_layers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          provider TEXT NOT NULL,
          service_name TEXT NOT NULL,
          layer_name TEXT NOT NULL,
          layer_id INTEGER NOT NULL,
          endpoint TEXT NOT NULL,
          geometry_type TEXT,
          spatial_reference TEXT NOT NULL DEFAULT '{}',
          fields_json TEXT NOT NULL DEFAULT '[]',
          status TEXT NOT NULL,
          last_checked TEXT NOT NULL,
          raw_metadata_json TEXT NOT NULL DEFAULT '{}',
          UNIQUE(provider, endpoint, layer_id)
        );

        CREATE TABLE IF NOT EXISTS territorial_criteria (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          internal_id TEXT NOT NULL REFERENCES property_candidates(internal_id) ON DELETE CASCADE,
          criterion_key TEXT NOT NULL,
          criterion_label TEXT NOT NULL,
          result TEXT NOT NULL,
          value TEXT,
          source TEXT,
          endpoint TEXT,
          layer_name TEXT,
          checked_at TEXT NOT NULL,
          evidence_json TEXT NOT NULL DEFAULT '{}',
          confidence REAL NOT NULL DEFAULT 0,
          observation TEXT,
          UNIQUE(internal_id, criterion_key, source, layer_name)
        );

        CREATE INDEX IF NOT EXISTS idx_property_candidates_location_method
          ON property_candidates (location_method, location_precision);

        CREATE INDEX IF NOT EXISTS idx_territorial_criteria_property
          ON territorial_criteria (internal_id, checked_at);
        """
    )
    _redact_historical_scraping_errors(connection)


def _apply_v8(connection: sqlite3.Connection) -> None:
    _invalidate_suspicious_geocodes(connection)
    _reclassify_known_procurement_regressions(connection)


def _apply_v9(connection: sqlite3.Connection) -> None:
    property_columns = {
        "source_epsg": "INTEGER",
        "normalized_epsg": "INTEGER NOT NULL DEFAULT 4326",
        "source_region": "TEXT",
        "source_commune": "TEXT",
        "calculated_region": "TEXT",
        "calculated_commune": "TEXT",
        "admin_validation_status": "TEXT NOT NULL DEFAULT 'GEOMETRY_UNKNOWN'",
        "admin_validation_confidence": "REAL NOT NULL DEFAULT 0",
        "admin_validation_reason": "TEXT",
    }
    for column, definition in property_columns.items():
        _add_column_if_missing(connection, "property_candidates", column, definition)


def _invalidate_suspicious_geocodes(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT latitude, longitude, COUNT(*) AS total
        FROM property_candidates
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
          AND LOWER(COALESCE(geocoding_source, location_source, '')) = 'nominatim'
          AND UPPER(COALESCE(location_precision, 'UNKNOWN')) NOT IN (
            'PARCEL_POLYGON',
            'EXACT_COORDINATES',
            'VERIFIED_ADDRESS',
            'STREET_ADDRESS',
            'EXACT',
            'APPROXIMATE_PROPERTY'
          )
        GROUP BY latitude, longitude
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    suspicious_points = {(row[0], row[1]) for row in rows}
    if not suspicious_points:
        return
    now = "CURRENT_TIMESTAMP"
    for latitude, longitude in suspicious_points:
        candidates = connection.execute(
            """
            SELECT internal_id, anomaly_flags_json
            FROM property_candidates
            WHERE latitude = ?
              AND longitude = ?
              AND LOWER(COALESCE(geocoding_source, location_source, '')) = 'nominatim'
            """,
            (latitude, longitude),
        ).fetchall()
        for internal_id, flags_json in candidates:
            flags = _append_flags(
                flags_json,
                [
                    "INVALID_LOCATION",
                    "SUSPICIOUS_GEOCODE",
                    "TERRITORIAL_ANALYSIS_STALE",
                ],
            )
            connection.execute(
                f"""
                UPDATE property_candidates
                SET latitude = NULL,
                    longitude = NULL,
                    location_source = 'INVALID_LOCATION',
                    location_method = 'invalidated_geocode',
                    location_precision = 'UNKNOWN',
                    geocoding_source = 'INVALID_LOCATION',
                    geocoding_confidence = 0,
                    territorial_status = 'SIN_INFORMACION_SUFICIENTE',
                    anomaly_flags_json = ?,
                    manual_notes = COALESCE(manual_notes || '\n', '') ||
                      'INVALID_LOCATION_SOURCE: duplicated approximate Nominatim point.',
                    updated_at = {now}
                WHERE internal_id = ?
                """,
                (json.dumps(flags, ensure_ascii=True), internal_id),
            )
            connection.execute(
                f"""
                INSERT INTO property_location_history (
                  internal_id, latitude, longitude, location_source, location_method,
                  location_precision, location_confidence, raw_result_json,
                  assigned_by, created_at
                )
                VALUES (?, NULL, NULL, 'INVALID_LOCATION', 'invalidated_geocode',
                        'UNKNOWN', 0, ?, 'migration_v8', {now})
                """,
                (
                    internal_id,
                    json.dumps(
                        {
                            "reason": "SUSPICIOUS_GEOCODE",
                            "previous_latitude": latitude,
                            "previous_longitude": longitude,
                        },
                        ensure_ascii=True,
                    ),
                ),
            )


def _reclassify_known_procurement_regressions(connection: sqlite3.Connection) -> None:
    known = {
        "2427-87-LE26": ("GOODS_FOR_PROPERTY", "GOODS_FOR_PROPERTY_CONTEXT"),
        "2450-90-LE26": ("GOODS_FOR_PROPERTY", "GOODS_FOR_PROPERTY_CONTEXT"),
        "4328-33-B226": ("LAND_DEMAND", "PUBLIC_BUYER_LAND_DEMAND"),
        "2794-22-LR26": ("LAND_DEMAND", "PUBLIC_BUYER_LAND_DEMAND"),
        "5358-9-LR26": ("LAND_DEMAND", "PUBLIC_BUYER_LAND_DEMAND"),
        "4295-54-LR26": ("LAND_SALE_PROCESS", "LAND_SALE_PROCESS"),
    }
    for external_id, (classification, rule) in known.items():
        connection.execute(
            """
            UPDATE source_records
            SET automatic_classification = ?,
                rules_triggered_json = ?,
                classification_reason = ?,
                property_id = CASE
                  WHEN ? IN ('LAND_DEMAND', 'PROPERTY_DEMAND', 'GOODS_FOR_PROPERTY')
                  THEN NULL
                  ELSE property_id
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE external_id = ?
            """,
            (
                classification,
                json.dumps([rule], ensure_ascii=True),
                f"migration_v8={classification}; rule={rule}",
                classification,
                external_id,
            ),
        )
        if classification in {"LAND_DEMAND", "PROPERTY_DEMAND", "GOODS_FOR_PROPERTY"}:
            connection.execute(
                """
                UPDATE property_candidates
                SET candidate_status = 'SOURCE_RECORD_ONLY',
                    updated_at = CURRENT_TIMESTAMP
                WHERE source = 'mercado_publico'
                  AND external_id = ?
                """,
                (external_id,),
            )


def _append_flags(flags_json: object, new_flags: list[str]) -> list[str]:
    try:
        flags = json.loads(str(flags_json or "[]"))
    except json.JSONDecodeError:
        flags = []
    if not isinstance(flags, list):
        flags = []
    result = [str(item) for item in flags]
    for flag in new_flags:
        if flag not in result:
            result.append(flag)
    return result


def _redact_historical_scraping_errors(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT id, message, exception FROM scraping_errors").fetchall()
    for row in rows:
        message = _sanitize_secret_text(row[1])
        exception = _sanitize_secret_text(row[2])
        if message != row[1] or exception != row[2]:
            connection.execute(
                "UPDATE scraping_errors SET message = ?, exception = ? WHERE id = ?",
                (message, exception, row[0]),
            )


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _sanitize_secret_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    import re

    text = str(value)
    replacements = [
        (r"(?i)(ticket=)[^&\s'\"}\]]+", r"\1REDACTED"),
        (r"(?i)(apikey=)[^&\s'\"}\]]+", r"\1REDACTED"),
        (r"(?i)(access_token=)[^&\s'\"}\]]+", r"\1REDACTED"),
        (r"(?i)(refresh_token=)[^&\s'\"}\]]+", r"\1REDACTED"),
        (r"(?i)(password=)[^&\s'\"}\]]+", r"\1REDACTED"),
        (r"(?i)(client_secret=)[^&\s'\"}\]]+", r"\1REDACTED"),
        (r"(?i)(authorization:\s*bearer\s+)[^,\s'\"}\]]+", r"\1REDACTED"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text
