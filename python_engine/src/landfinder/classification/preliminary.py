from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class PreliminaryLandStatus:
    POTENTIALLY_SUITABLE = "POTENCIALMENTE_APTO"
    NEEDS_REVIEW = "REQUIERE_REVISION"
    POTENTIALLY_UNSUITABLE = "POTENCIALMENTE_NO_APTO"
    INSUFFICIENT_INFORMATION = "SIN_INFORMACION_SUFICIENTE"


class CriterionResult:
    PASSES = "CUMPLE"
    FAILS = "NO_CUMPLE"
    PENDING = "PENDIENTE"
    NOT_VERIFIED = "NO_VERIFICADO"
    NOT_APPLICABLE = "NO_APLICA"


@dataclass(frozen=True)
class PreliminaryAssessment:
    status: str
    criteria: list[dict[str, Any]]
    explanation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "criteria": self.criteria,
            "explanation": self.explanation,
        }


def evaluate_preliminary_territorial_status(
    *,
    property_record: dict[str, Any],
    urban_limit: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    prc: dict[str, Any] | None,
) -> PreliminaryAssessment:
    checked_at = datetime.now(UTC).isoformat()
    criteria = [
        _location_criterion(property_record, checked_at),
        _surface_criterion(property_record, checked_at),
        _urban_limit_criterion(urban_limit, checked_at),
        _prc_criterion(prc, checked_at),
        _risk_criterion(risk, checked_at),
    ]
    status = _status_from_criteria(criteria)
    explanation = _explanation(status, criteria)
    return PreliminaryAssessment(status=status, criteria=criteria, explanation=explanation)


def insufficient_location_assessment(property_record: dict[str, Any]) -> PreliminaryAssessment:
    checked_at = datetime.now(UTC).isoformat()
    criteria = [
        _location_criterion(property_record, checked_at),
        _surface_criterion(property_record, checked_at),
        {
            "criterion_key": "urban_limit",
            "criterion_label": "Dentro de limite urbano",
            "result": CriterionResult.NOT_VERIFIED,
            "value": None,
            "source": None,
            "endpoint": None,
            "layer_name": None,
            "checked_at": checked_at,
            "confidence": 0,
            "observation": "Falta ubicacion verificable para consultar IDE MINVU.",
            "evidence": {},
        },
        {
            "criterion_key": "risk",
            "criterion_label": "Riesgo territorial",
            "result": CriterionResult.NOT_VERIFIED,
            "value": None,
            "source": None,
            "endpoint": None,
            "layer_name": None,
            "checked_at": checked_at,
            "confidence": 0,
            "observation": "Falta ubicacion verificable para consultar IDE MINVU.",
            "evidence": {},
        },
    ]
    return PreliminaryAssessment(
        status=PreliminaryLandStatus.INSUFFICIENT_INFORMATION,
        criteria=criteria,
        explanation="Sin informacion suficiente: no hay ubicacion consultable.",
    )


def _location_criterion(property_record: dict[str, Any], checked_at: str) -> dict[str, Any]:
    lat = property_record.get("latitude")
    lon = property_record.get("longitude")
    precision = str(property_record.get("location_precision") or "UNKNOWN")
    if lat is None or lon is None:
        result = CriterionResult.PENDING
        observation = "No hay coordenadas para ubicar el terreno."
        confidence = 0.0
    elif precision in {"EXACT", "APPROXIMATE_PROPERTY"}:
        result = CriterionResult.PASSES
        observation = "Coordenadas disponibles; precision debe leerse junto al metodo."
        confidence = float(property_record.get("geocoding_confidence") or 0.7)
    else:
        result = CriterionResult.PENDING
        observation = "Ubicacion aproximada; requiere verificacion antes de concluir."
        confidence = float(property_record.get("geocoding_confidence") or 0.45)
    return {
        "criterion_key": "location",
        "criterion_label": "Ubicacion del terreno",
        "result": result,
        "value": {"latitude": lat, "longitude": lon, "precision": precision},
        "source": property_record.get("location_source") or property_record.get("geocoding_source"),
        "endpoint": None,
        "layer_name": None,
        "checked_at": checked_at,
        "confidence": confidence,
        "observation": observation,
        "evidence": {},
    }


def _surface_criterion(property_record: dict[str, Any], checked_at: str) -> dict[str, Any]:
    area = property_record.get("gross_area_m2") or property_record.get("advertised_area_m2")
    return {
        "criterion_key": "surface",
        "criterion_label": "Superficie",
        "result": CriterionResult.PASSES if area else CriterionResult.PENDING,
        "value": area,
        "source": property_record.get("source"),
        "endpoint": property_record.get("canonical_url"),
        "layer_name": None,
        "checked_at": checked_at,
        "confidence": 0.75 if area else 0,
        "observation": None if area else "Publicacion sin superficie normalizada.",
        "evidence": {},
    }


