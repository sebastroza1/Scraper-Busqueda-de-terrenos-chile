from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import DATA_DIR


CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _path_for(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def read_persistent_cache(cache_key: str) -> dict[str, Any] | None:
    path = _path_for(cache_key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_persistent_cache(cache_key: str, payload: dict[str, Any]) -> None:
    path = _path_for(cache_key)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
