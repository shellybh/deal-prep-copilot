"""Knowledge base API (D35). A Knowledge Base management screen is future work.

- Everyone signed in: list current indexed documents, open one, test search (read-only, RLS applies).
- Admin only: upload, replace, delete; also sees processing/failed documents, failure reasons, versions.
Uploads return 202: indexing runs in the job worker (D14), clients poll the document status.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user, require_admin
from app.db.clients import get_admin_client, get_user_client
from app.rag.embeddings import GeminiEmbedder, EmbeddingError
from app.services.kb import KBError, KnowledgeBaseService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/kb", tags=["knowledge-base"])


def get_kb_service() -> KnowledgeBaseService:
    return KnowledgeBaseService.create(get_admin_client())


@lru_cache
def get_embedder() -> GeminiEmbedder:
    return GeminiEmbedder()


def _user_db(user: CurrentUser):
    return None if user.is_admin else get_user_client(user.access_token)


def _http(exc: KBError) -> HTTPException:
    return HTTPException(exc.status_code, exc.message)


def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    limit = get_settings().kb_max_upload_mb * 1024 * 1024
    raw = file.file.read(limit + 1)   # never read more than limit + 1 bytes into memory
    if len(raw) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"The file is larger than {get_settings().kb_max_upload_mb} MB.")
    return (file.filename or "").strip(), raw


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


class SearchHit(BaseModel):
    citation: str
    document_id: str
    file_name: str
    title: str
    version: int
    section: str
    content: str
    score: float


@router.get("/documents")
def list_documents(user: CurrentUser = Depends(get_current_user),
                   kb: KnowledgeBaseService = Depends(get_kb_service)) -> dict:
    return {"documents": kb.list_documents(_user_db(user), user.is_admin)}


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, user: CurrentUser = Depends(get_current_user),
                 kb: KnowledgeBaseService = Depends(get_kb_service)) -> dict:
    try:
        return kb.get_document(doc_id, _user_db(user), user.is_admin)
    except KBError as exc:
        raise _http(exc) from exc


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
def upload_document(file: UploadFile = File(...), admin: CurrentUser = Depends(require_admin),
                    kb: KnowledgeBaseService = Depends(get_kb_service)) -> dict:
    name, raw = _read_upload(file)
    try:
        return kb.upload(name, raw, admin.id)
    except KBError as exc:
        raise _http(exc) from exc


@router.post("/documents/{doc_id}/replace", status_code=status.HTTP_202_ACCEPTED)
def replace_document(doc_id: str, file: UploadFile = File(...), admin: CurrentUser = Depends(require_admin),
                     kb: KnowledgeBaseService = Depends(get_kb_service)) -> dict:
    name, raw = _read_upload(file)
    try:
        return kb.replace(doc_id, name, raw, admin.id)
    except KBError as exc:
        raise _http(exc) from exc


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, admin: CurrentUser = Depends(require_admin),
                    kb: KnowledgeBaseService = Depends(get_kb_service)) -> dict:
    try:
        return {"deleted_ids": kb.delete(doc_id, admin.id)}
    except KBError as exc:
        raise _http(exc) from exc


@router.post("/search")
def search(body: SearchRequest, user: CurrentUser = Depends(get_current_user)) -> dict:
    # Everyone (admins too) searches with their own token, so results match what RLS allows.
    try:
        chunks = KnowledgeBaseService.search(get_user_client(user.access_token), get_embedder(),
                                             body.query, body.k)
    except EmbeddingError as exc:
        log.warning("KB search embedding failed: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Search is temporarily unavailable.") from exc
    return {"query": body.query, "results": [SearchHit(
        citation=c.citation, document_id=c.document_id, file_name=c.file_name, title=c.title,
        version=c.version, section=c.section, content=c.content, score=round(c.score, 4),
    ).model_dump() for c in chunks]}
