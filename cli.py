import argparse
import json
from pathlib import Path

from landfinder.registry import load_sources
from landfinder.runner import run_sources

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--priority", default="P0", choices=["P0","P1","P2","P3","ALL"])
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()

    sources = load_sources()
    if args.priority != "ALL":
        sources = [s for s in sources if s["priority"] == args.priority]

    def show(i, total, source, result):
        print(
            f"[{i:02}/{total:02}] "
            f"{result['technical_status']:<14} "
            f"{source['provider']} - {source['name']} "
            f"HTTP={result.get('http_status')} "
            f"lat={result.get('latency_ms')}ms"
        )
        if result.get("error"):
            print("    ", result["error"])

    results = run_sources(sources, timeout=args.timeout, persist=True, callback=show)

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("JSON:", args.json_path)

if __name__ == "__main__":
    main()
