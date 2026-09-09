from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from landfinder.core.settings import Settings
from landfinder.models.enums import CredentialDiagnosticStatus


@dataclass(frozen=True)
class CredentialDiagnostic:
    source_id: str
    status: CredentialDiagnosticStatus
    checked_at: datetime
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status.value,
            "checked_at": self.checked_at.isoformat(),
            "message": self.message,
        }


async def diagnose_source_credentials(
    settings: Settings,
    source_id: str,
) -> CredentialDiagnostic:
    normalized = source_id.strip().lower()
    if normalized in {"mercado_publico", "chilecompra"}:
        return await diagnose_mercado_publico(settings)
    if normalized in {"mercadolibre", "mercadolibre_real_estate"}:
        return await diagnose_mercadolibre(settings)
    if normalized in {"cmf", "uf", "cmf_uf"}:
        return await diagnose_cmf(settings)
    return CredentialDiagnostic(
        source_id=source_id,
        status=CredentialDiagnosticStatus.UNAVAILABLE,
        checked_at=_now(),
        message="Fuente no reconocida para diagnostico de credenciales.",
    )


async def diagnose_mercado_publico(settings: Settings) -> CredentialDiagnostic:
    source_id = "mercado_publico"
    if not settings.mercado_publico_ticket:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.NOT_CONFIGURED,
            "Ticket Mercado Publico no configurado.",
        )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json",
                params={
                    "fecha": date.today().strftime("%d%m%Y"),
                    "ticket": settings.mercado_publico_ticket,
                },
            )
        return _diagnose_http_response(
            source_id,
            response,
            connected_message="Ticket Mercado Publico aceptado por API oficial.",
        )
    except httpx.HTTPError as exc:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.UNAVAILABLE,
            f"No se pudo contactar Mercado Publico ({type(exc).__name__}).",
        )


async def diagnose_mercadolibre(settings: Settings) -> CredentialDiagnostic:
    source_id = "mercadolibre_real_estate"
    if not settings.mercadolibre_access_token:
        status = (
            CredentialDiagnosticStatus.EXPIRED
            if settings.mercadolibre_refresh_token
            else CredentialDiagnosticStatus.NOT_CONFIGURED
        )
        message = (
            "Access token no configurado; existe refresh token y se requiere renovacion."
            if settings.mercadolibre_refresh_token
            else (
                "OAuth MercadoLibre no configurado: falta MERCADOLIBRE_ACCESS_TOKEN "
                "o MERCADOLIBRE_REFRESH_TOKEN con MERCADOLIBRE_CLIENT_ID."
            )
        )
        return _diagnostic(source_id, status, message)
    if settings.mercadolibre_access_token_expires_at:
        try:
            expires_at = datetime.fromisoformat(settings.mercadolibre_access_token_expires_at)
        except ValueError:
            return _diagnostic(
                source_id,
                CredentialDiagnosticStatus.EXPIRED,
                "Fecha de expiracion MercadoLibre invalida; requiere reconexion.",
            )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= _now():
            return _diagnostic(
                source_id,
                CredentialDiagnosticStatus.EXPIRED,
                "Access token MercadoLibre expirado; requiere refresh o reconexion.",
            )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://api.mercadolibre.com/sites/MLC/categories",
                headers={"Authorization": f"Bearer {settings.mercadolibre_access_token}"},
            )
        return _diagnose_http_response(
            source_id,
            response,
            connected_message="OAuth MercadoLibre aceptado por API oficial.",
            expired_on_unauthorized=True,
        )
    except httpx.HTTPError as exc:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.UNAVAILABLE,
            f"No se pudo contactar MercadoLibre ({type(exc).__name__}).",
        )


async def diagnose_cmf(settings: Settings) -> CredentialDiagnostic:
    source_id = "cmf"
    if not settings.cmf_api_key:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.NOT_CONFIGURED,
            "Clave CMF no configurada.",
        )
    today = date.today()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"https://api.cmfchile.cl/api-sbifv3/recursos_api/uf/{today:%Y/%m}",
                params={"apikey": settings.cmf_api_key, "formato": "json"},
            )
        return _diagnose_http_response(
            source_id,
            response,
            connected_message="Clave CMF aceptada por API oficial.",
        )
    except httpx.HTTPError as exc:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.UNAVAILABLE,
            f"No se pudo contactar CMF ({type(exc).__name__}).",
        )


def _diagnose_http_response(
    source_id: str,
    response: httpx.Response,
    *,
    connected_message: str,
    expired_on_unauthorized: bool = False,
) -> CredentialDiagnostic:
    if response.status_code == 429:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.RATE_LIMITED,
            "La fuente respondio limite de tasa.",
        )
    if response.status_code == 401 and expired_on_unauthorized:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.EXPIRED,
            "La fuente rechazo el token por expiracion o autorizacion vencida.",
        )
    if response.status_code in {401, 403}:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.INVALID_CREDENTIAL,
            "La fuente rechazo la credencial configurada.",
        )
    if response.status_code >= 500:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.UNAVAILABLE,
            f"La fuente respondio HTTP {response.status_code}.",
        )
    if response.status_code >= 400:
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.INVALID_CREDENTIAL,
            f"La fuente respondio HTTP {response.status_code}.",
        )
    payload = _safe_json(response)
    if _payload_has_error(payload):
        return _diagnostic(
            source_id,
            CredentialDiagnosticStatus.INVALID_CREDENTIAL,
            "La fuente respondio un error para la credencial configurada.",
        )
    return _diagnostic(source_id, CredentialDiagnosticStatus.CONNECTED, connected_message)


def _diagnostic(
    source_id: str,
    status: CredentialDiagnosticStatus,
    message: str,
) -> CredentialDiagnostic:
    return CredentialDiagnostic(
        source_id=source_id,
        status=status,
        checked_at=_now(),
        message=message,
    )


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _payload_has_error(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("error", "Error", "MensajeError", "mensajeError"):
        if payload.get(key):
            return True
    return False


def _now() -> datetime:
    return datetime.now(UTC)
