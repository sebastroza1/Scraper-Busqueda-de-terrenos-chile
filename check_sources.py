from __future__ import annotations

import argparse
import time
from collections import Counter

from landfinder.config import source_config
from landfinder.metro_adapter import metro_current_for_area, metro_future_for_area
from landfinder.probes import health_state, probe_source
from landfinder.registry import load_sources
from landfinder.storage import save_result


def source_status_group(status: str) -> str:
    if status == "healthy":
        return "OK"
    if status in {"slow", "auth_error", "not_configured", "unknown"}:
        return "WARN"
    return "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight Landfinder source health checks.")
    parser.add_argument("--priority", action="append", choices=["P0", "P1", "P2", "P3"], help="Priority to include. Can be repeated.")
    parser.add_argument("--timeout", type=int, default=None, help="Override timeout per source in seconds.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of sources to check.")
    parser.add_argument("--save", action="store_true", help="Persist results to the local health history database.")
    args = parser.parse_args()

    priorities = set(args.priority or ["P0", "P1"])
    sources = [source for source in load_sources() if source.get("priority") in priorities]
    if args.limit > 0:
        sources = sources[: args.limit]

    print("LANDFINDER SOURCE CHECK")
    print(f"Sources: {len(sources)} | Priorities: {', '.join(sorted(priorities))}")
    totals: Counter[str] = Counter()

    start = time.perf_counter()
    try:
        current = metro_current_for_area(-33.5623, -70.60053, 2000)
        future = metro_future_for_area(-33.5623, -70.60053, 2000)
        elapsed = int((time.perf_counter() - start) * 1000)
        line_count = sum(1 for line in current.values() if line.get("segments"))
        station_count = sum(len(line.get("stations") or []) for line in current.values())
        future_count = sum(1 for line in future.values() if line.get("segments"))
        totals["OK"] += 1
        print(
            f"[OK] metro_cache | healthy | LOCAL | {elapsed}ms | "
            f"current_lines={line_count} current_stations={station_count} future_lines={future_count}"
        )
    except Exception as exc:
        totals["FAIL"] += 1
        print(f"[FAIL] metro_cache | down | LOCAL | - | {type(exc).__name__}: {str(exc)[:120]}")

    for source in sources:
        cfg = source_config(source)
        timeout = args.timeout if args.timeout is not None else int(cfg["timeout"])
        result = probe_source(source, timeout).to_dict()
        if args.save:
            save_result(result)
        health = health_state(result)
        group = source_status_group(health["status"])
        totals[group] += 1
        latency = f"{result['latency_ms']}ms" if result.get("latency_ms") is not None else "-"
        error = f" | {result['error_type'] or 'ERROR'}: {str(result.get('error') or '')[:120]}" if group == "FAIL" else ""
        print(
            f"[{group}] {source['id']} | {health['status']} | {result['technical_status']} | "
            f"{latency} | timeout={timeout}s{error}"
        )

    print(f"Totals: OK={totals['OK']} WARN={totals['WARN']} FAIL={totals['FAIL']}")
    return 1 if totals["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
