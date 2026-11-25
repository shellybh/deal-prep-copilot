"""Ingest one file version into documents + corporate_documents. Backend/admin only (service key).

Two entry points share one core (`index_document`):
- `ingest(path)`: seed CLI (`ingest_data.py`). Idempotent per file name: an unchanged file (same
  checksum, chunking and embedding model) is skipped; a changed one gets its chunks replaced.
- `index_document(doc, raw)`: Phase 2C job runner, for an uploaded or replacement version that already
  has a `documents` row. A replacement (not yet current) is promoted only after it is indexed, so the
  old version stays searchable until then (`promote_document_version`, one transaction).

Embeddings are computed before anything is deleted, so a failed call leaves a previously indexed
version searchable. Failures are recorded on the document (`status = failed`, `error_message`).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath

from supabase import Client

from app.core.config import get_settings
from app.rag.chunking import (MARKDOWN_CHUNK_OVERLAP, MARKDOWN_CHUNK_SIZE, Chunk, chunk_csv, chunk_text,
                              markdown_title)
from app.rag.embeddings import GeminiEmbedder, to_pgvector
from app.rag.extractors import MIME_TYPES, ExtractionError, Extracted, extract, suffix_of

log = logging.getLogger(__name__)

SUPPORTED = MIME_TYPES
INSERT_BATCH = 50


@dataclass
class IngestResult:
    file_name: str
    status: str            # indexed | unchanged | failed
    chunks: int = 0
    error: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def checksum_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def document_title(file_name: str, extracted: Extracted) -> str:
    fallback = PurePath(file_name).stem.replace("_", " ").strip() or file_name
    if extracted.title:
        return extracted.title
    return markdown_title(extracted.text, fallback) if extracted.kind == "markdown" else fallback


def embedding_text(title: str, chunk: Chunk) -> str:
    """Text sent to the embedding model: document title + section give cut-off chunks their context.
    The stored `content` stays the raw chunk."""
    return f"{title}\n{chunk.section}\n\n{chunk.content}"


class Ingestor:
    def __init__(self, db: Client, embedder: GeminiEmbedder, strategy: str | None = None,
                 max_chunks: int | None = None):
        s = get_settings()
        self.db, self.embedder = db, embedder
        self.strategy = strategy or s.chunking_strategy
        self.chunk_size, self.chunk_overlap = s.chunk_size, s.chunk_overlap
        self.max_chunks = max_chunks or s.kb_max_chunks

    @property
    def chunking_signature(self) -> str:
        if self.strategy == "markdown":
            return f"markdown:{MARKDOWN_CHUNK_SIZE}/{MARKDOWN_CHUNK_OVERLAP}"
        return f"fixed:{self.chunk_size}/{self.chunk_overlap}"

    def chunk_extracted(self, extracted: Extracted) -> list[Chunk]:
        if extracted.kind == "csv":
            return chunk_csv(extracted.text)
        chunks = chunk_text(extracted.text, self.strategy, self.chunk_size, self.chunk_overlap)
        # Plain text without headings has no section: number the parts so every citation has a location.
        return [c if c.section else Chunk(c.content, f"part {i}", c.extra) for i, c in enumerate(chunks, 1)]

    # ------------------------------------------------------------ seed CLI
    def ingest(self, path: Path, force: bool = False) -> IngestResult:
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED:
            return IngestResult(path.name, "failed", error=f"unsupported file type {suffix}")
        raw = path.read_bytes()
        checksum = checksum_of(raw)
        existing = (self.db.table("documents").select("*")
                    .eq("file_name", path.name).eq("is_current", True).execute().data)
        doc = existing[0] if existing else None
        if doc and not force and self._unchanged(doc, checksum):
            return IngestResult(path.name, "unchanged")
        if doc is None:
            doc = self.db.table("documents").insert({
                "title": PurePath(path.name).stem, "file_name": path.name, "mime_type": SUPPORTED[suffix],
                "size_bytes": len(raw), "checksum": checksum, "status": "processing",
            }).execute().data[0]
        return self.index_document(doc, raw)

    # ------------------------------------------------------------ core (CLI + job runner)
    def index_document(self, doc: dict, raw: bytes) -> IngestResult:
        name = doc["file_name"]
        was_indexed = doc.get("status") == "indexed"
        if not was_indexed:
            self._update(doc["id"], status="processing", error_message=None)
        try:
            extracted = extract(name, raw)
            title = document_title(name, extracted)
            chunks = self.chunk_extracted(extracted)
            if not chunks:
                raise ExtractionError("No text found in the file.")
            if len(chunks) > self.max_chunks:
                raise ExtractionError(f"The document is too large to index: {len(chunks)} chunks "
                                      f"(limit {self.max_chunks}). Split it into smaller files.")
            vectors = self.embedder.embed_documents([embedding_text(title, c) for c in chunks])
        except Exception as exc:  # noqa: BLE001 - recorded on the document and reported
            return self._fail(doc, was_indexed, str(exc))

        if self._is_deleted(doc["id"]):
            return IngestResult(name, "failed", error="document was deleted while it was being indexed")

        suffix = suffix_of(name)
        rows = [{
            "document_id": doc["id"],
            "chunk_index": i,
            "content": c.content,
            "metadata": {"file_name": name, "chunk_index": i, "section": c.section,
                         "document_id": doc["id"], "version": doc.get("version", 1),
                         "chunking": "csv-rows" if suffix == ".csv" else self.chunking_signature,
                         **c.extra},
            "embedding": to_pgvector(v),
            "embedding_model": self.embedder.model,
        } for i, (c, v) in enumerate(zip(chunks, vectors))]

        self.db.table("corporate_documents").delete().eq("document_id", doc["id"]).execute()
        for i in range(0, len(rows), INSERT_BATCH):
            self.db.table("corporate_documents").insert(rows[i:i + INSERT_BATCH]).execute()
        self._update(doc["id"], title=title, size_bytes=len(raw), checksum=checksum_of(raw),
                     status="indexed", error_message=None, indexed_at=_now())
        if not doc.get("is_current", True):
            self.db.rpc("promote_document_version", {"p_new_id": doc["id"]}).execute()
        log.info("Indexed %s v%s: %d chunks", name, doc.get("version", 1), len(rows))
        return IngestResult(name, "indexed", chunks=len(rows))

    def mark_failed(self, doc_id: str, error: str) -> None:
        """Used by the job runner when it gives up on a job (e.g. the file can't be downloaded)."""
        self._update(doc_id, status="failed", error_message=error[:500])

    # ------------------------------------------------------------ helpers
    def _fail(self, doc: dict, was_indexed: bool, error: str) -> IngestResult:
        if not was_indexed:   # keep a previously indexed version searchable
            self.mark_failed(doc["id"], error)
        log.warning("Indexing failed for %s: %s", doc["file_name"], error)
        return IngestResult(doc["file_name"], "failed", error=error)

    def _is_deleted(self, doc_id: str) -> bool:
        rows = self.db.table("documents").select("deleted_at").eq("id", doc_id).limit(1).execute().data
        return not rows or rows[0].get("deleted_at") is not None

    def _unchanged(self, doc: dict, checksum: str) -> bool:
        if doc["status"] != "indexed" or doc["checksum"] != checksum:
            return False
        first = (self.db.table("corporate_documents").select("metadata,embedding_model")
                 .eq("document_id", doc["id"]).limit(1).execute().data)
        if not first:
            return False
        signature = first[0]["metadata"].get("chunking")
        return (first[0]["embedding_model"] == self.embedder.model
                and signature in (self.chunking_signature, "csv-rows"))

    def _update(self, doc_id: str, **fields) -> None:
        self.db.table("documents").update({**fields, "updated_at": _now()}).eq("id", doc_id).execute()
