from __future__ import annotations
import json
import sqlite3
from typing import Dict, Any, List
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    provider TEXT,
    name TEXT,
    category TEXT,
    priority TEXT,
    kind TEXT,
    audit_status TEXT,
    runtime_policy TEXT,
    legal_gate TEXT,
    technical_status TEXT,
    http_status INTEGER,
    latency_ms INTEGER,
    content_type TEXT,
    service_name TEXT,
    resource_count INTEGER,
    sample_resource TEXT,
    feature_count INTEGER,
    schema_hash TEXT,
    discovered_links_json TEXT,
    error_type TEXT,
    error TEXT,
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_health_source_time
ON health_checks(source_id, checked_at);
"""

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(health_checks)").fetchall()}
        if "error_type" not in cols:
            conn.execute("ALTER TABLE health_checks ADD COLUMN error_type TEXT")
        conn.commit()

def save_result(r: Dict[str, Any]):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO health_checks (
                source_id, provider, name, category, priority, kind,
                audit_status, runtime_policy, legal_gate, technical_status,
                http_status, latency_ms, content_type, service_name,
                resource_count, sample_resource, feature_count, schema_hash,
                discovered_links_json, error_type, error, checked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r.get("source_id"), r.get("provider"), r.get("name"),
                r.get("category"), r.get("priority"), r.get("kind"),
                r.get("audit_status"), r.get("runtime_policy"), r.get("legal_gate"),
                r.get("technical_status"), r.get("http_status"), r.get("latency_ms"),
                r.get("content_type"), r.get("service_name"), r.get("resource_count"),
                r.get("sample_resource"), r.get("feature_count"), r.get("schema_hash"),
                json.dumps(r.get("discovered_links") or [], ensure_ascii=False),
                r.get("error_type"), r.get("error"), r.get("checked_at"),
            )
        )
        conn.commit()

def load_history(limit=2500) -> List[Dict[str, Any]]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM health_checks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["discovered_links"] = json.loads(item.pop("discovered_links_json") or "[]")
        except Exception:
            item["discovered_links"] = []
        out.append(item)
    return out
