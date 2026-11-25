"""Hybrid retrieval over the knowledge base (D10, D11): calls the hybrid_search SQL function.

Pass a user-scoped client to search with the user's RLS, or the admin client for backend agents.
Reranking (D12) is deferred: `rerank` is the hook for it.
"""
from __future__ import annotations

from dataclasses import dataclass

from supabase import Client

from app.rag.embeddings import GeminiEmbedder, to_pgvector
from app.rag.keywords import keyword_query

MAX_K = 50


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: str
    file_name: str
    title: str
    version: int
    section: str
    content: str
    score: float
    semantic_rank: int | None
    keyword_rank: int | None
    metadata: dict

    @property
    def citation(self) -> str:
        return f"{self.file_name} § {self.section}" if self.section else self.file_name


def rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """No-op until reranking is approved (D12)."""
    return chunks


def retrieve(db: Client, embedder: GeminiEmbedder | None, query: str, k: int = 5,
             full_text_weight: float = 1.0, semantic_weight: float = 1.0,
             query_embedding: list[float] | None = None) -> list[RetrievedChunk]:
    """`query_embedding` lets callers (e.g. the eval) reuse an embedding instead of re-embedding."""
    query = query.strip()
    if not query:
        return []
    k = max(1, min(k, MAX_K))
    if query_embedding is None:
        query_embedding = embedder.embed_query(query)
    rows = db.rpc("hybrid_search", {
        "query_text": keyword_query(query),   # stop words removed for the FTS part
        "query_embedding": to_pgvector(query_embedding),
        "match_count": k,
        "full_text_weight": full_text_weight,
        "semantic_weight": semantic_weight,
    }).execute().data or []
    chunks = [RetrievedChunk(
        chunk_id=r["id"], document_id=r["document_id"], file_name=r["file_name"], title=r["title"],
        version=r["version"], section=(r["metadata"] or {}).get("section", ""), content=r["content"],
        score=r["score"], semantic_rank=r["semantic_rank"], keyword_rank=r["keyword_rank"],
        metadata=r["metadata"] or {},
    ) for r in rows]
    return rerank(query, chunks)
