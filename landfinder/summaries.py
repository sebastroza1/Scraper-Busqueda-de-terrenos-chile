from __future__ import annotations

from typing import Any

from .source_states import FAILURE_STATES, MISSING_DATA, NOT_CONFIGURED, SUCCESS_DATA, SUCCESS_EMPTY, normalize_status


def result_pipeline_counts(result: dict[str, Any] | None) -> dict[str, int]:
    counts = {"raw": 0, "normalized": 0, "matching": 0, "stored": 0, "rendered": 0}
    if not isinstance(result, dict):
        return counts
    if result.get("pipeline"):
        for key in ("raw", "normalized", "matching", "stored", "rendered"):
            counts[key] = int((result["pipeline"] or {}).get(key) or 0)
        return counts
    for layer in result.get("layers") or []:
        pipeline = layer.get("pipeline") or {}
        counts["raw"] += int(pipeline.get("raw") or 0)
        counts["normalized"] += int(pipeline.get("normalized") or 0)
        counts["matching"] += int(pipeline.get("matching") or 0)
        counts["stored"] += int(pipeline.get("stored") or 0)
        counts["rendered"] += len((layer.get("geojson") or {}).get("features") or [])
    if not counts["stored"]:
        counts["stored"] = len(result.get("records") or [])
    return counts


def land_use_summary_value(bundle: dict[str, Any]) -> str:
    if not bundle:
        return "No consultado"
    result = (bundle.get("technical") or {}).get("minvu_prms_uso_suelo")
    state = (bundle.get("layer_states") or {}).get("minvu_prms_uso_suelo")
    if not state:
        return "No consultado"
    status = normalize_status(state.get("status"), state.get("count"))
    if status in FAILURE_STATES:
        return "Temporalmente no disponible"
    if status in {NOT_CONFIGURED, MISSING_DATA}:
        return "Fuente no configurada"
    if status == SUCCESS_EMPTY:
        return "Sin coincidencias PRMS"
    if status != SUCCESS_DATA:
        return status

    raw_labels = []
    for record in (result or {}).get("records") or []:
        label = record.get("Elemento") or record.get("TIPO") or record.get("NOMBRE") or record.get("DESCRIPCION")
        label_text = str(label).strip() if label is not None else ""
        if label_text and label_text not in raw_labels:
            raw_labels.append(label_text)
    land_use_labels = [
        label
        for label in raw_labels
        if any(token in label.lower() for token in ("zona", "habitacional", "industrial", "equipamiento", "uso"))
    ]
    labels = (land_use_labels or raw_labels)[:2]
    if not labels:
        return "Fuente consultada sin etiqueta PRMS"
    suffix = "" if len((result or {}).get("records") or []) <= len(labels) else f" +{len((result or {}).get('records') or []) - len(labels)}"
    return "; ".join(labels) + suffix
