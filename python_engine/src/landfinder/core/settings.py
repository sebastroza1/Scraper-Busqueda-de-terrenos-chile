from __future__ import annotations

import os
import secrets
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    data_dir: Path
    database_path: Path
    session_token: str
    cmf_api_key: str | None = None
    mercado_publico_ticket: str | None = None
    mercadolibre_access_token: str | None = None
    mercadolibre_refresh_token: str | None = None
    mercadolibre_access_token_expires_at: str | None = None
    reference_property_id: str | None = None
    image_max_bytes: int = 8 * 1024 * 1024


def load_settings(
    *,
    data_dir: str | Path | None = None,
    port: int | None = None,
    session_token: str | None = None,
) -> Settings:
    root = Path(__file__).resolve().parents[4]
    resolved_data_dir = Path(
        data_dir or os.getenv("LAND_FINDER_DATA_DIR") or root / "data"
    ).resolve()
    resolved_data_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        port=port or int(os.getenv("LAND_FINDER_PORT", "8765")),
        data_dir=resolved_data_dir,
        database_path=Path(
            os.getenv("LAND_FINDER_DB", resolved_data_dir / "landfinder.sqlite")
        ).resolve(),
        session_token=session_token
        or os.getenv("LAND_FINDER_SESSION_TOKEN")
        or secrets.token_urlsafe(32),
        cmf_api_key=os.getenv("CMF_API_KEY") or os.getenv("UF_CMF_API_KEY"),
        mercado_publico_ticket=os.getenv("MERCADO_PUBLICO_TICKET"),
        mercadolibre_access_token=os.getenv("MERCADOLIBRE_ACCESS_TOKEN"),
        mercadolibre_refresh_token=os.getenv("MERCADOLIBRE_REFRESH_TOKEN"),
        mercadolibre_access_token_expires_at=os.getenv(
            "MERCADOLIBRE_ACCESS_TOKEN_EXPIRES_AT"
        ),
        reference_property_id=os.getenv("LAND_FINDER_REFERENCE_PROPERTY_ID")
        or os.getenv("LANDFINDER_REFERENCE_PROPERTY_ID"),
    )
