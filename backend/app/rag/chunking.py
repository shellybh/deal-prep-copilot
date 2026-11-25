"""Chunking (D13). Pure functions, no I/O.

Strategies for text/Markdown:
- "fixed":    RecursiveCharacterTextSplitter, chunk_size / overlap (baseline default 500 / 50).
- "markdown": split by headings first, then by size (default 1000 / 100), so tables and
              sections stay together. Evaluated against "fixed" in the retrieval eval.
CSV: groups of rows, header repeated as "Column: value" lines, location = row range.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

STRATEGIES = ("fixed", "markdown")
MARKDOWN_CHUNK_SIZE, MARKDOWN_CHUNK_OVERLAP = 1000, 100
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Chunk:
    content: str
    section: str                      # heading path ("A > B") or CSV row range ("rows 1-10")
    extra: dict = field(default_factory=dict)


def markdown_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            return _clean(m.group(2))
    return fallback


def _clean(heading: str) -> str:
    return heading.replace("**", "").replace("`", "").strip()


def _heading_index(text: str) -> list[tuple[int, int, str]]:
    """(char offset, level, title) for every Markdown heading, skipping fenced code blocks."""
    out, offset, in_code = [], 0, False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code and (m := _HEADING.match(line.rstrip("\n"))):
            out.append((offset, len(m.group(1)), _clean(m.group(2))))
        offset += len(line)
    return out


def _section_at(headings: list[tuple[int, int, str]], pos: int) -> str:
    path: list[tuple[int, str]] = []
    for offset, level, title in headings:
        if offset > pos:
            break
        path = [p for p in path if p[0] < level] + [(level, title)]
    return " > ".join(t for _, t in path)


def chunk_fixed(text: str, chunk_size: int = 500, overlap: int = 50) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("chunk overlap must be smaller than chunk size")
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap, add_start_index=True)
    headings = _heading_index(text)
    chunks = []
    for doc in splitter.create_documents([text]):
        content = doc.page_content.strip()
        if not content:
            continue
        start = doc.metadata["start_index"]
        # If the chunk opens with a heading, that heading is its section.
        first = content.splitlines()[0]
        pos = start + len(first) if _HEADING.match(first) else start
        chunks.append(Chunk(content, _section_at(headings, pos)))
    return chunks


def chunk_markdown(text: str, chunk_size: int = MARKDOWN_CHUNK_SIZE,
                   overlap: int = MARKDOWN_CHUNK_OVERLAP) -> list[Chunk]:
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")], strip_headers=False)
    size_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    chunks = []
    for section_doc in header_splitter.split_text(text):
        section = " > ".join(_clean(section_doc.metadata[k]) for k in ("h1", "h2", "h3")
                             if k in section_doc.metadata)
        for piece in size_splitter.split_text(section_doc.page_content):
            if piece.strip():
                chunks.append(Chunk(piece.strip(), section))
    return chunks


def chunk_text(text: str, strategy: str, chunk_size: int, overlap: int) -> list[Chunk]:
    if strategy == "fixed":
        return chunk_fixed(text, chunk_size, overlap)
    if strategy == "markdown":
        return chunk_markdown(text)
    raise ValueError(f"unknown chunking strategy {strategy!r}; use one of {STRATEGIES}")


def chunk_csv(text: str, rows_per_chunk: int = 10) -> list[Chunk]:
    """Row groups. Row numbers count data rows (header excluded), starting at 1."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    chunks = []
    for start in range(0, len(rows), rows_per_chunk):
        group = rows[start:start + rows_per_chunk]
        first, last = start + 1, start + len(group)
        blocks = ["\n".join(f"{col}: {val.strip()}" for col, val in zip(header, row)) for row in group]
        chunks.append(Chunk(
            content=f"Columns: {', '.join(header)}\n\n" + "\n\n".join(blocks),
            section=f"rows {first}-{last}",
            extra={"row_start": first, "row_end": last},
        ))
    return chunks
