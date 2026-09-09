from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
EXPORT_DIR = BASE_DIR / "exports"

REGISTRY_PATH = CONFIG_DIR / "sources_registry.json"
DB_PATH = DATA_DIR / "health_history.sqlite3"

DEFAULT_TIMEOUT = 12
USER_AGENT = (
    "LandfinderChile-SourceLab/0.3 "
    "(health-check tecnico de desarrollo; solicitudes livianas)"
)

for folder in (CONFIG_DIR, DATA_DIR, EXPORT_DIR):
    folder.mkdir(parents=True, exist_ok=True)
