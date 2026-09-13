from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlparse


_ACTIVE: dict[str, Any] | None = None
_CURRENT_SOURCE_ID: ContextVar[str | None] = ContextVar("landfinder_current_source_id", default=None)


def provider_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "overpass" in host:
        return "overpass"
    if "geoide.minvu" in host:
        return "minvu"
    if "rest-sit.mop" in host:
        return "mop"
    if "seia" in host or "sea.gob" in host:
        return "seia"
    if "mma.gob" in host:
        return "mma"
    return host or "unknown"


def start_run(run_id: str, area_ids: list[str], source_ids: list[str]) -> None:
    global _ACTIVE
    _ACTIVE = {
        "run_id": run_id,
        "area_ids": list(area_ids),
        "source_ids": list(source_ids),
        "started_at": time.time(),
        "finished_at": None,
        "request_count": 0,
        "request_count_per_provider": {},
        "request_count_per_source": {},
        "cache_hits": 0,
        "cache_misses": 0,
        "deduplicated_requests": 0,
        "total_network_time_ms": 0,
        "source_operations": {},
        "events": [],
    }


def current_run_id() -> str | None:
    return (_ACTIVE or {}).get("run_id")


def set_current_source(source_id: str):
    return _CURRENT_SOURCE_ID.set(source_id)


def reset_current_source(token) -> None:
    _CURRENT_SOURCE_ID.reset(token)


def record_cache(source_id: str, cache: str) -> None:
    if _ACTIVE is None:
        return
    if cache == "HIT":
        _ACTIVE["cache_hits"] += 1
    else:
        _ACTIVE["cache_misses"] += 1
    _ACTIVE["events"].append({"type": "cache", "source_id": source_id, "cache": cache, "ts": time.time()})


def record_network(url: str, duration_ms: int) -> None:
    if _ACTIVE is None:
        return
    provider = provider_from_url(url)
    source_id = _CURRENT_SOURCE_ID.get() or "unknown"
    _ACTIVE["request_count"] += 1
    _ACTIVE["request_count_per_provider"][provider] = _ACTIVE["request_count_per_provider"].get(provider, 0) + 1
    _ACTIVE["request_count_per_source"][source_id] = _ACTIVE["request_count_per_source"].get(source_id, 0) + 1
    _ACTIVE["total_network_time_ms"] += int(duration_ms)
    _ACTIVE["events"].append(
        {
            "type": "network",
            "provider": provider,
            "source_id": source_id,
            "duration_ms": int(duration_ms),
            "ts": time.time(),
        }
    )


def record_source_operation(source_id: str, status: str, duration_ms: int, cache: str) -> None:
    if _ACTIVE is None:
        return
    _ACTIVE["source_operations"][source_id] = {
        "status": status,
        "duration_ms": int(duration_ms),
        "cache": cache,
        "finished_at": time.time(),
    }


def record_source_reuse(source_id: str, state: dict[str, Any] | None = None) -> None:
    if _ACTIVE is None:
        return
    state = state or {}
    _ACTIVE["deduplicated_requests"] += 1
    _ACTIVE["source_operations"][source_id] = {
        "status": f"reuse:{state.get('status') or 'terminal'}",
        "duration_ms": int(state.get("duration_ms") or 0),
        "cache": state.get("cache") or "REUSE",
        "finished_at": time.time(),
    }


def finish_run() -> dict[str, Any] | None:
    if _ACTIVE is None:
        return None
    _ACTIVE["finished_at"] = time.time()
    return metrics_snapshot()


def metrics_snapshot() -> dict[str, Any] | None:
    if _ACTIVE is None:
        return None
    snapshot = dict(_ACTIVE)
    snapshot["request_count_per_provider"] = dict(_ACTIVE["request_count_per_provider"])
    snapshot["request_count_per_source"] = dict(_ACTIVE["request_count_per_source"])
    snapshot["source_operations"] = dict(_ACTIVE["source_operations"])
    elapsed_to = snapshot.get("finished_at") or time.time()
    snapshot["elapsed_ms"] = int((elapsed_to - float(snapshot["started_at"])) * 1000)
    return snapshot
