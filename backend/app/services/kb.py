"""Knowledge base management use cases (D4, D35). Called by `app/api/kb.py` after the role check.

Writes use the admin client (service key). Reads for regular users go through their own client, so
RLS decides what they see (current, indexed documents only).

Version model (one `documents` row per file version):
- upload   → new row, `is_current = true`, status `uploaded`, job queued.
- replace  → new row `version + 1`, `replaces_document_id = old`, `is_current = false` until indexed;
             then `promote_document_version` archives the old one in the same transaction.
- delete   → soft delete of the whole chain (`deleted_at`, not current), chunks + files removed.
             Rows stay so future briefing sources can still name the document (D4).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import get_settings
from app.rag.embeddings import GeminiEmbedder
from app.rag.extractors import ExtractionError, suffix_of, validate_upload
from app.rag.ingest import checksum_of
from app.rag.retrieval import RetrievedChunk, retrieve
from app.workers.ingestion import INGEST_KIND
from app.workers.jobs import JobQueue

log = logging.getLogger(__name__)

ADMIN_FIELDS = ("id,title,file_name,mime_type,size_bytes,status,error_message,version,is_current,"
                "replaces_document_id,uploaded_by,indexed_at,archived_at,created_at,updated_at")
USER_FIELDS = "id,title,file_name,mime_type,size_bytes,version,indexed_at,updated_at"
PENDING = ("uploaded", "processing")


class KBError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code, self.message = status_code, message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class KnowledgeBaseService:
    db: Client                      # admin client
    queue: JobQueue
    bucket: str
    max_bytes: int

    @classmethod
    def create(cls, db: Client) -> "KnowledgeBaseService":
        s = get_settings()
        return cls(db=db, queue=JobQueue(db), bucket=s.kb_bucket, max_bytes=s.kb_max_upload_mb * 1024 * 1024)

    # ------------------------------------------------------------ writes (admin)
    def upload(self, file_name: str, raw: bytes, admin_id: str) -> dict:
        mime = self._validate(file_name, raw)
        file_name = file_name.strip()
        checksum = checksum_of(raw)
        for other in self._live_rows_named(file_name):
            if other.get("checksum") == checksum:
                raise KBError(409, f"An identical file named '{file_name}' is already in the knowledge base.")
            raise KBError(409, f"A document named '{file_name}' already exists. Use replace to upload "
                               "a new version.")
        doc_id = str(uuid.uuid4())
        row = {"id": doc_id, "title": file_name, "file_name": file_name, "mime_type": mime,
               "size_bytes": len(raw), "checksum": checksum, "status": "uploaded", "version": 1,
               "is_current": True, "uploaded_by": admin_id,
               "storage_path": f"{doc_id}/original{suffix_of(file_name)}"}
        return self._store_and_queue(row, raw, admin_id)

    def replace(self, doc_id: str, file_name: str, raw: bytes, admin_id: str) -> dict:
        old = self._live_row(doc_id)
        if not old["is_current"]:
            raise KBError(409, "Only the current version of a document can be replaced.")
        if old["status"] in PENDING:
            raise KBError(409, "The document is still being processed. Try again when it is indexed or failed.")
        mime = self._validate(file_name, raw)
        file_name = file_name.strip()
        checksum = checksum_of(raw)
        if checksum == old.get("checksum"):
            raise KBError(409, "The new file is identical to the current version.")

        pending = (self.db.table("documents").select("id,status").eq("replaces_document_id", doc_id)
                   .is_("deleted_at", "null").is_("archived_at", "null").eq("is_current", False)
                   .execute().data or [])
        if any(p["status"] in PENDING for p in pending):
            raise KBError(409, "A new version of this document is already being processed.")
        for p in pending:   # earlier failed replacement attempts: discard them
            self._soft_delete([p["id"]], admin_id)
        if any(r["id"] != doc_id for r in self._live_rows_named(file_name)):
            raise KBError(409, f"Another document named '{file_name}' already exists.")

        new_id = str(uuid.uuid4())
        row = {"id": new_id, "title": old["title"], "file_name": file_name, "mime_type": mime,
               "size_bytes": len(raw), "checksum": checksum, "status": "uploaded",
               "version": old["version"] + 1, "replaces_document_id": doc_id, "is_current": False,
               "uploaded_by": admin_id, "storage_path": f"{new_id}/original{suffix_of(file_name)}"}
        return self._store_and_queue(row, raw, admin_id)

    def delete(self, doc_id: str, admin_id: str) -> list[str]:
        """Deletes a document with all its versions (or only a pending/failed new version).
        Returns the ids marked deleted."""
        doc = self._live_row(doc_id)
        if doc["is_current"]:
            ids = self._chain_ids(doc)
        elif doc.get("archived_at"):
            raise KBError(409, "Archived versions are removed together with the current document.")
        else:
            ids = [doc_id]   # a replacement that was never promoted
        rows = self.db.table("documents").select("id,storage_path").in_("id", ids).execute().data or []
        self._soft_delete(ids, admin_id)   # hidden from search right away (not current)
        self.db.table("corporate_documents").delete().in_("document_id", ids).execute()
        for i in ids:
            self.queue.cancel_for_document(i)
        paths = [r["storage_path"] for r in rows if r.get("storage_path")]
        if paths:
            try:
                self.db.storage.from_(self.bucket).remove(paths)
            except Exception:  # noqa: BLE001 - the rows are already deleted; an orphan file is harmless
                log.warning("Could not remove %d stored file(s) for document %s", len(paths), doc_id)
        log.info("Admin %s deleted document %s (%d versions)", admin_id, doc_id, len(ids))
        return ids

    # ------------------------------------------------------------ reads
    def list_documents(self, user_db: Client | None, is_admin: bool) -> list[dict]:
        if is_admin:
            return (self.db.table("documents").select(ADMIN_FIELDS).is_("deleted_at", "null")
                    .is_("archived_at", "null").order("created_at", desc=True).execute().data or [])
        # RLS: current + indexed only.
        return user_db.table("documents").select(USER_FIELDS).order("title").execute().data or []

    def get_document(self, doc_id: str, user_db: Client | None, is_admin: bool) -> dict:
        if not is_admin:
            rows = user_db.table("documents").select(USER_FIELDS).eq("id", doc_id).limit(1).execute().data
            if not rows:
                raise KBError(404, "Document not found.")
            return rows[0]
        rows = (self.db.table("documents").select(ADMIN_FIELDS).eq("id", doc_id)
                .is_("deleted_at", "null").limit(1).execute().data)
        if not rows:
            raise KBError(404, "Document not found.")
        doc = rows[0]
        history = self._chain_ids(doc) if doc["is_current"] else [doc_id]
        doc["versions"] = (self.db.table("documents")
                           .select("id,version,file_name,status,is_current,indexed_at,archived_at,created_at")
                           .in_("id", history).order("version", desc=True).execute().data or [])
        jobs = (self.db.table("jobs").select("id,status,attempts,max_attempts,error,created_at,finished_at")
                .eq("payload->>document_id", doc_id).order("created_at", desc=True).limit(1).execute().data)
        doc["latest_job"] = jobs[0] if jobs else None
        return doc

    @staticmethod
    def search(user_db: Client, embedder: GeminiEmbedder, query: str, k: int) -> list[RetrievedChunk]:
        """Test search box: the same hybrid search the agents use, with the caller's RLS."""
        return retrieve(user_db, embedder, query, k=k)

    # ------------------------------------------------------------ helpers
    def _validate(self, file_name: str, raw: bytes) -> str:
        if len(raw) > self.max_bytes:
            raise KBError(413, f"The file is larger than {self.max_bytes // (1024 * 1024)} MB.")
        try:
            return validate_upload(file_name, raw, self.max_bytes)
        except ExtractionError as exc:
            raise KBError(400, str(exc)) from exc

    def _store_and_queue(self, row: dict, raw: bytes, admin_id: str) -> dict:
        try:
            doc = self.db.table("documents").insert(row).execute().data[0]
        except APIError as exc:
            if exc.code == "23505":   # unique current file name: a parallel upload won
                raise KBError(409, f"A document named '{row['file_name']}' already exists.") from exc
            raise
        try:
            self.db.storage.from_(self.bucket).upload(
                row["storage_path"], raw, {"content-type": row["mime_type"], "upsert": "false"})
        except Exception as exc:
            self.db.table("documents").delete().eq("id", doc["id"]).execute()
            log.warning("Storage upload failed for %s: %s", row["file_name"], type(exc).__name__)
            raise KBError(502, "The file could not be stored. Try again.") from exc
        try:
            self.queue.enqueue(INGEST_KIND, {"document_id": doc["id"]}, created_by=admin_id)
        except Exception as exc:
            self.db.table("documents").update({"status": "failed", "updated_at": _now(),
                                               "error_message": "Could not queue the file for processing."}
                                              ).eq("id", doc["id"]).execute()
            raise KBError(502, "The file was stored but could not be queued. Upload it again.") from exc
        log.info("Admin %s uploaded %s v%s", admin_id, row["file_name"], row["version"])
        return {k: doc.get(k) for k in ADMIN_FIELDS.split(",")}

    def _live_row(self, doc_id: str) -> dict:
        try:
            uuid.UUID(doc_id)
        except ValueError as exc:
            raise KBError(404, "Document not found.") from exc
        rows = (self.db.table("documents").select("*").eq("id", doc_id).is_("deleted_at", "null")
                .limit(1).execute().data)
        if not rows:
            raise KBError(404, "Document not found.")
        return rows[0]

    def _live_rows_named(self, file_name: str) -> list[dict]:
        """Non-deleted, non-archived rows with this name: current docs and pending/failed new versions."""
        return (self.db.table("documents").select("id,checksum,status,is_current").eq("file_name", file_name)
                .is_("deleted_at", "null").is_("archived_at", "null").execute().data or [])

    def _chain_ids(self, current: dict) -> list[str]:
        """The current version, its archived predecessors and any unpromoted new versions."""
        ids, prev = [current["id"]], current.get("replaces_document_id")
        while prev and prev not in ids:
            ids.append(prev)
            rows = self.db.table("documents").select("replaces_document_id").eq("id", prev).limit(1).execute().data
            prev = rows[0]["replaces_document_id"] if rows else None
        pending = (self.db.table("documents").select("id").eq("replaces_document_id", current["id"])
                   .eq("is_current", False).is_("archived_at", "null").is_("deleted_at", "null")
                   .execute().data or [])
        return ids + [p["id"] for p in pending]

    def _soft_delete(self, ids: list[str], admin_id: str) -> None:
        self.db.table("documents").update({"deleted_at": _now(), "deleted_by": admin_id, "is_current": False,
                                           "updated_at": _now()}).in_("id", ids).execute()
