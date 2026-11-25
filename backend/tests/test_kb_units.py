"""Phase 2C unit tests: extractors, upload validation, chunking of extracted text, job runner, ingestion
handler, KB API permissions and error mapping. No network."""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import docx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.api import kb as kb_api
from app.core import security
from app.main import app
from app.rag.extractors import (SCANNED_PDF_MESSAGE, ExtractionError, Extracted, extract, validate_upload)
from app.rag.ingest import Ingestor, document_title
from app.rag.retrieval import RetrievedChunk
from app.services.kb import KBError, KnowledgeBaseService
from app.workers.ingestion import IngestionHandler
from app.workers.jobs import RETRY_BACKOFF_SECONDS, PermanentJobError, Worker

FIXTURES = Path(__file__).parent / "fixtures"
MB = 1024 * 1024


# ---------------------------------------------------------------- helpers
def docx_bytes() -> bytes:
    d = docx.Document()
    d.add_heading("Partner Program", level=0)          # Title style
    d.add_heading("Discounts", level=1)
    d.add_paragraph("Partners get 20% off.")
    d.add_paragraph("Quarterly review", style="List Bullet")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Tier", "Discount"
    t.cell(1, 0).text, t.cell(1, 1).text = "Gold", "20% | annual"
    d.add_heading("תמיכה", level=2)
    d.add_paragraph("זמן תגובה של 4 שעות.")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def blank_pdf_bytes(pages: int = 2) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- extractors
def test_pdf_extraction_marks_pages_and_keeps_hebrew():
    out = extract("guide.pdf", (FIXTURES / "kb_sample_he_en.pdf").read_bytes())
    assert out.kind == "markdown"
    assert "## Page 1" in out.text and "## Page 2" in out.text
    assert "Partners get a 20% discount" in out.text
    for word in ("מדריך", "שותפים", "הנחה", "Enterprise"):   # word order in mixed RTL lines may differ
        assert word in out.text


def test_scanned_pdf_without_text_fails_with_clear_message():
    with pytest.raises(ExtractionError) as exc:
        extract("scan.pdf", blank_pdf_bytes())
    assert str(exc.value) == SCANNED_PDF_MESSAGE
    assert "OCR" in SCANNED_PDF_MESSAGE


def test_corrupt_pdf_fails_cleanly():
    with pytest.raises(ExtractionError, match="could not be read"):
        extract("bad.pdf", b"%PDF-1.7\nthis is not really a pdf")


def test_docx_headings_tables_and_lists_become_markdown():
    out = extract("partners.docx", docx_bytes())
    assert out.title == "Partner Program"
    lines = out.text.splitlines()
    assert "# Partner Program" in lines and "# Discounts" in lines and "## תמיכה" in lines
    assert "- Quarterly review" in lines
    assert "| Tier | Discount |" in lines and "| Gold | 20% \\| annual |" in lines


def test_txt_utf8_and_windows_1255_hebrew():
    assert extract("a.txt", "שלום world".encode("utf-8")).text == "שלום world"
    assert extract("b.txt", "שלום עולם".encode("cp1255")).text == "שלום עולם"
    assert extract("c.txt", "﻿BOM".encode("utf-8")).text == "BOM"


def test_csv_and_md_kinds():
    assert extract("x.csv", b"a,b\n1,2").kind == "csv"
    assert extract("x.md", b"# T\n\nbody").kind == "markdown"


# ---------------------------------------------------------------- upload validation (D35)
@pytest.mark.parametrize("name,raw,match", [
    ("notes.exe", b"MZ", "Unsupported file type"),
    ("noext", b"hello", "Unsupported file type"),
    ("empty.txt", b"", "empty"),
    ("fake.pdf", b"hello", "not a PDF"),
    ("fake.docx", b"PK\x03\x04garbage", "not a Word"),
    ("bin.txt", b"abc\x00def", "binary"),
    ("../evil.md", b"# x", "Invalid file name"),
    ("a" * 201 + ".md", b"# x", "too long"),
])
def test_validate_upload_rejects(name, raw, match):
    with pytest.raises(ExtractionError, match=match):
        validate_upload(name, raw, max_bytes=MB)


