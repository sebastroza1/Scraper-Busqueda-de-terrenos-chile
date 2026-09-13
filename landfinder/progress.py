from __future__ import annotations

from typing import Any

from .source_states import FAILURE_STATES, TERMINAL_STATES, normalize_status


def source_progress(bundle: dict[str, Any]) -> tuple[int, int, float]:
    states = list((bundle.get("layer_states") or {}).values())
    total = len(states)
    if total == 0:
        return 0, 0, 0.0
    done = sum(1 for state in states if normalize_status(state.get("status"), state.get("count")) in TERMINAL_STATES)
    return done, total, done / total


def progress_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    done, total, ratio = source_progress(bundle)
    states = list((bundle.get("layer_states") or {}).values())
    warnings = sum(
        1
        for state in states
        if normalize_status(state.get("status"), state.get("count")) in FAILURE_STATES
    )
    total_ms = 0
    seen_operations = set()
    for state in states:
        operation_id = state.get("batch_source_id") or state.get("source_id")
        if operation_id in seen_operations:
            continue
        seen_operations.add(operation_id)
        total_ms += int(state.get("duration_ms") or 0)
    return {
        "done": done,
        "total": total,
        "ratio": ratio,
        "warnings": warnings,
        "duration_ms": total_ms,
        "complete": bool(total and done == total),
    }
