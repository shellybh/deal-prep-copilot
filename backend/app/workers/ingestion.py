"""Ingestion job handler: download the original from Storage, then `Ingestor.index_document`."""
from __future__ import annotations

import logging

from supabase import Client

from app.core.config import get_settings
from app.rag.embeddings import GeminiEmbedder
from app.rag.ingest import Ingestor
from app.workers.jobs import JobQueue, PermanentJobError, Worker

log = logging.getLogger(__name__)

INGEST_KIND = "ingest_document"


class IngestionHandler:
    def __init__(self, db: Client, ingestor: Ingestor, bucket: str | None = None):
        self.db, self.ingestor = db, ingestor
        self.bucket = bucket or get_settings().kb_bucket

    def run(self, job: dict) -> None:
        doc_id = job["payload"]["document_id"]
        rows = self.db.table("documents").select("*").eq("id", doc_id).limit(1).execute().data
        if not rows or rows[0].get("deleted_at"):
            log.info("Ingestion job %s skipped: document %s was deleted", job["id"], doc_id)
            return
        doc = rows[0]
        if not doc.get("storage_path"):
            raise PermanentJobError("The original file is missing from storage.")
        raw = self.db.storage.from_(self.bucket).download(doc["storage_path"])  # errors are retried
        result = self.ingestor.index_document(doc, raw)
        if result.status == "failed":
            # Already recorded on the document. A bad file won't get better on retry.
            raise PermanentJobError(result.error or "indexing failed")

    def give_up(self, job: dict, error: str) -> None:
        doc_id = job["payload"].get("document_id")
        if doc_id:
            rows = self.db.table("documents").select("status").eq("id", doc_id).limit(1).execute().data
            if rows and rows[0]["status"] != "indexed":
                self.ingestor.mark_failed(doc_id, error)


def build_worker(db: Client, embedder: GeminiEmbedder | None = None) -> Worker:
    s = get_settings()
    ingestor = Ingestor(db, embedder or GeminiEmbedder())
    return Worker(queue=JobQueue(db), handlers={INGEST_KIND: IngestionHandler(db, ingestor)},
                  concurrency={INGEST_KIND: s.ingest_concurrency}, poll_seconds=s.worker_poll_seconds,
                  stale_seconds=s.job_stale_seconds)