def test_validate_upload_size_and_accepts_real_files():
    with pytest.raises(ExtractionError, match="larger than 1 MB"):
        validate_upload("big.txt", b"a" * (MB + 1), max_bytes=MB)
    assert validate_upload("g.pdf", (FIXTURES / "kb_sample_he_en.pdf").read_bytes(), MB) == "application/pdf"
    assert validate_upload("p.DOCX", docx_bytes(), MB).endswith("wordprocessingml.document")
    assert validate_upload("n.md", "# כותרת".encode(), MB) == "text/markdown"


# ---------------------------------------------------------------- ingestor (no DB)
def _ingestor(**kw) -> Ingestor:
    return Ingestor(MagicMock(), SimpleNamespace(model="m"), **kw)


def test_plain_text_chunks_get_part_numbers_as_section():
    chunks = _ingestor(strategy="markdown").chunk_extracted(Extracted("word " * 600, "text"))
    assert len(chunks) > 1
    assert [c.section for c in chunks] == [f"part {i}" for i in range(1, len(chunks) + 1)]


def test_pdf_chunks_cite_the_page():
    ext = extract("g.pdf", (FIXTURES / "kb_sample_he_en.pdf").read_bytes())
    sections = {c.section for c in _ingestor(strategy="markdown").chunk_extracted(ext)}
    assert sections == {"Page 1", "Page 2"}


def test_document_title_rules():
    assert document_title("price_list.pdf", Extracted("## Page 1\n\nx", "markdown")) == "price list"
    assert document_title("a.docx", Extracted("# Doc", "markdown", title="From props")) == "From props"
    assert document_title("a.md", Extracted("# Real Title\n\nx", "markdown")) == "Real Title"


def test_index_document_fails_over_chunk_limit_without_embedding():
    ing = _ingestor(strategy="fixed", max_chunks=2)
    ing.embedder = MagicMock(model="m")
    doc = {"id": "d1", "file_name": "long.txt", "status": "uploaded", "is_current": True}
    result = ing.index_document(doc, (("x" * 400 + "\n\n") * 10).encode())
    assert result.status == "failed" and "too large to index" in result.error
    ing.embedder.embed_documents.assert_not_called()


def test_index_document_failure_keeps_indexed_version_status():
    ing = _ingestor(strategy="markdown")
    calls = []
    ing._update = lambda doc_id, **f: calls.append(f)
    doc = {"id": "d1", "file_name": "scan.pdf", "status": "indexed", "is_current": True}
    assert ing.index_document(doc, blank_pdf_bytes()).status == "failed"
    assert calls == []   # previously indexed version untouched (seed CLI re-ingest)

    doc_new = {"id": "d2", "file_name": "scan.pdf", "status": "uploaded", "is_current": True}
    ing.index_document(doc_new, blank_pdf_bytes())
    assert calls[0]["status"] == "processing" and calls[-1]["status"] == "failed"
    assert "scanned" in calls[-1]["error_message"]


# ---------------------------------------------------------------- job runner
class FakeQueue:
    def __init__(self, jobs):
        self.jobs, self.completed, self.failed = list(jobs), [], []

    def claim(self, kind, worker_id, max_running=1):
        out, self.jobs = self.jobs[:max_running], self.jobs[max_running:]
        return out

    def complete(self, job_id):
        self.completed.append(job_id)

    def fail(self, job, error, permanent=False):
        final = permanent or job["attempts"] >= job["max_attempts"]
        self.failed.append((job["id"], error, final))
        return final

    def heartbeat(self, job_id):
        pass

    def stale_jobs(self, kind, stale_seconds):
        return [j for j in self.jobs if j.get("stale")]


