"""Run the job worker without the API (D14). The API also starts one by default (WORKER_ENABLED=true).

Run from the backend folder:
    python run_worker.py          # poll until Ctrl+C
    python run_worker.py --once   # process the jobs that are due now, then exit
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import ConfigError, get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.db.clients import get_admin_client  # noqa: E402
from app.workers.ingestion import build_worker  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process queued background jobs (document ingestion).")
    parser.add_argument("--once", action="store_true", help="run the due jobs once and exit")
    args = parser.parse_args(argv)
    try:
        setup_logging(get_settings().log_level)
        worker = build_worker(get_admin_client())
    except ConfigError as exc:
        print(f"FAILED: {exc}")
        return 2
    logging.getLogger(__name__).info("Worker %s", worker.worker_id)
    if args.once:
        recovered = worker.recover_stale()
        ran = worker.run_once()
        print(f"Recovered {recovered} stale job(s), ran {ran} job(s).")
        return 0
    stop = asyncio.Event()
    try:
        asyncio.run(worker.run_forever(stop))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
