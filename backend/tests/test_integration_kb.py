"""Live Phase 2A checks against the dev project (python -m pytest -m integration).
Needs the sample KB ingested (python ingest_data.py) and GEMINI_API_KEY. Uses a few embedding calls.
"""
from __future__ import annotations

import secrets
import uuid

import pytest
from supabase import ClientOptions, create_client

from app.core.config import get_settings
from app.db.clients import get_admin_client, get_user_client
from app.rag.embeddings import GeminiEmbedder
from app.rag.ingest import Ingestor
from app.tools import search_internal_docs

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def embedder():
    return GeminiEmbedder()


def test_every_chunk_has_citation_metadata():
    rows = get_admin_client().table("corporate_documents").select("metadata").execute().data
    assert rows, "KB is empty: run python ingest_data.py"
    for r in rows:
        m = r["metadata"]
        assert m.get("file_name") and m.get("section") and isinstance(m.get("chunk_index"), int)
        assert m.get("document_id") and m.get("version")


def test_sample_kb_is_fully_indexed():
    docs = get_admin_client().table("documents").select("file_name,status").eq("is_current", True).execute().data
    names = {d["file_name"] for d in docs if d["status"] == "indexed"}
    assert len(names) >= 16 and "crm_historical_win_loss_data_2025_2026.csv" in names


def test_ingest_is_idempotent_and_searchable(tmp_path, embedder):
    db = get_admin_client()
    marker = f"Zephyrquark{uuid.uuid4().hex[:6]}"
    path = tmp_path / f"itest_{marker}.md"
    path.write_text(f"# Integration Test Doc\n\n## Secret Product\n\nThe {marker} module ships in Q3.\n",
                    encoding="utf-8")
    ingestor = Ingestor(db, embedder)
    try:
        first = ingestor.ingest(path)
        second = ingestor.ingest(path)
        assert first.status == "indexed" and first.chunks >= 1
        assert second.status == "unchanged"
        doc = db.table("documents").select("id").eq("file_name", path.name).execute().data
        assert len(doc) == 1
        chunks = db.table("corporate_documents").select("id").eq("document_id", doc[0]["id"]).execute().data
        assert len(chunks) == first.chunks

        hits = search_internal_docs(f"When does {marker} ship?", k=3)
        assert hits[0]["file_name"] == path.name
        assert hits[0]["citation"] == f"{path.name} § Integration Test Doc > Secret Product"
    finally:
        db.table("documents").delete().eq("file_name", path.name).execute()  # chunks cascade


def test_search_internal_docs_returns_citations():
    hits = search_internal_docs("How do we beat QuantaLake on total cost of ownership?")
    assert len(hits) == 5
    assert hits[0]["file_name"] == "battlecard_quantalake.md"
    assert {"citation", "section", "document_id", "version", "score", "content"} <= hits[0].keys()


def test_hebrew_query_finds_english_document():
    hits = search_internal_docs("מה זמן התגובה לתקלת P1 בחבילת Enterprise?", k=3)
    assert hits[0]["file_name"] == "pricing_enterprise_Q4_2026.md"


def test_rls_signed_in_user_can_search_but_not_write(embedder):
    admin = get_admin_client()
    s = get_settings()
    email, password = f"kb-test-{uuid.uuid4().hex[:8]}@example.com", secrets.token_urlsafe(16)
    uid = admin.auth.admin.create_user({"email": email, "password": password, "email_confirm": True}).user.id
    try:
        anon = create_client(s.supabase_url, s.supabase_anon_key,
                             options=ClientOptions(auto_refresh_token=False, persist_session=False))
        token = anon.auth.sign_in_with_password({"email": email, "password": password}).session.access_token
        user_db = get_user_client(token)
        from app.rag.retrieval import retrieve
        assert retrieve(user_db, embedder, "QuantaLake pricing", k=3)  # RLS allows reads
        with pytest.raises(Exception, match="(?i)permission denied"):
            user_db.table("documents").insert({"title": "x", "file_name": "x.md"}).execute()
        with pytest.raises(Exception, match="(?i)permission denied"):
            user_db.table("corporate_documents").delete().gte("id", 0).execute()
    finally:
        admin.auth.admin.delete_user(uid)


def test_anon_cannot_read_or_search():
    s = get_settings()
    anon = create_client(s.supabase_url, s.supabase_anon_key,
                         options=ClientOptions(auto_refresh_token=False, persist_session=False))
    with pytest.raises(Exception, match="(?i)permission denied"):
        anon.table("corporate_documents").select("id").limit(1).execute()
    with pytest.raises(Exception, match="(?i)permission denied"):
        anon.rpc("hybrid_search", {"query_text": "x", "query_embedding": "[" + ",".join(["0"] * 1536) + "]"}).execute()
