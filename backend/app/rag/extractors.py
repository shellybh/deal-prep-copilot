"""File validation and text extraction for the knowledge base (D3, D13, D35). Pure functions, no I/O.

Every format is turned into text the existing chunkers understand:
- MD, TXT: decoded text (UTF-8, then Windows-1255 for old Hebrew files).
- CSV: decoded text, chunked as row groups by `chunk_csv`.
- PDF (pypdf): "## Page N" before each page, so the Markdown chunker cites the page.
- DOCX (python-docx): headings → Markdown headings, tables → Markdown tables, so sections and
  tables stay together, like the Markdown files that won the Phase 2A eval.
No OCR (D35): a PDF without a text layer (scanned) fails with a clear message.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
}
TEXT_TYPES = {".txt", ".md", ".csv"}
MIN_PDF_TEXT_CHARS = 20   # fewer non-space characters than this in the whole PDF = no text layer

SCANNED_PDF_MESSAGE = ("No extractable text: the PDF is probably a scanned document (OCR is not "
                       "supported). Upload a digital version or a text file.")


class ExtractionError(ValueError):
    """The file can't be used. The message is shown to the admin as the failure reason."""


@dataclass(frozen=True)
class Extracted:
    text: str
    kind: str       # "markdown" (headings usable) | "text" | "csv"
    title: str | None = None


def suffix_of(file_name: str) -> str:
    return PurePath(file_name).suffix.lower()


def validate_upload(file_name: str, raw: bytes, max_bytes: int) -> str:
    """Checks name, size, extension and content (not only the extension). Returns the MIME type."""
    name = file_name.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ExtractionError("Invalid file name.")
    if len(name) > 200:
        raise ExtractionError("File name is too long (max 200 characters).")
    suffix = suffix_of(name)
    if suffix not in MIME_TYPES:
        raise ExtractionError(f"Unsupported file type '{suffix or '(none)'}'. Allowed: "
                              + ", ".join(sorted(s.lstrip('.').upper() for s in MIME_TYPES)) + ".")
    if not raw:
        raise ExtractionError("The file is empty.")
    if len(raw) > max_bytes:
        raise ExtractionError(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    if suffix == ".pdf" and not raw.startswith(b"%PDF-"):
        raise ExtractionError("The file has a .pdf name but is not a PDF.")
    if suffix == ".docx" and not _is_docx(raw):
        raise ExtractionError("The file has a .docx name but is not a Word (DOCX) document.")
    if suffix in TEXT_TYPES:
        decode_text(raw)   # raises if binary
    return MIME_TYPES[suffix]


def _is_docx(raw: bytes) -> bool:
    if not raw.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return "word/document.xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


def decode_text(raw: bytes) -> str:
    if b"\x00" in raw[:8192]:
        raise ExtractionError("The file is not a text file (binary content).")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1255")   # legacy Hebrew Windows encoding
    except UnicodeDecodeError as exc:
        raise ExtractionError("Unknown text encoding: save the file as UTF-8.") from exc


def extract(file_name: str, raw: bytes) -> Extracted:
    suffix = suffix_of(file_name)
    if suffix == ".md":
        return Extracted(decode_text(raw), "markdown")
    if suffix == ".txt":
        return Extracted(decode_text(raw), "text")
    if suffix == ".csv":
        return Extracted(decode_text(raw), "csv")
    if suffix == ".pdf":
        return extract_pdf(raw)
    if suffix == ".docx":
        return extract_docx(raw)
    raise ExtractionError(f"Unsupported file type '{suffix}'.")


# ---------------------------------------------------------------- PDF
def extract_pdf(raw: bytes) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ExtractionError("The PDF is password-protected. Upload an unprotected copy.")
        pages = [(page.extract_text() or "") for page in reader.pages]
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise ExtractionError(f"The PDF could not be read ({type(exc).__name__}).") from exc

    if sum(len(re.sub(r"\s", "", p)) for p in pages) < MIN_PDF_TEXT_CHARS:
        raise ExtractionError(SCANNED_PDF_MESSAGE)
    parts = [f"## Page {i}\n\n{_clean_pdf_text(text)}" for i, text in enumerate(pages, start=1)
             if text.strip()]
    # PDF metadata titles are often junk ("Microsoft Word - x.docx"): the file name is the title.
    return Extracted("\n\n".join(parts), "markdown")


def _clean_pdf_text(text: str) -> str:
    # Lines starting with '#' would be read as headings by the Markdown chunker.
    lines = [("\\" + line) if line.lstrip().startswith("#") else line for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ---------------------------------------------------------------- DOCX
_HEADING_STYLE = re.compile(r"^heading\s*(\d)$", re.IGNORECASE)


def extract_docx(raw: bytes) -> Extracted:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001 - python-docx raises several unrelated types
        raise ExtractionError(f"The Word document could not be read ({type(exc).__name__}).") from exc

    blocks: list[str] = []
    title = (document.core_properties.title or "").strip() or None
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            style = (item.style.name if item.style is not None else "") or ""
            if style.lower() == "title":
                blocks.append(f"# {text}")
                title = title or text
            elif m := _HEADING_STYLE.match(style):
                blocks.append(f"{'#' * min(int(m.group(1)), 6)} {text}")
            elif style.lower().startswith("list"):
                blocks.append(f"- {text}")
            else:
                blocks.append(text)
        elif isinstance(item, Table):
            table = _table_markdown(item)
            if table:
                blocks.append(table)
    text = "\n\n".join(blocks).strip()
    if not text:
        raise ExtractionError("No text found in the Word document.")
    return Extracted(text, "markdown", title=title)


def _table_markdown(table) -> str:
    rows = []
    for row in table.rows:
        cells = [" ".join(c.text.split()).replace("|", "\\|") for c in row.cells]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)