def _urban_limit_criterion(urban_limit: dict[str, Any] | None, checked_at: str) -> dict[str, Any]:
    status = str((urban_limit or {}).get("status") or "UNKNOWN")
    if status == "YES":
        result = CriterionResult.PASSES
        observation = "El punto/geometria intersecta una capa de limite urbano."
    elif status == "NO":
        result = CriterionResult.FAILS
        observation = "No se detecto interseccion con las capas de limite urbano consultadas."
    else:
        result = CriterionResult.NOT_VERIFIED
        observation = "No hay respuesta verificable de limite urbano."
    return {
        "criterion_key": "urban_limit",
        "criterion_label": "Dentro de limite urbano",
        "result": result,
        "value": status,
        "source": (urban_limit or {}).get("source"),
        "endpoint": (urban_limit or {}).get("service"),
        "layer_name": (urban_limit or {}).get("layer"),
        "checked_at": checked_at,
        "confidence": float((urban_limit or {}).get("confidence") or 0),
        "observation": observation,
        "evidence": urban_limit or {},
    }


def _prc_criterion(prc: dict[str, Any] | None, checked_at: str) -> dict[str, Any]:
    status = str((prc or {}).get("status") or "UNKNOWN")
    zone = (prc or {}).get("zone")
    if status == "FOUND" and zone:
        result = CriterionResult.PASSES
        observation = "Se encontro capa PRC/IPT con atributo de zona."
    elif status == "UNKNOWN":
        result = CriterionResult.NOT_VERIFIED
        observation = (prc or {}).get("warning") or "No se encontro zona PRC verificable."
    else:
        result = CriterionResult.PENDING
        observation = "PRC requiere revision manual."
    return {
        "criterion_key": "prc_zoning",
        "criterion_label": "Zonificacion / PRC",
        "result": result,
        "value": zone,
        "source": (prc or {}).get("source"),
        "endpoint": (prc or {}).get("source_url") or (prc or {}).get("service_url"),
        "layer_name": (prc or {}).get("applicable_layer"),
        "checked_at": checked_at,
        "confidence": 0.75 if result == CriterionResult.PASSES else 0.2,
        "observation": observation,
        "evidence": prc or {},
    }


def _risk_criterion(risk: dict[str, Any] | None, checked_at: str) -> dict[str, Any]:
    status = str((risk or {}).get("status") or "UNKNOWN")
    if status == "INTERSECTION_DETECTED":
        result = CriterionResult.FAILS
        observation = "Se detecto interseccion con al menos una capa de riesgo."
    elif status == "NO_INTERSECTION_DETECTED":
        result = CriterionResult.PASSES
        observation = "No se detecto interseccion con las capas de riesgo consultadas."
    else:
        result = CriterionResult.NOT_VERIFIED
        observation = "Riesgo no verificado."
    return {
        "criterion_key": "risk",
        "criterion_label": "Riesgo territorial",
        "result": result,
        "value": {"status": status, "risk_types": (risk or {}).get("risk_types") or []},
        "source": (risk or {}).get("source"),
        "endpoint": None,
        "layer_name": ",".join((risk or {}).get("layers") or []),
        "checked_at": checked_at,
        "confidence": float((risk or {}).get("confidence") or 0),
        "observation": observation,
        "evidence": risk or {},
    }


def _status_from_criteria(criteria: list[dict[str, Any]]) -> str:
    by_key = {item["criterion_key"]: item for item in criteria}
    if any(item["result"] == CriterionResult.FAILS for item in criteria):
        return PreliminaryLandStatus.POTENTIALLY_UNSUITABLE
    urban = by_key.get("urban_limit", {}).get("result")
    risk = by_key.get("risk", {}).get("result")
    location = by_key.get("location", {}).get("result")
    pending = any(
        item["result"] in {CriterionResult.PENDING, CriterionResult.NOT_VERIFIED}
        for item in criteria
    )
    if (
        location == CriterionResult.PASSES
        and urban == CriterionResult.PASSES
        and risk == CriterionResult.PASSES
    ):
        return (
            PreliminaryLandStatus.NEEDS_REVIEW
            if pending
            else PreliminaryLandStatus.POTENTIALLY_SUITABLE
        )
    if location == CriterionResult.PASSES:
        return PreliminaryLandStatus.NEEDS_REVIEW
    return PreliminaryLandStatus.INSUFFICIENT_INFORMATION


def _explanation(status: str, criteria: list[dict[str, Any]]) -> str:
    failed = [
        item["criterion_label"] for item in criteria if item["result"] == CriterionResult.FAILS
    ]
    pending = [
        item["criterion_label"]
        for item in criteria
        if item["result"] in {CriterionResult.PENDING, CriterionResult.NOT_VERIFIED}
    ]
    if failed:
        return f"{status}: revisar criterios no cumplidos: {', '.join(failed)}."
    if pending:
        return f"{status}: quedan criterios pendientes/no verificados: {', '.join(pending)}."
    return f"{status}: evaluacion preliminar con fuentes disponibles; no equivale a apto normativo."