def _job(i, attempts=1, max_attempts=3, **kw):
    return {"id": f"j{i}", "kind": "ingest_document", "attempts": attempts, "max_attempts": max_attempts,
            "payload": {"document_id": f"d{i}"}, **kw}


def test_worker_completes_and_respects_concurrency():
    handler = MagicMock()
    q = FakeQueue([_job(1), _job(2)])
    w = Worker(queue=q, handlers={"ingest_document": handler}, concurrency={"ingest_document": 1})
    assert w.run_once() == 1 and q.completed == ["j1"]
    assert w.run_once() == 1 and q.completed == ["j1", "j2"]
    assert w.run_once() == 0


def test_worker_permanent_error_fails_immediately_and_gives_up():
    handler = MagicMock()
    handler.run.side_effect = PermanentJobError("bad file")
    q = FakeQueue([_job(1)])
    Worker(queue=q, handlers={"ingest_document": handler}).run_once()
    assert q.failed == [("j1", "bad file", True)]
    handler.give_up.assert_called_once()


def test_worker_retries_transient_errors_then_gives_up():
    handler = MagicMock()
    handler.run.side_effect = ConnectionError("storage down")
    q = FakeQueue([_job(1, attempts=1), _job(2, attempts=3)])
    w = Worker(queue=q, handlers={"ingest_document": handler}, concurrency={"ingest_document": 2})
    w.run_once()
    assert q.failed[0][2] is False and q.failed[1][2] is True   # j1 re-queued, j2 out of attempts
    handler.give_up.assert_called_once()


def test_worker_recovers_stale_jobs():
    handler = MagicMock()
    q = FakeQueue([_job(1, attempts=3, stale=True)])
    assert Worker(queue=q, handlers={"ingest_document": handler}).recover_stale() == 1
    handler.give_up.assert_called_once()


def test_retry_backoff_grows():
    assert list(RETRY_BACKOFF_SECONDS) == sorted(RETRY_BACKOFF_SECONDS)


# ---------------------------------------------------------------- ingestion handler
def _handler_db(doc):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = (
        [doc] if doc else [])
    db.storage.from_.return_value.download.return_value = b"# T\n\nbody"
    return db


def test_handler_skips_deleted_document():
    ingestor = MagicMock()
    IngestionHandler(_handler_db({"id": "d1", "deleted_at": "2026-11-07"}), ingestor, "b").run(_job(1))
    ingestor.index_document.assert_not_called()


def test_handler_failed_indexing_is_permanent():
    ingestor = MagicMock()
    ingestor.index_document.return_value = SimpleNamespace(status="failed", error="no text")
    doc = {"id": "d1", "deleted_at": None, "storage_path": "d1/original.md"}
    with pytest.raises(PermanentJobError, match="no text"):
        IngestionHandler(_handler_db(doc), ingestor, "b").run(_job(1))


# ---------------------------------------------------------------- service checks before any write
def _service(max_mb=1):
    db = MagicMock()
    return KnowledgeBaseService(db=db, queue=MagicMock(), bucket="b", max_bytes=max_mb * MB), db


def test_service_rejects_too_large_and_wrong_type_before_writing():
    svc, db = _service()
    with pytest.raises(KBError) as big:
        svc.upload("a.txt", b"a" * (MB + 1), "admin")
    assert big.value.status_code == 413
    with pytest.raises(KBError) as bad:
        svc.upload("a.exe", b"MZ", "admin")
    assert bad.value.status_code == 400
    db.table.return_value.insert.assert_not_called()
    db.storage.from_.assert_not_called()


def test_service_upload_existing_name_is_conflict():
    svc, db = _service()
    (db.table.return_value.select.return_value.eq.return_value.is_.return_value.is_.return_value
     .execute.return_value.data) = [{"id": "x", "checksum": "other", "status": "indexed", "is_current": True}]
    with pytest.raises(KBError, match="Use replace") as exc:
        svc.upload("a.md", b"# new", "admin")
    assert exc.value.status_code == 409


