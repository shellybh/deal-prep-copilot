"""FastAPI app (D23). Run from backend/:  uvicorn app.main:app --reload"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health, kb, users
from app.core.config import ConfigError, get_settings
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Starts the job worker (D14) with the API, unless WORKER_ENABLED=false (e.g. a separate worker
    process: python run_worker.py). Unit tests don't enter the lifespan, so no worker runs there."""
    stop, task = asyncio.Event(), None
    if settings.worker_enabled:
        from app.db.clients import get_admin_client
        from app.workers.ingestion import build_worker
        try:
            task = asyncio.create_task(build_worker(get_admin_client()).run_forever(stop))
        except ConfigError as exc:   # e.g. no GEMINI_API_KEY: the API still runs, ingestion doesn't
            log.error("Job worker not started: %s", exc)
    yield
    stop.set()
    if task:
        await task


app = FastAPI(title="Deal-Prep Copilot API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health.router)
app.include_router(users.router, prefix="/api")
app.include_router(kb.router, prefix="/api")
