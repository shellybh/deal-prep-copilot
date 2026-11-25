"""Live Phase 2C checks against the dev project (python -m pytest -m integration).
Needs migration 20261107120000_kb_management.sql and GEMINI_API_KEY. Uses a few embedding calls.

Goes through the real API with real tokens (throwaway admin + regular user, no email sent), runs the job
worker with run_once(), and removes every row, job and stored file it created.
"""
from __future__ import annotations

import io
import secrets
import uuid
from pathlib import Path

import docx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from supabase import ClientOptions, create_client

from app.core.config import get_settings
from app.db.clients import get_admin_client, get_user_client
from app.main import app
from app.workers.ingestion import INGEST_KIND, build_worker
from app.workers.jobs import JobQueue

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


def _marker() -> str:
    return f"Quorvex{uuid.uuid4().hex[:8]}"


def _md(marker: str, version: str) -> bytes:
    return f"# Itest Guide {version}\n\n## Launch\n\nThe {marker} module launches in {version}.\n".encode()


def _docx(marker: str) -> bytes:
    d = docx.Document()
    d.add_heading("Itest Word Guide", level=0)
    d.add_heading("Launch", level=1)
    d.add_paragraph(f"The {marker} module launches in Q4 per the Word version.")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _blank_pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def users():
    admin = get_admin_client()
    s = get_settings()
    created = {}
    try:
        for role in ("user", "admin"):
            email, password = f"kb2c-{role}-{uuid.uuid4().hex[:8]}@example.com", secrets.token_urlsafe(16)
            uid = admin.auth.admin.create_user({"email": email, "password": password, "email_confirm": True}).user.id
            if role == "admin":
                admin.table("profiles").update({"role": "admin"}).eq("id", uid).execute()
            anon = create_client(s.supabase_url, s.supabase_anon_key,
                                 options=ClientOptions(auto_refresh_token=False, persist_session=False))
            token = anon.auth.sign_in_with_password({"email": email, "password": password}).session.access_token
            created[role] = {"id": uid, "headers": {"Authorization": f"Bearer {token}"}, "token": token}
        yield created
    finally:
        for u in created.values():
            admin.auth.admin.delete_user(u["id"])


@pytest.fixture(scope="module")
def worker():
    return build_worker(get_admin_client())


@pytest.fixture
def cleanup():
    """Collects document ids; removes rows (chunks cascade), jobs and stored files afterwards."""
    ids: list[str] = []
    yield ids
    db = get_admin_client()
    for doc_id in ids:
        rows = db.table("documents").select("id,storage_path").or_(
            f"id.eq.{doc_id},replaces_document_id.eq.{doc_id}").execute().data or []
        all_ids = {r["id"] for r in rows} | {doc_id}
        paths = [r["storage_path"] for r in rows if r.get("storage_path")]
        if paths:
            db.storage.from_(get_settings().kb_bucket).remove(paths)
        for i in all_ids:
            db.table("jobs").delete().eq("payload->>document_id", i).execute()
        # Newer versions point at older ones: clear the links, then delete.
        db.table("documents").update({"replaces_document_id": None}).in_("id", list(all_ids)).execute()
        db.table("documents").delete().in_("id", list(all_ids)).execute()


def _upload(headers, name, raw, doc_id=None):
    url = f"/api/kb/documents/{doc_id}/replace" if doc_id else "/api/kb/documents"
    return client.post(url, headers=headers, files={"file": (name, raw)})


def _search(headers, query, k=3):
    r = client.post("/api/kb/search", headers=headers, json={"query": query, "k": k})
    assert r.status_code == 200, r.text
    return r.json()["results"]


def _doc(doc_id):
    return get_admin_client().table("documents").select("*").eq("id", doc_id).single().execute().data


