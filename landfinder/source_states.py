from __future__ import annotations

from typing import Any


NOT_REQUESTED = "NOT_REQUESTED"
LOADING = "LOADING"
SUCCESS_DATA = "SUCCESS_DATA"
SUCCESS_EMPTY = "SUCCESS_EMPTY"
STALE = "STALE"
TIMEOUT = "TIMEOUT"
ERROR = "ERROR"
RATE_LIMITED = "RATE_LIMITED"
NOT_CONFIGURED = "NOT_CONFIGURED"
MISSING_DATA = "MISSING_DATA"
CIRCUIT_OPEN = "CIRCUIT_OPEN"
VISUAL_ONLY = "VISUAL_ONLY"

TERMINAL_STATES = {
    SUCCESS_DATA,
    SUCCESS_EMPTY,
    STALE,
    TIMEOUT,
    ERROR,
    RATE_LIMITED,
    NOT_CONFIGURED,
    MISSING_DATA,
    CIRCUIT_OPEN,
    VISUAL_ONLY,
}

SUCCESS_STATES = {SUCCESS_DATA, SUCCESS_EMPTY, STALE, VISUAL_ONLY}
FAILURE_STATES = {TIMEOUT, ERROR, RATE_LIMITED, CIRCUIT_OPEN}
UNKNOWN_COUNT_STATES = {TIMEOUT, ERROR, RATE_LIMITED, NOT_CONFIGURED, MISSING_DATA, CIRCUIT_OPEN}


def normalize_status(status: str | None, count: int | None = None) -> str:
    if not status:
        return NOT_REQUESTED
    if status in TERMINAL_STATES or status == LOADING or status == NOT_REQUESTED:
        return status
    if status in {"OK", "CACHE_HIT"}:
        return SUCCESS_DATA if (count or 0) > 0 else SUCCESS_EMPTY
    if status == "OK_SIN_COINCIDENCIAS":
        return SUCCESS_EMPTY
    if status == "STALE_CACHE":
        return STALE
    if status == "SOURCE_ERROR":
        return ERROR
    if status in {"NOT_SUPPORTED", "DEGRADED"}:
        return ERROR
    return status


def classify_runtime_error(error: str | None) -> str:
    text = (error or "").lower()
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return RATE_LIMITED
    if "timeout" in text or "timed out" in text or "demor" in text or "tiempo" in text:
        return TIMEOUT
    return ERROR


def source_result_count(result: Any) -> int | None:
    if result is None:
        return None
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        if "count" in result and isinstance(result.get("count"), int):
            return int(result["count"])
        if "features" in result and isinstance(result.get("features"), list):
            return len(result["features"])
        if all(isinstance(value, dict) for value in result.values()):
            total = 0
            found = False
            for value in result.values():
                if "segments" in value:
                    total += len(value.get("segments") or [])
                    found = True
                elif "stations_in_area" in value:
                    total += len(value.get("stations_in_area") or [])
                    found = True
            if found:
                return total
    return 0
