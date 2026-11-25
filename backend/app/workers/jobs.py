"""Generic DB-backed job runner (D14). Ingestion uses it now; research runs reuse it in Phase 4.

- `JobQueue`: enqueue, claim (`claim_jobs` SQL function: advisory lock + FOR UPDATE SKIP LOCKED,
  respects a per-kind concurrency limit, D18), heartbeat, complete, fail with retry + backoff,
  recovery of stale running jobs (worker died / backend restarted).
- `Worker`: runs registered handlers. `run_once()` for tests and the CLI, `run_forever()` as an
  asyncio task started with the API (`app/main.py` lifespan). Jobs run in a thread, so the event
  loop stays free; a heartbeat thread updates `heartbeat_at` while a job runs.

A handler is any object with `run(job)` and `give_up(job, error)`:
- `run` raises `PermanentJobError` for failures a retry can't fix (bad file); any other exception is
  retried up to `max_attempts` with backoff.
- `give_up` is called once when the job finally fails, so the handler can mark its own record failed.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from supabase import Client

log = logging.getLogger(__name__)

RETRY_BACKOFF_SECONDS = (10, 60, 300)


class PermanentJobError(RuntimeError):
    """The job can't succeed on retry (e.g. invalid file). Fails it immediately."""


class JobHandler(Protocol):
    def run(self, job: dict) -> None: ...
    def give_up(self, job: dict, error: str) -> None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None


class JobQueue:
    def __init__(self, db: Client):
        self.db = db

    def enqueue(self, kind: str, payload: dict, created_by: str | None = None, max_attempts: int = 3) -> dict:
        return self.db.table("jobs").insert({
            "kind": kind, "payload": payload, "created_by": created_by, "max_attempts": max_attempts,
        }).execute().data[0]

    def claim(self, kind: str, worker_id: str, max_running: int = 1) -> list[dict]:
        return self.db.rpc("claim_jobs", {"p_kind": kind, "p_worker": worker_id,
                                          "p_max_running": max_running}).execute().data or []

    def heartbeat(self, job_id: str) -> None:
        self._update(job_id, {"heartbeat_at": _iso(_now())}, only_status="running")

    def complete(self, job_id: str) -> None:
        self._update(job_id, {"status": "succeeded", "finished_at": _iso(_now()), "error": None})

    def fail(self, job: dict, error: str, permanent: bool = False) -> bool:
        """Returns True if the job is finally failed (no retry left), False if it was re-queued."""
        error = error[:1000]
        if permanent or job["attempts"] >= job["max_attempts"]:
            self._update(job["id"], {"status": "failed", "finished_at": _iso(_now()), "error": error})
            return True
        delay = RETRY_BACKOFF_SECONDS[min(job["attempts"], len(RETRY_BACKOFF_SECONDS)) - 1]
        self._update(job["id"], {"status": "queued", "error": error, "locked_by": None,
                                 "run_after": _iso(_now() + timedelta(seconds=delay))})
        return False

    def cancel_for_document(self, document_id: str) -> None:
        """Queued jobs for a deleted document are cancelled. A running one notices the delete itself."""
        (self.db.table("jobs").update({"status": "cancelled", "finished_at": _iso(_now()),
                                       "updated_at": _iso(_now())})
         .eq("status", "queued").eq("payload->>document_id", document_id).execute())

    def stale_jobs(self, kind: str, stale_seconds: int) -> list[dict]:
        cutoff = _now() - timedelta(seconds=stale_seconds)
        rows = self.db.table("jobs").select("*").eq("kind", kind).eq("status", "running").execute().data or []
        return [j for j in rows if (_parse(j.get("heartbeat_at")) or cutoff) <= cutoff]

    def _update(self, job_id: str, fields: dict, only_status: str | None = None) -> None:
        q = self.db.table("jobs").update({**fields, "updated_at": _iso(_now())}).eq("id", job_id)
        if only_status:
            q = q.eq("status", only_status)
        q.execute()


@dataclass
class Worker:
    queue: JobQueue
    handlers: dict[str, JobHandler]
    concurrency: dict[str, int] = field(default_factory=dict)   # kind -> max running (default 1)
    poll_seconds: float = 2.0
    heartbeat_seconds: float = 15.0
    stale_seconds: int = 300
    worker_id: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}")

    def recover_stale(self) -> int:
        """A running job whose heartbeat stopped belongs to a dead worker: retry it or give up."""
        count = 0
        for kind, handler in self.handlers.items():
            for job in self.queue.stale_jobs(kind, self.stale_seconds):
                log.warning("Recovering stale %s job %s (attempt %s)", kind, job["id"], job["attempts"])
                if self.queue.fail(job, "worker stopped while the job was running"):
                    handler.give_up(job, "Processing was interrupted. Upload the file again.")
                count += 1
        return count

    def run_once(self) -> int:
        """Claim and run every due job (up to each kind's limit). Returns the number of jobs run.
        Claimed jobs run one after another; parallel execution is added with research runs."""
        ran = 0
        for kind in self.handlers:
            for job in self.queue.claim(kind, self.worker_id, self.concurrency.get(kind, 1)):
                self._run_job(job)
                ran += 1
        return ran

    def _run_job(self, job: dict) -> None:
        handler = self.handlers[job["kind"]]
        stop = threading.Event()
        beat = threading.Thread(target=self._heartbeat_loop, args=(job["id"], stop), daemon=True)
        beat.start()
        try:
            handler.run(job)
        except PermanentJobError as exc:
            self.queue.fail(job, str(exc), permanent=True)
            handler.give_up(job, str(exc))
        except Exception as exc:  # noqa: BLE001 - any other error is retried
            log.exception("Job %s (%s) failed on attempt %s", job["id"], job["kind"], job["attempts"])
            if self.queue.fail(job, f"{type(exc).__name__}: {exc}"):
                handler.give_up(job, "Processing failed after several attempts. Try uploading again.")
        else:
            self.queue.complete(job["id"])
        finally:
            stop.set()
            beat.join(timeout=1)

    def _heartbeat_loop(self, job_id: str, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            try:
                self.queue.heartbeat(job_id)
            except Exception:  # noqa: BLE001 - a missed heartbeat must not kill the job
                log.warning("Heartbeat failed for job %s", job_id)

    async def run_forever(self, stop: asyncio.Event) -> None:
        log.info("Job worker %s started (kinds: %s)", self.worker_id, ", ".join(self.handlers))
        try:
            await asyncio.to_thread(self.recover_stale)
        except Exception:  # noqa: BLE001
            log.exception("Stale job recovery failed")
        while not stop.is_set():
            try:
                ran = await asyncio.to_thread(self.run_once)
            except Exception:  # noqa: BLE001 - e.g. DB unreachable: keep polling
                log.exception("Job worker poll failed")
                ran = 0
            if not ran:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
                except asyncio.TimeoutError:
                    pass
        log.info("Job worker %s stopped", self.worker_id)
