from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"

REGISTRY_PATH = CONFIG_DIR / "sources_registry.json"
DB_PATH = DATA_DIR / "health_history.sqlite3"

DEFAULT_TIMEOUT = 10
SOURCE_CONFIG = {
    "default": {"timeout": 10, "retries": 0, "cache_ttl_seconds": 900, "circuit_failures": 3, "circuit_cooldown_seconds": 180},
    "metro_static": {"timeout": 2, "retries": 0, "cache_ttl_seconds": 3600, "circuit_failures": 2, "circuit_cooldown_seconds": 120},
    "osm_overpass": {"timeout": 8, "retries": 0, "cache_ttl_seconds": 900, "circuit_failures": 3, "circuit_cooldown_seconds": 180},
    "arcgis": {"timeout": 10, "retries": 0, "cache_ttl_seconds": 900, "circuit_failures": 3, "circuit_cooldown_seconds": 180},
    "wfs": {"timeout": 10, "retries": 0, "cache_ttl_seconds": 900, "circuit_failures": 3, "circuit_cooldown_seconds": 180},
    "wms": {"timeout": 8, "retries": 0, "cache_ttl_seconds": 900, "circuit_failures": 3, "circuit_cooldown_seconds": 180},
    "mop": {"timeout": 8, "retries": 0, "cache_ttl_seconds": 900, "circuit_failures": 3, "circuit_cooldown_seconds": 240},
    "seia": {"timeout": 10, "retries": 0, "cache_ttl_seconds": 900, "circuit_failures": 3, "circuit_cooldown_seconds": 240},
    "unconfigured": {"timeout": 0, "retries": 0, "cache_ttl_seconds": 0, "circuit_failures": 0, "circuit_cooldown_seconds": 0},
}


def source_config(source_or_key):
    if isinstance(source_or_key, str):
        key = source_or_key
        provider = ""
        kind = source_or_key
    else:
        key = source_or_key.get("id", "")
        provider = source_or_key.get("provider", "")
        kind = source_or_key.get("kind", "")

    haystack = f"{key} {provider}".lower()
    if kind == "unconfigured" or "gap" in key:
        return SOURCE_CONFIG["unconfigured"]
    if "overpass" in haystack or "osm" in haystack:
        return SOURCE_CONFIG["osm_overpass"]
    if "mop" in haystack or "dga" in haystack:
        return SOURCE_CONFIG["mop"]
    if "seia" in haystack or "sea" in haystack:
        return SOURCE_CONFIG["seia"]
    if kind in SOURCE_CONFIG:
        return SOURCE_CONFIG[kind]
    if kind in ("arcgis_service", "arcgis_layer"):
        return SOURCE_CONFIG["arcgis"]
    return SOURCE_CONFIG["default"]
USER_AGENT = (
    "LandfinderChile-SourceLab/0.3 "
    "(health-check tecnico de desarrollo; solicitudes livianas)"
)

for folder in (CONFIG_DIR, DATA_DIR, EXPORT_DIR):
    folder.mkdir(parents=True, exist_ok=True)
