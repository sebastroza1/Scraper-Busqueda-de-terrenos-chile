from __future__ import annotations

from typing import Any

from .config import source_config
from .runtime_sources import runtime_source_record


def source_capability(source_id: str, official_sources: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    record = runtime_source_record(source_id, official_sources)
    cfg = source_config(record)
    kind = record.get("kind")
    configured = kind != "unconfigured" and int(cfg.get("timeout") or 0) > 0
    return {
        "source_id": source_id,
        "configured": configured,
        "provider": record.get("provider") or source_id,
        "kind": kind,
        "timeout": int(cfg.get("timeout") or 0),
        "cache_ttl_seconds": int(cfg.get("cache_ttl_seconds") or 0),
    }


def build_source_capabilities(
    source_ids: list[str],
    official_sources: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    return {source_id: source_capability(source_id, official_sources) for source_id in dict.fromkeys(source_ids)}
