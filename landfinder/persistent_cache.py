from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import DATA_DIR


CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_SCHEMA_VERSION = "landfinder-source-cache-v2"


def _path_for(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def read_persistent_cache(cache_key: str) -> dict[str, Any] | None:
    path = _path_for(cache_key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not cache_payload_is_valid(payload):
        return None
    return payload


def write_persistent_cache(cache_key: str, payload: dict[str, Any]) -> None:
    path = _path_for(cache_key)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def delete_persistent_cache(cache_key: str) -> bool:
    path = _path_for(cache_key)
    if not path.exists():
        return False
    path.unlink()
    return True


def cache_payload_is_valid(payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") == CACHE_SCHEMA_VERSION:
        return "value" in payload and "stored_at" in payload
    # Legacy non-empty caches are still usable. Legacy empty caches are
    # considered suspicious because earlier provider failures could persist [].
    count = payload.get("count")
    return isinstance(count, int) and count > 0 and "value" in payload


def cache_age_seconds(payload: dict[str, Any], now: float) -> float | None:
    try:
        return max(0.0, float(now) - float(payload.get("stored_at")))
    except (TypeError, ValueError):
        return None


def cache_digest(cache_key: str) -> str:
    return hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
