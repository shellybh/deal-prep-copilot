from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors

from app.rag import chunking
from app.rag.chunking import Chunk, chunk_csv, chunk_fixed, chunk_markdown, markdown_title
from app.rag.embeddings import EmbeddingError, GeminiEmbedder, normalize, to_pgvector
from app.rag.ingest import embedding_text

KB = Path(__file__).resolve().parents[2] / "rag_knowledge_base"

DOC = """# Pricing Guide

Intro paragraph.

## Core Tiers

| Feature | Starter |
|---|---|
| Price | $1,200 |

### Notes

""" + "Long notes sentence. " * 60 + """

## Discounts

Volume discounts apply.
"""


# ---------------------------------------------------------------- chunking
def test_fixed_chunks_respect_size_and_carry_heading_path():
    chunks = chunk_fixed(DOC, 500, 50)
    assert all(len(c.content) <= 500 for c in chunks)
    assert chunks[0].section == "Pricing Guide"
    assert any(c.section == "Pricing Guide > Core Tiers > Notes" for c in chunks)
    last = chunks[-1]
    assert "Volume discounts" in last.content and last.section == "Pricing Guide > Discounts"


def test_fixed_chunks_overlap():
    text = " ".join(f"word{i}" for i in range(400))
    a, b = chunk_fixed(text, 200, 50)[:2]
    assert a.content[-30:].split()[-1] in b.content  # tail of a repeats at the start of b


def test_fixed_rejects_overlap_not_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_fixed("x", 50, 50)


def test_headings_inside_code_blocks_are_ignored():
    text = "# Real\n\n```\n# not a heading\n```\n\ntext"
    assert {c.section for c in chunk_fixed(text, 500, 50)} == {"Real"}


def test_markdown_strategy_keeps_tables_whole():
    chunks = chunk_markdown(DOC)
    table = [c for c in chunks if "| Price | $1,200 |" in c.content]
    assert table and "| Feature | Starter |" in table[0].content
    assert table[0].section == "Pricing Guide > Core Tiers"


def test_markdown_title_strips_formatting():
    assert markdown_title("intro\n# **NexaStream** Guide\n## x", "fallback") == "NexaStream Guide"
    assert markdown_title("no headings", "fallback") == "fallback"


def test_csv_row_groups_keep_header_and_row_range():
    rows = "\n".join(f"Co{i},Tech,{i}" for i in range(1, 24))
    chunks = chunk_csv("Company_Name,Industry,Size\n" + rows + "\n,,\n", rows_per_chunk=10)
    assert [c.section for c in chunks] == ["rows 1-10", "rows 11-20", "rows 21-23"]
    assert chunks[1].extra == {"row_start": 11, "row_end": 20}
    assert chunks[1].content.startswith("Columns: Company_Name, Industry, Size")
    assert "Company_Name: Co11\nIndustry: Tech\nSize: 11" in chunks[1].content
    assert "Co10" not in chunks[1].content


def test_csv_empty_file():
    assert chunk_csv("") == []


def test_sample_kb_chunks_have_sections():
    for path in sorted(KB.glob("*.md")):
        chunks = chunking.chunk_text(path.read_text(encoding="utf-8"), "fixed", 500, 50)
        assert chunks, path.name
        assert all(c.section for c in chunks), path.name


def test_embedding_text_adds_title_and_section():
    assert embedding_text("Guide", Chunk("body", "A > B")) == "Guide\nA > B\n\nbody"


# ---------------------------------------------------------------- embeddings
def _client(*responses):
    client = MagicMock()
    client.models.embed_content.side_effect = list(responses)
    return client


def _resp(*vectors):
    return SimpleNamespace(embeddings=[SimpleNamespace(values=v) for v in vectors])


def test_normalize_and_pgvector_format():
    assert normalize([3.0, 4.0]) == [0.6, 0.8]
    assert to_pgvector([0.6, 0.8]) == "[0.6,0.8]"
    with pytest.raises(EmbeddingError):
        normalize([0.0, 0.0])


def test_embeddings_are_normalized_and_counted():
    emb = GeminiEmbedder(client=_client(_resp([3.0, 4.0], [0.0, 2.0])), model="m", dim=2)
    assert emb.embed_documents(["a", "bb"]) == [[0.6, 0.8], [0.0, 1.0]]
    assert (emb.usage.requests, emb.usage.texts, emb.usage.characters) == (1, 2, 3)


def test_dimension_mismatch_fails_clearly():
    emb = GeminiEmbedder(client=_client(_resp([1.0, 0.0, 0.0])), model="m", dim=2)
    with pytest.raises(EmbeddingError, match="dimension 3 != expected 2"):
        emb.embed_query("q")


def test_batches_of_50(monkeypatch):
    client = MagicMock()
    client.models.embed_content.side_effect = lambda model, contents, config: _resp(*[[1.0, 0.0]] * len(contents))
    emb = GeminiEmbedder(client=client, model="m", dim=2)
    assert len(emb.embed_documents(["t"] * 120)) == 120
    assert [len(c.kwargs["contents"]) for c in client.models.embed_content.call_args_list] == [50, 50, 20]


def test_rate_limit_is_retried_then_succeeds():
    rate_limited = errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    sleeps = []
    emb = GeminiEmbedder(client=_client(rate_limited, _resp([1.0, 0.0])), model="m", dim=2, sleep=sleeps.append)
    assert emb.embed_query("q") == [1.0, 0.0]
    assert sleeps == [2]


def test_non_retryable_error_raises():
    bad = errors.ClientError(400, {"error": {"message": "bad request", "status": "INVALID_ARGUMENT"}})
    emb = GeminiEmbedder(client=_client(bad), model="m", dim=2, sleep=lambda s: None)
    with pytest.raises(EmbeddingError, match="400"):
        emb.embed_query("q")


def test_keyword_query_drops_stop_words_keeps_names_and_numbers():
    from app.rag.keywords import keyword_query
    assert keyword_query("What is the Enterprise tier list price?") == "Enterprise tier list price"
    assert keyword_query("מה אחוז הניצחונות שלנו מול InsightForge?") == "אחוז הניצחונות מול InsightForge"
    assert keyword_query("Who must approve a discount above 30%?") == "must approve discount 30%"
    assert keyword_query("what is the") == ""