# ---------------------------------------------------------------- tests
def test_upload_index_search_and_visibility(users, worker, cleanup):
    marker = _marker()
    name = f"itest_{marker}.md"
    r = _upload(users["admin"]["headers"], name, _md(marker, "Q3"))
    assert r.status_code == 202, r.text
    doc_id = r.json()["id"]
    cleanup.append(doc_id)
    assert r.json()["status"] == "uploaded"

    # Not visible to regular users before it is indexed.
    listed = client.get("/api/kb/documents", headers=users["user"]["headers"]).json()["documents"]
    assert doc_id not in {d["id"] for d in listed}

    assert worker.run_once() >= 1
    doc = _doc(doc_id)
    assert doc["status"] == "indexed" and doc["is_current"] and doc["storage_path"] == f"{doc_id}/original.md"

    hits = _search(users["user"]["headers"], f"When does {marker} launch?")
    assert hits[0]["document_id"] == doc_id and hits[0]["citation"].endswith("Itest Guide Q3 > Launch")
    listed = client.get("/api/kb/documents", headers=users["user"]["headers"]).json()["documents"]
    mine = next(d for d in listed if d["id"] == doc_id)
    assert "error_message" not in mine and "status" not in mine          # user fields only

    detail = client.get(f"/api/kb/documents/{doc_id}", headers=users["admin"]["headers"]).json()
    assert detail["latest_job"]["status"] == "succeeded" and len(detail["versions"]) == 1

    dup = _upload(users["admin"]["headers"], name, _md(marker, "Q3"))
    assert dup.status_code == 409 and "identical" in dup.json()["detail"]
    other = _upload(users["admin"]["headers"], name, _md(marker, "Q9"))
    assert other.status_code == 409 and "replace" in other.json()["detail"]


def test_scanned_pdf_fails_and_is_hidden_from_users(users, worker, cleanup):
    name = f"itest_scan_{uuid.uuid4().hex[:6]}.pdf"
    r = _upload(users["admin"]["headers"], name, _blank_pdf())
    assert r.status_code == 202, r.text
    doc_id = r.json()["id"]
    cleanup.append(doc_id)
    worker.run_once()

    doc = _doc(doc_id)
    assert doc["status"] == "failed" and "scanned" in doc["error_message"]
    job = (get_admin_client().table("jobs").select("status,attempts").eq("payload->>document_id", doc_id)
           .single().execute().data)
    assert job == {"status": "failed", "attempts": 1}                    # permanent: no retries

    admin_list = client.get("/api/kb/documents", headers=users["admin"]["headers"]).json()["documents"]
    assert next(d for d in admin_list if d["id"] == doc_id)["error_message"]
    user_list = client.get("/api/kb/documents", headers=users["user"]["headers"]).json()["documents"]
    assert doc_id not in {d["id"] for d in user_list}
    assert client.get(f"/api/kb/documents/{doc_id}", headers=users["user"]["headers"]).status_code == 404


def test_replace_keeps_old_version_searchable_until_new_is_indexed(users, worker, cleanup):
    old_marker, new_marker = _marker(), _marker()
    r = _upload(users["admin"]["headers"], f"itest_{old_marker}.md", _md(old_marker, "Q3"))
    v1 = r.json()["id"]
    cleanup.append(v1)
    worker.run_once()

    r = _upload(users["admin"]["headers"], f"itest_{old_marker}.docx", _docx(new_marker), doc_id=v1)
    assert r.status_code == 202, r.text
    v2 = r.json()["id"]
    assert r.json()["version"] == 2 and r.json()["is_current"] is False

    # Before the worker runs: v1 still current and searchable, v2 not visible.
    hits = _search(users["user"]["headers"], f"When does {old_marker} launch?")
    assert hits[0]["document_id"] == v1
    again = _upload(users["admin"]["headers"], "x.md", _md(new_marker, "Q5"), doc_id=v1)
    assert again.status_code == 409                                       # one pending version at a time

    worker.run_once()
    old, new = _doc(v1), _doc(v2)
    assert new["is_current"] and new["status"] == "indexed" and new["version"] == 2
    assert not old["is_current"] and old["archived_at"]
    assert get_admin_client().table("corporate_documents").select("id").eq("document_id", v1).execute().data == []

    hits = _search(users["user"]["headers"], f"When does {new_marker} launch?")
    assert hits[0]["document_id"] == v2 and hits[0]["version"] == 2
    assert all(h["document_id"] != v1 for h in _search(users["user"]["headers"], old_marker, k=10))
    detail = client.get(f"/api/kb/documents/{v2}", headers=users["admin"]["headers"]).json()
    assert [v["version"] for v in detail["versions"]] == [2, 1]


