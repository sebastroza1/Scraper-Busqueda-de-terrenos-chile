from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from landfinder.models.enums import ConnectorStrategy, ManualClassification, SourceRole
from landfinder.models.property import DataProvenance, EvidenceRecord, GeometryMetrics
from landfinder.models.records import CanonicalPropertyMatch, NormalizedPropertyRecord
from landfinder.storage.database import connect, init_database


def utc_now() -> datetime:
    return datetime.now(UTC)


def _json(value: Any) -> str:
    def default(item: Any) -> str:
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, datetime):
            return item.isoformat()
        return str(item)

    return json.dumps(value, ensure_ascii=True, default=default)


def _num(value: Decimal | int | float | None) -> str | int | float | None:
    return str(value) if isinstance(value, Decimal) else value


class Database:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        init_database(self.database_path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = connect(self.database_path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class PropertyRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, record: NormalizedPropertyRecord) -> str:
        with self.database.transaction() as connection:
            existing = self._find_existing(connection, record)
            internal_id = existing or record.internal_id
            now = utc_now().isoformat()
            property_values = (
                internal_id,
                str(record.source_id),
                str(record.source_type),
                record.external_id,
                record.canonical_url,
                record.title,
                record.publication_date.isoformat() if record.publication_date else None,
                record.last_seen.isoformat(),
                "unknown",
                None,
                "unknown",
                record.region,
                record.province,
                record.commune,
                record.address,
                record.address,
                record.latitude,
                record.longitude,
                record.location_precision,
                record.location_source,
                record.location_method,
                record.geocoded_at.isoformat() if record.geocoded_at else None,
                record.geocoding_source,
                record.geocoding_confidence,
                _num(record.price_clp),
                _num(record.price_uf),
                record.uf_date.isoformat() if record.uf_date else None,
                _num(record.uf_rate),
                record.uf_rate_date.isoformat() if record.uf_rate_date else None,
                record.uf_source,
                record.uf_retrieved_at.isoformat() if record.uf_retrieved_at else None,
                1 if record.uf_cache_hit else 0 if record.uf_cache_hit is not None else None,
                _num(record.gross_area_m2),
                _num(record.gross_area_m2),
                _num(record.price_uf_m2),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                record.data_quality_score,
                _json(record.observations),
                record.first_seen.isoformat(),
                now,
            )
            connection.execute(
                """
                INSERT INTO property_candidates (
                  internal_id, source, source_type, external_id, canonical_url,
                  publication_title, publication_date, last_seen, seller_type, broker,
                  listing_status, region, province, commune, original_address,
                  normalized_address, latitude, longitude, location_precision,
                  location_source, location_method, geocoded_at, geocoding_source,
                  geocoding_confidence, asking_price_clp, asking_price_uf, uf_date,
                  uf_rate, uf_rate_date, uf_source, uf_retrieved_at, uf_cache_hit,
                  gross_area_m2, advertised_area_m2, price_uf_m2_gross,
                  estimated_usable_area_m2, price_uf_m2_usable,
                  estimated_net_developable_area_m2, net_developable_ratio,
                  usable_price_uf_m2, estimated_dwelling_capacity,
                  estimated_land_cost_per_dwelling, auction_minimum,
                  auction_guarantee, auction_commission, auction_date, data_quality_score,
                  anomaly_flags_json, created_at, updated_at
                )
                VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(internal_id) DO UPDATE SET
                  source = excluded.source,
                  source_type = excluded.source_type,
                  external_id = excluded.external_id,
                  canonical_url = excluded.canonical_url,
                  publication_title = excluded.publication_title,
                  publication_date = excluded.publication_date,
                  last_seen = excluded.last_seen,
                  region = excluded.region,
                  province = excluded.province,
                  commune = excluded.commune,
                  original_address = excluded.original_address,
                  normalized_address = excluded.normalized_address,
                  latitude = excluded.latitude,
                  longitude = excluded.longitude,
                  location_precision = excluded.location_precision,
                  location_source = excluded.location_source,
                  location_method = excluded.location_method,
                  geocoded_at = excluded.geocoded_at,
                  geocoding_source = excluded.geocoding_source,
                  geocoding_confidence = excluded.geocoding_confidence,
                  asking_price_clp = excluded.asking_price_clp,
                  asking_price_uf = excluded.asking_price_uf,
                  uf_date = excluded.uf_date,
                  uf_rate = excluded.uf_rate,
                  uf_rate_date = excluded.uf_rate_date,
                  uf_source = excluded.uf_source,
                  uf_retrieved_at = excluded.uf_retrieved_at,
                  uf_cache_hit = excluded.uf_cache_hit,
                  gross_area_m2 = excluded.gross_area_m2,
                  advertised_area_m2 = excluded.advertised_area_m2,
                  price_uf_m2_gross = excluded.price_uf_m2_gross,
                  data_quality_score = excluded.data_quality_score,
                  anomaly_flags_json = excluded.anomaly_flags_json,
                  updated_at = excluded.updated_at
                """,
                property_values,
            )

            SourceRecordRepository.from_connection(connection).upsert(internal_id, record)
            DataProvenanceRepository.from_connection(connection).add_many(
                _record_provenance(internal_id, record)
            )
            if record.price_amount is not None:
                PriceHistoryRepository.from_connection(connection).add(internal_id, record)
            if record.preview_image_path or record.image_sha256:
                ImageRepository.from_connection(connection).upsert(internal_id, record)
            return internal_id

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        commune: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        if commune:
            filters.append("commune = ?")
            params.append(commune)
        if source:
            filters.append("source = ?")
            params.append(source)
        where = "WHERE " + " AND ".join(filters) if filters else ""
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM property_candidates
                {where}
                ORDER BY last_seen DESC
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, internal_id: str) -> dict[str, Any] | None:
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM property_candidates WHERE internal_id = ?",
                (internal_id,),
            ).fetchone()
            if row is None:
                return None
            payload = dict(row)
            payload["source_records"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT * FROM property_source_records WHERE internal_id = ?",
                    (internal_id,),
                ).fetchall()
            ]
            payload["images"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT * FROM images WHERE internal_id = ?",
                    (internal_id,),
                ).fetchall()
            ]
            payload["price_history"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT * FROM price_history WHERE internal_id = ? ORDER BY observed_at",
                    (internal_id,),
                ).fetchall()
            ]
            payload["data_provenance"] = [
                dict(item)
                for item in connection.execute(
                    "SELECT * FROM data_provenance WHERE property_id = ? ORDER BY retrieved_at",
                    (internal_id,),
                ).fetchall()
            ]
            payload["location_history"] = [
                _decode_json_columns(dict(item), ("raw_result_json",))
                for item in connection.execute(
                    """
                    SELECT * FROM property_location_history
                    WHERE internal_id = ?
                    ORDER BY created_at DESC, id DESC
                    """,
                    (internal_id,),
                ).fetchall()
            ]
            payload["territorial_criteria"] = [
                _decode_json_columns(dict(item), ("evidence_json",))
                for item in connection.execute(
                    """
                    SELECT * FROM territorial_criteria
                    WHERE internal_id = ?
                    ORDER BY checked_at DESC, criterion_key
                    """,
                    (internal_id,),
                ).fetchall()
            ]
        return payload

    def create_manual(self, payload: dict[str, Any]) -> str:
        now = utc_now().isoformat()
        internal_id = str(payload.get("internal_id") or uuid4())
        title = str(payload.get("title") or "Terreno manual").strip()
        lat = _safe_float(payload.get("latitude"))
        lon = _safe_float(payload.get("longitude"))
        location_precision = "EXACT" if lat is not None and lon is not None else "UNKNOWN"
        location_method = "manual" if lat is not None and lon is not None else None
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO property_candidates (
                  internal_id, source, source_type, external_id, canonical_url,
                  publication_title, publication_date, last_seen, seller_type, broker,
                  listing_status, region, province, commune, original_address,
                  normalized_address, latitude, longitude, location_precision,
                  location_source, location_method, geocoded_at, geocoding_source,
                  geocoding_confidence, asking_price_clp, asking_price_uf,
                  gross_area_m2, advertised_area_m2, data_quality_score,
                  anomaly_flags_json, territorial_status, candidate_status,
                  manual_notes, created_at, updated_at
                )
                VALUES (
                  ?, 'manual', 'manual', ?, ?, ?, NULL, ?, 'unknown', NULL,
                  'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  '[]', 'SIN_INFORMACION_SUFICIENTE', 'ACTIVE', ?, ?, ?
                )
                """,
                (
                    internal_id,
                    payload.get("external_id"),
                    payload.get("url"),
                    title,
                    now,
                    payload.get("region"),
                    payload.get("province"),
                    payload.get("commune"),
                    payload.get("address"),
                    payload.get("address"),
                    lat,
                    lon,
                    location_precision,
                    "manual",
                    location_method,
                    now if location_method else None,
                    "manual" if location_method else None,
                    0.98 if location_method else 0,
                    _num(payload.get("asking_price_clp")),
                    _num(payload.get("asking_price_uf")),
                    _num(payload.get("gross_area_m2")),
                    _num(payload.get("gross_area_m2")),
                    65 if location_method else 45,
                    payload.get("observations"),
                    now,
                    now,
                ),
            )
        if lat is not None and lon is not None:
            self.update_location(
                internal_id,
                latitude=lat,
                longitude=lon,
                location_source="manual",
                location_method="manual",
                location_precision=location_precision,
                location_confidence=0.98,
                address=payload.get("address"),
                region=payload.get("region"),
                commune=payload.get("commune"),
                raw_result={"reason": "manual_property_creation"},
                assigned_by="user",
            )
        return internal_id

    def update_location(
        self,
        internal_id: str,
        *,
        latitude: float,
        longitude: float,
        location_source: str,
        location_method: str,
        location_precision: str,
        location_confidence: float,
        address: str | None = None,
        region: str | None = None,
        commune: str | None = None,
        raw_result: dict[str, Any] | None = None,
        assigned_by: str = "system",
    ) -> dict[str, Any]:
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Coordinates out of range")
        now = utc_now().isoformat()
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT internal_id FROM property_candidates WHERE internal_id = ?",
                (internal_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(internal_id)
            connection.execute(
                """
                UPDATE property_candidates
                SET latitude = ?,
                    longitude = ?,
                    location_source = ?,
                    location_method = ?,
                    location_precision = ?,
                    geocoding_source = ?,
                    geocoding_confidence = ?,
                    geocoded_at = ?,
                    normalized_address = COALESCE(?, normalized_address),
                    region = COALESCE(?, region),
                    commune = COALESCE(?, commune),
                    updated_at = ?
                WHERE internal_id = ?
                """,
                (
                    latitude,
                    longitude,
                    location_source,
                    location_method,
                    location_precision,
                    location_source,
                    location_confidence,
                    now,
                    address,
                    region,
                    commune,
                    now,
                    internal_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO property_location_history (
                  internal_id, latitude, longitude, location_source,
                  location_method, location_precision, location_confidence,
                  address, region, commune, raw_result_json, assigned_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    internal_id,
                    latitude,
                    longitude,
                    location_source,
                    location_method,
                    location_precision,
                    location_confidence,
                    address,
                    region,
                    commune,
                    _json(raw_result or {}),
                    assigned_by,
                    now,
                ),
            )
        updated = self.get(internal_id)
        if updated is None:
            raise KeyError(internal_id)
        return updated

    def update_territorial_status(
        self,
        internal_id: str,
        *,
        status: str,
        summary: dict[str, Any],
        checked_at: datetime | None = None,
    ) -> None:
        now = (checked_at or utc_now()).isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE property_candidates
                SET territorial_status = ?,
                    territorial_checked_at = ?,
                    territorial_summary_json = ?,
                    updated_at = ?
                WHERE internal_id = ?
                """,
                (status, now, _json(summary), now, internal_id),
            )

    def count(self) -> int:
        with connect(self.database.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM property_candidates").fetchone()[0])

    @staticmethod
    def _find_existing(
        connection: sqlite3.Connection,
        record: NormalizedPropertyRecord,
    ) -> str | None:
        if record.external_id:
            row = connection.execute(
                """
                SELECT internal_id FROM property_source_records
                WHERE source = ? AND external_id = ?
                """,
                (record.source_id, record.external_id),
            ).fetchone()
            if row:
                return str(row[0])
        if record.canonical_url:
            row = connection.execute(
                "SELECT internal_id FROM property_candidates WHERE canonical_url = ?",
                (record.canonical_url,),
            ).fetchone()
            if row:
                return str(row[0])
        return None


class SourceRecordRepository:
    def __init__(
        self, database: Database | None = None, connection: sqlite3.Connection | None = None
    ) -> None:
        self.database = database
        self.connection = connection

    @classmethod
    def from_connection(cls, connection: sqlite3.Connection) -> SourceRecordRepository:
        return cls(connection=connection)

    def upsert(self, internal_id: str, record: NormalizedPropertyRecord) -> None:
        connection = self.connection
        if connection is None:
            if self.database is None:
                raise RuntimeError("database or connection required")
            with self.database.transaction() as txn:
                self.connection = txn
                self.upsert(internal_id, record)
                self.connection = None
            return

        source_id = str(record.source_id)
        source_type = str(record.source_type)
        existing_id: int | None = None
        if record.external_id:
            row = connection.execute(
                """
                SELECT id FROM property_source_records
                WHERE source = ? AND external_id = ?
                LIMIT 1
                """,
                (source_id, record.external_id),
            ).fetchone()
            existing_id = int(row[0]) if row else None
        elif record.canonical_url:
            row = connection.execute(
                """
                SELECT id FROM property_source_records
                WHERE internal_id = ? AND source = ? AND canonical_url = ?
                LIMIT 1
                """,
                (internal_id, source_id, record.canonical_url),
            ).fetchone()
            existing_id = int(row[0]) if row else None

        if existing_id is not None:
            connection.execute(
                """
                UPDATE property_source_records
                SET internal_id = ?,
                    source_type = ?,
                    canonical_url = ?,
                    last_seen = ?,
                    parser_version = ?,
                    raw_payload_json = ?
                WHERE id = ?
                """,
                (
                    internal_id,
                    source_type,
                    record.canonical_url,
                    record.last_seen.isoformat(),
                    "0.1.0",
                    _json(record.raw_payload),
                    existing_id,
                ),
            )
            return

        connection.execute(
            """
            INSERT INTO property_source_records (
              internal_id, source, source_type, external_id, canonical_url,
              first_seen, last_seen, parser_version, raw_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                internal_id,
                source_id,
                source_type,
                record.external_id,
                record.canonical_url,
                record.first_seen.isoformat(),
                record.last_seen.isoformat(),
                "0.1.0",
                _json(record.raw_payload),
            ),
        )


class SourceRecordAuditRepository:
    def __init__(
        self, database: Database | None = None, connection: sqlite3.Connection | None = None
    ) -> None:
        self.database = database
        self.connection = connection

    @classmethod
    def from_connection(cls, connection: sqlite3.Connection) -> SourceRecordAuditRepository:
        return cls(connection=connection)

    def upsert_many(self, job_id: str, records: list[dict[str, Any]]) -> list[str]:
        if self.connection is not None:
            return [self.upsert(job_id, record) for record in records]
        if self.database is None:
            raise RuntimeError("database or connection required")
        with self.database.transaction() as txn:
            self.connection = txn
            try:
                return [self.upsert(job_id, record) for record in records]
            finally:
                self.connection = None

    def upsert(self, job_id: str, record: dict[str, Any]) -> str:
        connection = self.connection
        if connection is None:
            if self.database is None:
                raise RuntimeError("database or connection required")
            with self.database.transaction() as txn:
                self.connection = txn
                result = self.upsert(job_id, record)
                self.connection = None
                return result

        now = utc_now().isoformat()
        source_record_id = str(
            record.get("source_record_id")
            or _stable_source_record_id(
                job_id=job_id,
                source=str(record.get("source") or ""),
                external_id=record.get("external_id"),
                raw_payload=record.get("raw_payload"),
            )
        )
        raw_payload = _sanitize_external_payload(record.get("raw_payload") or {})
        connection.execute(
            """
            INSERT INTO source_records (
              source_record_id, job_id, source, source_type, external_id, title,
              description, organization, organization_region, organization_commune,
              organization_address, publication_date, closing_date, status,
              region, commune, property_region, property_commune, property_address,
              amount, currency, amount_raw, amount_type, amount_source,
              amount_confidence, surface_raw, surface_m2, surface_source,
              surface_confidence, source_url, detail_fetched, detail_attempts,
              detail_http_status, fields_extracted_json, fields_missing_json,
              extraction_reasons_json, data_completeness_score, raw_payload_json,
              automatic_classification, automatic_confidence, automatic_score,
              classification_reason, positive_terms_json, negative_terms_json,
              rules_triggered_json, manual_classification, manual_review_status,
              property_id, created_at, updated_at
            )
            VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(source_record_id) DO UPDATE SET
              job_id = excluded.job_id,
              source = excluded.source,
              source_type = excluded.source_type,
              external_id = excluded.external_id,
              title = excluded.title,
              description = excluded.description,
              organization = excluded.organization,
              organization_region = excluded.organization_region,
              organization_commune = excluded.organization_commune,
              organization_address = excluded.organization_address,
              publication_date = excluded.publication_date,
              closing_date = excluded.closing_date,
              status = excluded.status,
              region = excluded.region,
              commune = excluded.commune,
              property_region = excluded.property_region,
              property_commune = excluded.property_commune,
              property_address = excluded.property_address,
              amount = excluded.amount,
              currency = excluded.currency,
              amount_raw = excluded.amount_raw,
              amount_type = excluded.amount_type,
              amount_source = excluded.amount_source,
              amount_confidence = excluded.amount_confidence,
              surface_raw = excluded.surface_raw,
              surface_m2 = excluded.surface_m2,
              surface_source = excluded.surface_source,
              surface_confidence = excluded.surface_confidence,
              source_url = excluded.source_url,
              detail_fetched = excluded.detail_fetched,
              detail_attempts = excluded.detail_attempts,
              detail_http_status = excluded.detail_http_status,
              fields_extracted_json = excluded.fields_extracted_json,
              fields_missing_json = excluded.fields_missing_json,
              extraction_reasons_json = excluded.extraction_reasons_json,
              data_completeness_score = excluded.data_completeness_score,
              raw_payload_json = excluded.raw_payload_json,
              automatic_classification = excluded.automatic_classification,
              automatic_confidence = excluded.automatic_confidence,
              automatic_score = excluded.automatic_score,
              classification_reason = excluded.classification_reason,
              positive_terms_json = excluded.positive_terms_json,
              negative_terms_json = excluded.negative_terms_json,
              rules_triggered_json = excluded.rules_triggered_json,
              updated_at = excluded.updated_at
            """,
            (
                source_record_id,
                job_id,
                str(record.get("source") or ""),
                str(record.get("source_type") or ""),
                record.get("external_id"),
                record.get("title"),
                record.get("description"),
                record.get("organization"),
                record.get("organization_region"),
                record.get("organization_commune"),
                record.get("organization_address"),
                record.get("publication_date"),
                record.get("closing_date"),
                record.get("status"),
                record.get("region"),
                record.get("commune"),
                record.get("property_region"),
                record.get("property_commune"),
                record.get("property_address"),
                _num(record.get("amount")),
                record.get("currency"),
                record.get("amount_raw"),
                record.get("amount_type"),
                record.get("amount_source"),
                float(record.get("amount_confidence") or 0),
                record.get("surface_raw"),
                _num(record.get("surface_m2")),
                record.get("surface_source"),
                float(record.get("surface_confidence") or 0),
                _sanitize_secret_text(record.get("source_url")),
                1 if record.get("detail_fetched") else 0,
                int(record.get("detail_attempts") or 0),
                record.get("detail_http_status"),
                _json(record.get("fields_extracted") or []),
                _json(record.get("fields_missing") or []),
                _json(record.get("extraction_reasons") or {}),
                int(record.get("data_completeness_score") or 0),
                _json(raw_payload),
                str(record.get("automatic_classification") or "UNKNOWN"),
                float(record.get("automatic_confidence") or 0),
                int(record.get("automatic_score") or 0),
                record.get("classification_reason"),
                _json(record.get("positive_terms") or []),
                _json(record.get("negative_terms") or []),
                _json(record.get("rules_triggered") or []),
                str(record.get("manual_classification") or ManualClassification.UNREVIEWED),
                str(record.get("manual_review_status") or "UNREVIEWED"),
                record.get("property_id"),
                now,
                now,
            ),
        )
        return source_record_id

    def list(
        self,
        *,
        job_id: str | None = None,
        bucket: str | None = None,
        classification: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = self._filters(
            job_id=job_id,
            bucket=bucket,
            classification=classification,
            q=q,
        )
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM source_records
                {where}
                ORDER BY updated_at DESC, source_record_id
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return [_decode_source_record(dict(row)) for row in rows]

    def count(
        self,
        *,
        job_id: str | None = None,
        bucket: str | None = None,
        classification: str | None = None,
        q: str | None = None,
    ) -> int:
        where, params = self._filters(
            job_id=job_id,
            bucket=bucket,
            classification=classification,
            q=q,
        )
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                f"SELECT COUNT(*) FROM source_records {where}",
                params,
            ).fetchone()
        return int(row[0])

    def get(self, source_record_id: str) -> dict[str, Any] | None:
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM source_records WHERE source_record_id = ?",
                (source_record_id,),
            ).fetchone()
        return _decode_source_record(dict(row)) if row else None

    def distribution(self, job_id: str | None = None) -> dict[str, Any]:
        where = "WHERE job_id = ?" if job_id else ""
        params = (job_id,) if job_id else ()
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT automatic_classification, COUNT(*) AS count
                FROM source_records
                {where}
                GROUP BY automatic_classification
                """,
                params,
            ).fetchall()
            manual_reviewed = connection.execute(
                f"""
                SELECT COUNT(*) FROM source_records
                {where}{" AND" if where else "WHERE"} manual_review_status = 'REVIEWED'
                """,
                params,
            ).fetchone()[0]

        counts = {str(row["automatic_classification"]): int(row["count"]) for row in rows}
        total = sum(counts.values())
        accepted = sum(counts.get(item, 0) for item in ("LAND_ACQUISITION", "LAND_SALE"))
        possible = sum(counts.get(item, 0) for item in ("REAL_ESTATE", "POSSIBLE_LAND", "UNKNOWN"))
        rejected = counts.get("FALSE_POSITIVE", 0)
        return {
            "total_analyzed": total,
            "distribution": counts,
            "accepted": accepted,
            "possible": possible,
            "rejected": rejected,
            "manual_reviewed": int(manual_reviewed),
        }

    def update_manual_classification(
        self,
        source_record_id: str,
        manual_classification: ManualClassification,
    ) -> dict[str, Any]:
        existing = self.get(source_record_id)
        if existing is None:
            raise KeyError(source_record_id)
        now = utc_now().isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE source_records
                SET manual_classification = ?,
                    manual_review_status = 'REVIEWED',
                    updated_at = ?
                WHERE source_record_id = ?
                """,
                (manual_classification.value, now, source_record_id),
            )
            connection.execute(
                """
                INSERT INTO classifier_feedback (
                  source_record_id, job_id, automatic_classification,
                  automatic_confidence, automatic_score, manual_classification,
                  positive_terms_json, negative_terms_json, classification_reason,
                  reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_record_id,
                    existing["job_id"],
                    existing["automatic_classification"],
                    existing["automatic_confidence"],
                    existing["automatic_score"],
                    manual_classification.value,
                    _json(existing.get("positive_terms") or []),
                    _json(existing.get("negative_terms") or []),
                    existing.get("classification_reason"),
                    now,
                ),
            )
        updated = self.get(source_record_id)
        if updated is None:
            raise KeyError(source_record_id)
        return updated

    def link_property(
        self,
        *,
        job_id: str,
        source: str,
        external_id: str | None,
        property_id: str,
    ) -> None:
        if not external_id:
            return
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE source_records
                SET property_id = ?, updated_at = ?
                WHERE job_id = ? AND source = ? AND external_id = ?
                """,
                (property_id, utc_now().isoformat(), job_id, source, external_id),
            )

    @staticmethod
    def _filters(
        *,
        job_id: str | None,
        bucket: str | None,
        classification: str | None,
        q: str | None,
    ) -> tuple[str, list[Any]]:
        filters = []
        params: list[Any] = []
        if job_id:
            filters.append("job_id = ?")
            params.append(job_id)
        if classification:
            filters.append("automatic_classification = ?")
            params.append(classification)
        if bucket:
            classifications = _bucket_classifications(bucket)
            if classifications:
                filters.append(
                    "automatic_classification IN (" + ", ".join("?" for _ in classifications) + ")"
                )
                params.extend(classifications)
        if q:
            like = f"%{q}%"
            filters.append(
                """
                (
                  title LIKE ?
                  OR description LIKE ?
                  OR organization LIKE ?
                  OR organization_commune LIKE ?
                  OR property_commune LIKE ?
                  OR automatic_classification LIKE ?
                  OR positive_terms_json LIKE ?
                  OR negative_terms_json LIKE ?
                )
                """
            )
            params.extend([like, like, like, like, like, like, like, like])
        return ("WHERE " + " AND ".join(filters) if filters else ""), params


class DataProvenanceRepository:
    def __init__(
        self, database: Database | None = None, connection: sqlite3.Connection | None = None
    ) -> None:
        self.database = database
        self.connection = connection

    @classmethod
    def from_connection(cls, connection: sqlite3.Connection) -> DataProvenanceRepository:
        return cls(connection=connection)

    def add_many(self, records: list[DataProvenance]) -> None:
        for record in records:
            self.upsert(record)

    def upsert(self, record: DataProvenance) -> None:
        connection = self.connection
        if connection is None:
            if self.database is None:
                raise RuntimeError("database or connection required")
            with self.database.transaction() as txn:
                self.connection = txn
                self.upsert(record)
                self.connection = None
            return
        connection.execute(
            """
            INSERT INTO data_provenance (
              property_id, field_name, value, source_id, source_type, method,
              retrieved_at, confidence, source_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(property_id, field_name, source_id, method)
            DO UPDATE SET
              value = excluded.value,
              source_type = excluded.source_type,
              retrieved_at = excluded.retrieved_at,
              confidence = excluded.confidence,
              source_url = excluded.source_url
            """,
            (
                record.property_id,
                record.field_name,
                _json(record.value),
                record.source_id,
                record.source_type,
                str(record.method) if record.method else "",
                record.retrieved_at.isoformat(),
                record.confidence,
                str(record.source_url) if record.source_url else None,
            ),
        )

    def list_for_property(self, property_id: str) -> list[dict[str, Any]]:
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM data_provenance
                WHERE property_id = ?
                ORDER BY retrieved_at DESC, id DESC
                """,
                (property_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class ImageRepository:
    def __init__(
        self, database: Database | None = None, connection: sqlite3.Connection | None = None
    ) -> None:
        self.database = database
        self.connection = connection

    @classmethod
    def from_connection(cls, connection: sqlite3.Connection) -> ImageRepository:
        return cls(connection=connection)

    def upsert(self, internal_id: str, record: NormalizedPropertyRecord) -> None:
        connection = self.connection
        if connection is None:
            if self.database is None:
                raise RuntimeError("database or connection required")
            with self.database.transaction() as txn:
                self.connection = txn
                self.upsert(internal_id, record)
                self.connection = None
            return
        source_url = record.image_urls[0] if record.image_urls else None
        row = None
        if record.image_sha256:
            row = connection.execute(
                "SELECT image_id FROM images WHERE internal_id = ? AND sha256 = ? LIMIT 1",
                (internal_id, record.image_sha256),
            ).fetchone()
        if row is None and source_url:
            row = connection.execute(
                "SELECT image_id FROM images WHERE internal_id = ? AND source_url = ? LIMIT 1",
                (internal_id, source_url),
            ).fetchone()

        image_id = str(row[0]) if row else str(uuid4())
        sql = (
            """
            UPDATE images
            SET source_url = ?,
                preview_path = ?,
                sha256 = ?,
                perceptual_hash = ?,
                mime_type = ?,
                retrieved_at = ?,
                allowed_to_download = ?
            WHERE image_id = ?
            """
            if row
            else """
            INSERT INTO images (
              source_url, preview_path, sha256, perceptual_hash, mime_type,
              retrieved_at, allowed_to_download, image_id, internal_id, original_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """
        )
        params = (
            source_url,
            record.preview_image_path,
            record.image_sha256,
            record.image_phash,
            "image/jpeg" if record.preview_image_path else None,
            utc_now().isoformat(),
            1 if record.preview_image_path else None,
            image_id,
        )
        if row:
            connection.execute(sql, params)
        else:
            connection.execute(sql, (*params, internal_id))


class PriceHistoryRepository:
    def __init__(
        self, database: Database | None = None, connection: sqlite3.Connection | None = None
    ) -> None:
        self.database = database
        self.connection = connection

    @classmethod
    def from_connection(cls, connection: sqlite3.Connection) -> PriceHistoryRepository:
        return cls(connection=connection)

    def add(self, internal_id: str, record: NormalizedPropertyRecord) -> None:
        connection = self.connection
        if connection is None:
            if self.database is None:
                raise RuntimeError("database or connection required")
            with self.database.transaction() as txn:
                self.connection = txn
                self.add(internal_id, record)
                self.connection = None
            return
        connection.execute(
            """
            INSERT INTO price_history (
              internal_id, observed_at, asking_price_clp, asking_price_uf,
              uf_date, source, evidence_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                internal_id,
                record.last_seen.isoformat(),
                _num(record.price_clp),
                _num(record.price_uf),
                record.uf_date.isoformat() if record.uf_date else None,
                str(record.source_id),
                record.canonical_url,
            ),
        )


class CanonicalRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_matches(self, matches: list[CanonicalPropertyMatch]) -> None:
        with self.database.transaction() as connection:
            for match in matches:
                connection.execute(
                    """
                    INSERT INTO canonical_properties (
                      canonical_id, primary_internal_id, source_count,
                      duplicate_confidence, created_at, updated_at
                    )
                    VALUES (?, ?, 1, ?, ?, ?)
                    ON CONFLICT(canonical_id) DO UPDATE SET
                      duplicate_confidence = MAX(
                        duplicate_confidence,
                        excluded.duplicate_confidence
                      ),
                      updated_at = excluded.updated_at
                    """,
                    (
                        match.canonical_id,
                        match.internal_id,
                        match.match_score,
                        utc_now().isoformat(),
                        utc_now().isoformat(),
                    ),
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO canonical_property_sources (
                      canonical_id, internal_id, match_reason_json, match_score
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        match.canonical_id,
                        match.internal_id,
                        _json(
                            match.match_reason
                            + (["POSSIBLE_DUPLICATE"] if match.possible_duplicate else [])
                        ),
                        match.match_score,
                    ),
                )


class EvidenceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(self, internal_id: str, record: EvidenceRecord) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO evidence_records (
                  internal_id, property_id, category, field, value, source_name,
                  source_url, layer_name, source_record_id, raw_metadata,
                  raw_value, normalized_value, source, url, retrieved_at, method,
                  parser_version, rule_version, confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    internal_id,
                    record.property_id or internal_id,
                    record.category,
                    record.field,
                    _json(record.value),
                    record.source_name,
                    str(record.source_url) if record.source_url else None,
                    record.layer_name,
                    record.source_record_id,
                    _json(record.raw_metadata),
                    _json(record.raw_value),
                    _json(record.normalized_value),
                    record.source,
                    str(record.url) if record.url else None,
                    record.retrieved_at.isoformat(),
                    str(record.method) if record.method else None,
                    record.parser_version,
                    record.rule_version,
                    record.confidence,
                ),
            )
            return int(cursor.lastrowid)

    def add_many(self, internal_id: str, records: list[EvidenceRecord]) -> list[int]:
        return [self.add(internal_id, record) for record in records]

    def list_for_property(self, internal_id: str) -> list[dict[str, Any]]:
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_records
                WHERE internal_id = ? OR property_id = ?
                ORDER BY retrieved_at DESC, id DESC
                """,
                (internal_id, internal_id),
            ).fetchall()
        return [dict(row) for row in rows]


class GeometryMetricsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(self, internal_id: str, metrics: GeometryMetrics) -> None:
        parcel_geometry_json = _json(metrics.parcel_geometry)
        polygon_geojson_json = _json(metrics.polygon_geojson)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO geometry_metrics (
                  internal_id, geometry_status, geometry_type, geometry_source,
                  geometry_retrieved_at, geometry_confidence, parcel_geometry,
                  polygon_geojson, official_area_m2, area_difference_percent,
                  geometric_area_m2, perimeter_m, estimated_width_m,
                  estimated_depth_m, width_depth_ratio, verified_street_frontage_m,
                  estimated_main_frontage_m, secondary_frontages_json,
                  approximate_depth_m, frontage_depth_ratio, public_road_frontage_count,
                  compactness_index, elongation, irregularity_index, orientation_degrees,
                  bounding_box_json, centroid_latitude, centroid_longitude,
                  shape_quality_score, shape_warnings_json
                )
                VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(internal_id) DO UPDATE SET
                  geometry_status = excluded.geometry_status,
                  geometry_type = excluded.geometry_type,
                  geometry_source = excluded.geometry_source,
                  geometry_retrieved_at = excluded.geometry_retrieved_at,
                  geometry_confidence = excluded.geometry_confidence,
                  parcel_geometry = excluded.parcel_geometry,
                  polygon_geojson = excluded.polygon_geojson,
                  official_area_m2 = excluded.official_area_m2,
                  area_difference_percent = excluded.area_difference_percent,
                  geometric_area_m2 = excluded.geometric_area_m2,
                  perimeter_m = excluded.perimeter_m,
                  estimated_width_m = excluded.estimated_width_m,
                  estimated_depth_m = excluded.estimated_depth_m,
                  width_depth_ratio = excluded.width_depth_ratio,
                  verified_street_frontage_m = excluded.verified_street_frontage_m,
                  estimated_main_frontage_m = excluded.estimated_main_frontage_m,
                  secondary_frontages_json = excluded.secondary_frontages_json,
                  approximate_depth_m = excluded.approximate_depth_m,
                  frontage_depth_ratio = excluded.frontage_depth_ratio,
                  public_road_frontage_count = excluded.public_road_frontage_count,
                  compactness_index = excluded.compactness_index,
                  elongation = excluded.elongation,
                  irregularity_index = excluded.irregularity_index,
                  orientation_degrees = excluded.orientation_degrees,
                  bounding_box_json = excluded.bounding_box_json,
                  centroid_latitude = excluded.centroid_latitude,
                  centroid_longitude = excluded.centroid_longitude,
                  shape_quality_score = excluded.shape_quality_score,
                  shape_warnings_json = excluded.shape_warnings_json
                """,
                (
                    internal_id,
                    str(metrics.geometry_status),
                    str(metrics.geometry_type),
                    metrics.geometry_source,
                    metrics.geometry_retrieved_at.isoformat()
                    if metrics.geometry_retrieved_at
                    else None,
                    metrics.geometry_confidence,
                    parcel_geometry_json,
                    polygon_geojson_json,
                    metrics.official_area_m2,
                    metrics.area_difference_percent,
                    metrics.geometric_area_m2,
                    metrics.perimeter_m,
                    metrics.estimated_width_m,
                    metrics.estimated_depth_m,
                    metrics.width_depth_ratio,
                    metrics.verified_street_frontage_m,
                    metrics.estimated_main_frontage_m,
                    _json(metrics.secondary_frontages_m),
                    metrics.approximate_depth_m,
                    metrics.frontage_depth_ratio,
                    metrics.public_road_frontage_count,
                    metrics.compactness_index,
                    metrics.elongation,
                    metrics.irregularity_index,
                    metrics.orientation_degrees,
                    _json(metrics.bounding_box),
                    metrics.centroid_latitude,
                    metrics.centroid_longitude,
                    metrics.shape_quality_score,
                    _json(metrics.shape_warnings),
                ),
            )
            connection.execute(
                """
                UPDATE property_candidates
                SET geometry_status = ?,
                    geometry_source = ?,
                    geometry_type = ?,
                    parcel_geometry = ?,
                    geometry_area_m2 = ?,
                    geometry_perimeter_m = ?,
                    official_area_m2 = ?,
                    area_difference_percent = ?,
                    updated_at = ?
                WHERE internal_id = ?
                """,
                (
                    str(metrics.geometry_status),
                    metrics.geometry_source,
                    str(metrics.geometry_type),
                    parcel_geometry_json,
                    metrics.geometric_area_m2,
                    metrics.perimeter_m,
                    metrics.official_area_m2,
                    metrics.area_difference_percent,
                    utc_now().isoformat(),
                    internal_id,
                ),
            )

    def get(self, internal_id: str) -> dict[str, Any] | None:
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM geometry_metrics WHERE internal_id = ?",
                (internal_id,),
            ).fetchone()
        return dict(row) if row else None


class GeospatialCacheRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                """
                SELECT response_json FROM geospatial_cache
                WHERE cache_key = ? AND expires_at > ?
                """,
                (cache_key, utc_now().isoformat()),
            ).fetchone()
        return json.loads(row["response_json"]) if row else None

    def set(
        self,
        *,
        cache_key: str,
        service_url: str,
        layer_id: str,
        geometry_hash: str,
        query_hash: str,
        spatial_reference: str,
        response: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        now = utc_now().isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO geospatial_cache (
                  cache_key, service_url, layer_id, geometry_hash, query_hash,
                  spatial_reference, response_json, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                  response_json = excluded.response_json,
                  created_at = excluded.created_at,
                  expires_at = excluded.expires_at
                """,
                (
                    cache_key,
                    service_url,
                    layer_id,
                    geometry_hash,
                    query_hash,
                    spatial_reference,
                    _json(response),
                    now,
                    expires_at.isoformat(),
                ),
            )


class GeocodingCacheRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM geocoding_cache
                WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > ?)
                """,
                (cache_key, utc_now().isoformat()),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE geocoding_cache SET last_used_at = ? WHERE cache_key = ?",
                (utc_now().isoformat(), cache_key),
            )
        return _decode_json_columns(dict(row), ("request_json", "response_json"))

    def set(
        self,
        *,
        cache_key: str,
        provider: str,
        query_text: str,
        normalized_query: str,
        request: dict[str, Any],
        response: dict[str, Any],
        latitude: float | None,
        longitude: float | None,
        display_name: str | None,
        location_precision: str,
        location_method: str,
        confidence: float,
        source_url: str | None,
        expires_at: datetime | None = None,
    ) -> None:
        now = utc_now().isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO geocoding_cache (
                  cache_key, provider, query_text, normalized_query, request_json,
                  response_json, latitude, longitude, display_name,
                  location_precision, location_method, confidence, source_url,
                  created_at, last_used_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                  response_json = excluded.response_json,
                  latitude = excluded.latitude,
                  longitude = excluded.longitude,
                  display_name = excluded.display_name,
                  location_precision = excluded.location_precision,
                  location_method = excluded.location_method,
                  confidence = excluded.confidence,
                  source_url = excluded.source_url,
                  last_used_at = excluded.last_used_at,
                  expires_at = excluded.expires_at
                """,
                (
                    cache_key,
                    provider,
                    query_text,
                    normalized_query,
                    _json(request),
                    _json(response),
                    latitude,
                    longitude,
                    display_name,
                    location_precision,
                    location_method,
                    confidence,
                    source_url,
                    now,
                    now,
                    expires_at.isoformat() if expires_at else None,
                ),
            )


class MinvuLayerRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert_many(self, rows: list[dict[str, Any]]) -> None:
        with self.database.transaction() as connection:
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO minvu_layers (
                      provider, service_name, layer_name, layer_id, endpoint,
                      geometry_type, spatial_reference, fields_json, status,
                      last_checked, raw_metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(provider, endpoint, layer_id) DO UPDATE SET
                      service_name = excluded.service_name,
                      layer_name = excluded.layer_name,
                      geometry_type = excluded.geometry_type,
                      spatial_reference = excluded.spatial_reference,
                      fields_json = excluded.fields_json,
                      status = excluded.status,
                      last_checked = excluded.last_checked,
                      raw_metadata_json = excluded.raw_metadata_json
                    """,
                    (
                        row.get("provider") or "IDE MINVU",
                        row.get("service_name") or "",
                        row.get("layer_name") or "",
                        int(row.get("layer_id") or 0),
                        row.get("endpoint") or row.get("service_url") or "",
                        row.get("geometry_type"),
                        _json(row.get("spatial_reference") or {}),
                        _json(row.get("fields") or []),
                        row.get("status") or "UNKNOWN",
                        row.get("last_checked") or utc_now().isoformat(),
                        _json(row),
                    ),
                )

    def list(self, *, limit: int = 500) -> list[dict[str, Any]]:
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM minvu_layers
                ORDER BY last_checked DESC, service_name, layer_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            _decode_json_columns(
                dict(row), ("spatial_reference", "fields_json", "raw_metadata_json")
            )
            for row in rows
        ]


class TerritorialCriteriaRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def replace_for_property(self, internal_id: str, rows: list[dict[str, Any]]) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM territorial_criteria WHERE internal_id = ?",
                (internal_id,),
            )
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO territorial_criteria (
                      internal_id, criterion_key, criterion_label, result, value,
                      source, endpoint, layer_name, checked_at, evidence_json,
                      confidence, observation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        internal_id,
                        row["criterion_key"],
                        row["criterion_label"],
                        row["result"],
                        _json(row.get("value")),
                        row.get("source"),
                        row.get("endpoint"),
                        row.get("layer_name"),
                        row.get("checked_at") or utc_now().isoformat(),
                        _json(row.get("evidence") or {}),
                        float(row.get("confidence") or 0),
                        row.get("observation"),
                    ),
                )

    def list_for_property(self, internal_id: str) -> list[dict[str, Any]]:
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM territorial_criteria
                WHERE internal_id = ?
                ORDER BY checked_at DESC, criterion_key
                """,
                (internal_id,),
            ).fetchall()
        return [_decode_json_columns(dict(row), ("evidence_json",)) for row in rows]


class SourceRunStatusRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(
        self,
        *,
        job_id: str,
        source_id: str,
        source_type: str,
        enabled: bool,
        configured: bool,
        attempted: bool,
        status: str,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        records_received: int = 0,
        records_accepted: int = 0,
        records_rejected: int = 0,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        queries: list[str] | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO source_run_status (
                  job_id, source_id, source_type, enabled, configured, attempted,
                  status, started_at, finished_at, records_received,
                  records_accepted, records_rejected, warnings, errors, queries_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, source_id) DO UPDATE SET
                  source_type = excluded.source_type,
                  enabled = excluded.enabled,
                  configured = excluded.configured,
                  attempted = excluded.attempted,
                  status = excluded.status,
                  started_at = COALESCE(source_run_status.started_at, excluded.started_at),
                  finished_at = excluded.finished_at,
                  records_received = excluded.records_received,
                  records_accepted = excluded.records_accepted,
                  records_rejected = excluded.records_rejected,
                  warnings = excluded.warnings,
                  errors = excluded.errors,
                  queries_json = excluded.queries_json
                """,
                (
                    job_id,
                    source_id,
                    source_type,
                    1 if enabled else 0,
                    1 if configured else 0,
                    1 if attempted else 0,
                    status,
                    started_at.isoformat() if started_at else None,
                    finished_at.isoformat() if finished_at else None,
                    records_received,
                    records_accepted,
                    records_rejected,
                    _json(warnings or []),
                    _json(errors or []),
                    _json(queries or []),
                ),
            )

    def list_for_job(self, job_id: str) -> list[dict[str, Any]]:
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM source_run_status
                WHERE job_id = ?
                ORDER BY source_type, source_id
                """,
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_latest(self) -> list[dict[str, Any]]:
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                """
                SELECT job_id FROM source_run_status
                ORDER BY COALESCE(finished_at, started_at) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return []
        return self.list_for_job(str(row["job_id"]))


class ScrapingRunRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, run_id: str, filters: dict[str, Any], sources: list[str]) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO scraping_runs(
                  run_id, status, filters_json, sources_json, created_at
                )
                VALUES (?, 'QUEUED', ?, ?, ?)
                """,
                (run_id, _json(filters), _json(sources), utc_now().isoformat()),
            )

    def update(
        self,
        run_id: str,
        *,
        status: str,
        found_count: int | None = None,
        processed_count: int | None = None,
        discarded_count: int | None = None,
        finished: bool = False,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE scraping_runs
                SET status = ?,
                    found_count = COALESCE(?, found_count),
                    processed_count = COALESCE(?, processed_count),
                    discarded_count = COALESCE(?, discarded_count),
                    started_at = COALESCE(started_at, ?),
                    finished_at = CASE WHEN ? THEN ? ELSE finished_at END
                WHERE run_id = ?
                """,
                (
                    status,
                    found_count,
                    processed_count,
                    discarded_count,
                    utc_now().isoformat(),
                    1 if finished else 0,
                    utc_now().isoformat(),
                    run_id,
                ),
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with connect(self.database.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM scraping_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None


class ScrapingErrorRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(
        self,
        *,
        run_id: str | None,
        source_id: str | None,
        stage: str | None,
        property_id: str | None,
        message: str,
        exception: str | None = None,
    ) -> None:
        safe_message = _sanitize_secret_text(message) or ""
        safe_exception = _sanitize_secret_text(exception)
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO scraping_errors(
                  run_id, source_id, stage, property_id, message, exception, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    source_id,
                    stage,
                    property_id,
                    safe_message,
                    safe_exception,
                    utc_now().isoformat(),
                ),
            )

    def list_recent(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.database.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM scraping_errors ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def _stable_source_record_id(
    *,
    job_id: str,
    source: str,
    external_id: Any,
    raw_payload: Any,
) -> str:
    if external_id not in (None, ""):
        seed = f"{job_id}:{source}:{external_id}"
    else:
        seed = f"{job_id}:{source}:{_json(raw_payload)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"sr_{digest}"


def _sanitize_external_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_external_payload(item)
            for key, item in value.items()
            if str(key).lower() not in {"ticket", "apikey", "access_token", "refresh_token"}
        }
    if isinstance(value, list):
        return [_sanitize_external_payload(item) for item in value]
    if isinstance(value, str):
        return _sanitize_secret_text(value)
    return value


def _sanitize_secret_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
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


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decode_json_columns(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    for column in columns:
        public_key = column.removesuffix("_json")
        row[public_key] = _decode_json(row.get(column), default={})
    return row


def _decode_source_record(row: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "positive_terms_json",
        "negative_terms_json",
        "rules_triggered_json",
        "fields_extracted_json",
        "fields_missing_json",
    ):
        public_key = key.removesuffix("_json")
        row[public_key] = _decode_json(row.get(key), default=[])
    row["extraction_reasons"] = _decode_json(row.get("extraction_reasons_json"), default={})
    row["raw_payload"] = _decode_json(row.get("raw_payload_json"), default={})
    return row


def _decode_json(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def _bucket_classifications(bucket: str) -> list[str]:
    normalized = bucket.lower()
    if normalized in {"candidates", "candidate", "accepted", "candidatos"}:
        return ["LAND_ACQUISITION", "LAND_SALE"]
    if normalized in {"possible", "posibles"}:
        return ["REAL_ESTATE", "POSSIBLE_LAND", "UNKNOWN"]
    if normalized in {"rejected", "descartados"}:
        return ["FALSE_POSITIVE"]
    return []


def _record_provenance(
    internal_id: str,
    record: NormalizedPropertyRecord,
) -> list[DataProvenance]:
    source_confidence = max(0.2, min(1.0, record.data_quality_score / 100))
    source_method: ConnectorStrategy | str = (
        ConnectorStrategy.OFFICIAL_API
        if record.source_id in {"mercado_publico", "mercadolibre_real_estate"}
        else "source_record"
    )
    rows: list[DataProvenance] = []

    def add_source(field: str, value: Any, *, confidence: float = source_confidence) -> None:
        if value in (None, ""):
            return
        rows.append(
            DataProvenance(
                property_id=internal_id,
                field_name=field,
                value=value,
                source_id=record.source_id,
                source_type=SourceRole.SEARCH.value,
                method=source_method,
                retrieved_at=record.last_seen,
                confidence=confidence,
                source_url=record.canonical_url,
            )
        )

    add_source("publication_title", record.title)
    add_source("gross_area_m2", record.gross_area_m2)
    add_source("region", record.region)
    add_source("commune", record.commune)
    add_source("normalized_address", record.address)
    add_source("latitude", record.latitude, confidence=0.45)
    add_source("longitude", record.longitude, confidence=0.45)
    add_source("location_precision", record.location_precision, confidence=0.7)
    if record.price_currency == "CLP":
        add_source("asking_price_clp", record.price_amount)
    elif record.price_currency == "UF":
        add_source("asking_price_uf", record.price_amount)
        add_source("price_uf_m2_gross", record.price_uf_m2)
    elif record.price_clp is not None:
        add_source("asking_price_clp", record.price_clp)
    elif record.price_uf is not None:
        add_source("asking_price_uf", record.price_uf)

    if record.uf_rate is None:
        return rows

    cmf_fields = {
        "uf_rate": record.uf_rate,
        "uf_rate_date": record.uf_rate_date,
        "uf_source": record.uf_source,
        "uf_retrieved_at": record.uf_retrieved_at,
        "uf_cache_hit": record.uf_cache_hit,
    }
    if record.price_currency == "CLP":
        cmf_fields["asking_price_uf"] = record.price_uf
        cmf_fields["price_uf_m2_gross"] = record.price_uf_m2
    elif record.price_currency == "UF":
        cmf_fields["asking_price_clp"] = record.price_clp
        cmf_fields["price_uf_m2_gross"] = record.price_uf_m2

    for field, value in cmf_fields.items():
        if value in (None, ""):
            continue
        rows.append(
            DataProvenance(
                property_id=internal_id,
                field_name=field,
                value=value,
                source_id="cmf_uf",
                source_type=SourceRole.ENRICHMENT.value,
                method=ConnectorStrategy.OFFICIAL_API,
                retrieved_at=record.uf_retrieved_at or record.last_seen,
                confidence=0.95,
                source_url="https://api.cmfchile.cl/api-sbifv3/recursos_api/uf",
            )
        )
    return rows
