from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from landfinder.api.app import create_app
from landfinder.core.credentials import diagnose_cmf, diagnose_mercadolibre
from landfinder.core.settings import Settings


def _settings(tmp_path: Path, **overrides) -> Settings:  # noqa: ANN003
    values = {
        "data_dir": tmp_path,
        "database_path": tmp_path / "landfinder.sqlite",
        "session_token": "test-token",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_cmf_credential_diagnostic_not_configured(tmp_path) -> None:
    diagnostic = await diagnose_cmf(_settings(tmp_path))

    assert diagnostic.status == "NOT_CONFIGURED"
    assert "Clave CMF" in diagnostic.message


@pytest.mark.asyncio
async def test_mercadolibre_credential_diagnostic_expired(tmp_path) -> None:
    diagnostic = await diagnose_mercadolibre(
        _settings(
            tmp_path,
            mercadolibre_access_token="configured",
            mercadolibre_access_token_expires_at=(
                datetime.now(UTC) - timedelta(minutes=1)
            ).isoformat(),
        )
    )

    assert diagnostic.status == "EXPIRED"


def test_credential_diagnostic_endpoint_is_sanitized(tmp_path) -> None:
    client = TestClient(create_app(_settings(tmp_path)))

    response = client.post(
        "/credentials/diagnostics/mercado_publico",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "NOT_CONFIGURED"
    assert "MERCADO_PUBLICO_TICKET" not in payload["message"]