def test_delete_removes_chunks_and_file_but_keeps_row(users, worker, cleanup):
    marker = _marker()
    r = _upload(users["admin"]["headers"], f"itest_{marker}.pdf", (FIXTURES / "kb_sample_he_en.pdf").read_bytes())
    doc_id = r.json()["id"]
    cleanup.append(doc_id)
    worker.run_once()
    doc = _doc(doc_id)
    assert doc["status"] == "indexed", doc["error_message"]
    hits = _search(users["user"]["headers"], "הנחה לשותפים על חבילת Enterprise", k=5)
    assert any(h["document_id"] == doc_id and h["section"] == "Page 2" for h in hits)

    assert client.delete(f"/api/kb/documents/{doc_id}", headers=users["user"]["headers"]).status_code == 403
    r = client.delete(f"/api/kb/documents/{doc_id}", headers=users["admin"]["headers"])
    assert r.status_code == 200 and r.json()["deleted_ids"] == [doc_id]

    doc = _doc(doc_id)
    assert doc["deleted_at"] and not doc["is_current"]                   # row kept for citations
    db = get_admin_client()
    assert db.table("corporate_documents").select("id").eq("document_id", doc_id).execute().data == []
    with pytest.raises(Exception):
        db.storage.from_(get_settings().kb_bucket).download(doc["storage_path"])
    assert all(h["document_id"] != doc_id for h in _search(users["user"]["headers"], "Enterprise partners", k=10))
    assert client.get(f"/api/kb/documents/{doc_id}", headers=users["admin"]["headers"]).status_code == 404


def test_regular_user_has_no_direct_access_to_jobs_or_storage(users):
    db = get_user_client(users["user"]["token"])
    with pytest.raises(Exception, match="(?i)permission denied"):
        db.table("jobs").select("id").limit(1).execute()
    with pytest.raises(Exception, match="(?i)permission denied"):
        db.rpc("claim_jobs", {"p_kind": INGEST_KIND, "p_worker": "x", "p_max_running": 1}).execute()
    try:                                                               # private bucket, no policies:
        listed = db.storage.from_(get_settings().kb_bucket).list()     # empty list or an error
    except Exception:  # noqa: BLE001
        listed = []
    assert listed == []
    r = _upload(users["user"]["headers"], "x.md", b"# x")
    assert r.status_code == 403


def test_claim_respects_concurrency_limit():
    db = get_admin_client()
    queue = JobQueue(db)
    fake_ids = [str(uuid.uuid4()) for _ in range(2)]
    jobs = [queue.enqueue(INGEST_KIND, {"document_id": i}) for i in fake_ids]
    try:
        first = queue.claim(INGEST_KIND, "itest", max_running=1)
        assert len(first) == 1 and first[0]["status"] == "running" and first[0]["attempts"] == 1
        assert queue.claim(INGEST_KIND, "itest", max_running=1) == []    # limit reached
        queue.complete(first[0]["id"])
        second = queue.claim(INGEST_KIND, "itest", max_running=1)
        assert len(second) == 1 and second[0]["id"] != first[0]["id"]
        queue.complete(second[0]["id"])
    finally:
        for j in jobs:
            db.table("jobs").delete().eq("id", j["id"]).execute()