def test_service_unknown_id_is_404():
    svc, _ = _service()
    with pytest.raises(KBError) as exc:
        svc.delete("not-a-uuid", "admin")
    assert exc.value.status_code == 404


# ---------------------------------------------------------------- API: permissions and mapping
client = TestClient(app)


@pytest.fixture
def fake_kb():
    svc = MagicMock(spec=KnowledgeBaseService)
    app.dependency_overrides[kb_api.get_kb_service] = lambda: svc
    yield svc
    app.dependency_overrides.clear()


def as_role(role):
    app.dependency_overrides[security.get_current_user] = lambda: security.CurrentUser(
        id=f"{role}-id", email=None, role=role, access_token="tok")


def test_kb_endpoints_require_login(fake_kb):
    assert client.get("/api/kb/documents").status_code == 401
    assert client.post("/api/kb/search", json={"query": "x"}).status_code == 401
    assert client.post("/api/kb/documents", files={"file": ("a.md", b"# a")}).status_code == 401


def test_regular_user_cannot_manage_documents(fake_kb):
    as_role("user")
    assert client.post("/api/kb/documents", files={"file": ("a.md", b"# a")}).status_code == 403
    assert client.post("/api/kb/documents/x/replace", files={"file": ("a.md", b"# a")}).status_code == 403
    assert client.delete("/api/kb/documents/x").status_code == 403
    fake_kb.upload.assert_not_called()
    fake_kb.replace.assert_not_called()
    fake_kb.delete.assert_not_called()


def test_regular_user_lists_with_own_client(fake_kb, monkeypatch):
    as_role("user")
    monkeypatch.setattr(kb_api, "get_user_client", lambda token: f"user-db:{token}")
    fake_kb.list_documents.return_value = [{"id": "d1"}]
    assert client.get("/api/kb/documents").json() == {"documents": [{"id": "d1"}]}
    fake_kb.list_documents.assert_called_once_with("user-db:tok", False)


def test_admin_upload_returns_202_and_maps_errors(fake_kb):
    as_role("admin")
    fake_kb.upload.return_value = {"id": "d1", "status": "uploaded"}
    r = client.post("/api/kb/documents", files={"file": ("a.md", "# שלום".encode())})
    assert r.status_code == 202 and r.json()["status"] == "uploaded"
    fake_kb.upload.assert_called_once_with("a.md", "# שלום".encode(), "admin-id")

    fake_kb.upload.side_effect = KBError(409, "exists")
    r = client.post("/api/kb/documents", files={"file": ("a.md", b"# a")})
    assert r.status_code == 409 and r.json()["detail"] == "exists"


def test_upload_over_limit_is_413_before_service(fake_kb, monkeypatch):
    as_role("admin")
    monkeypatch.setattr(kb_api, "get_settings", lambda: SimpleNamespace(kb_max_upload_mb=1))
    r = client.post("/api/kb/documents", files={"file": ("a.txt", b"a" * (MB + 1))})
    assert r.status_code == 413
    fake_kb.upload.assert_not_called()


def test_search_uses_callers_token_and_validates(fake_kb, monkeypatch):
    as_role("user")
    seen = {}
    monkeypatch.setattr(kb_api, "get_user_client", lambda token: seen.setdefault("token", token))
    monkeypatch.setattr(kb_api, "get_embedder", lambda: None)
    chunk = RetrievedChunk(1, "d1", "a.md", "A", 1, "Intro", "text", 0.5, 1, None, {})
    monkeypatch.setattr(KnowledgeBaseService, "search", staticmethod(lambda db, emb, q, k: [chunk]))
    r = client.post("/api/kb/search", json={"query": "pricing", "k": 3})
    assert r.status_code == 200 and seen["token"] == "tok"
    assert r.json()["results"][0]["citation"] == "a.md § Intro"
    assert client.post("/api/kb/search", json={"query": ""}).status_code == 422
    assert client.post("/api/kb/search", json={"query": "x", "k": 99}).status_code == 422
