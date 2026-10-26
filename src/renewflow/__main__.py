"""`python -m renewflow` starts the dashboard and API on http://127.0.0.1:8000."""

from __future__ import annotations

import argparse

import uvicorn

from .api.app import create_app
from .service import RenewFlow


def main() -> None:
    parser = argparse.ArgumentParser(prog="renewflow", description="Run the RenewFlow demo server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reset", action="store_true", help="Wipe the database and reseed demo data.")
    args = parser.parse_args()

    svc = RenewFlow.create()
    if args.reset:
        svc.reset()
    uvicorn.run(create_app(svc), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
