from __future__ import annotations
import json
from typing import List, Dict, Any
from .config import REGISTRY_PATH

REQUIRED = {
    "id", "provider", "name", "category", "priority", "kind",
    "audit_status", "runtime_policy", "legal_gate", "role",
    "coverage", "note"
}

def load_sources() -> List[Dict[str, Any]]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("sources_registry.json debe contener una lista.")

    ids = []
    for source in data:
        missing = REQUIRED - set(source)
        if missing:
            raise ValueError(f"{source.get('id')}: faltan campos {sorted(missing)}")
        ids.append(source["id"])

    if len(ids) != len(set(ids)):
        raise ValueError("Hay IDs duplicados en el registro.")
    return data
