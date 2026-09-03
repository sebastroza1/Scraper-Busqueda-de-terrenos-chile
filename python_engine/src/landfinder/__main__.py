from __future__ import annotations

import argparse

import uvicorn
from dotenv import load_dotenv

from landfinder.api.app import create_app
from landfinder.core.settings import load_settings
from landfinder.storage.database import init_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Landfinder local backend")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.host != "127.0.0.1":
        raise SystemExit("Refusing to bind outside 127.0.0.1 by default")

    load_dotenv()
    settings = load_settings(data_dir=args.data_dir, port=args.port)
    init_database(settings.database_path)
    app = create_app(settings)
    print(f"LANDFINDER_SESSION_TOKEN={settings.session_token}", flush=True)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
