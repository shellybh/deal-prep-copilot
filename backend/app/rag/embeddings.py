"""Gemini embeddings (D9): gemini-embedding-001 at 1536 dims, L2-normalized, batched, with retry."""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

from google import genai
from google.genai import errors, types

from app.core.config import get_settings

log = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_ATTEMPTS = 6


class EmbeddingError(RuntimeError):
    pass


@dataclass
class EmbeddingUsage:
    """Counts for cost tracking. Persisted to usage_events once that table exists (Phase 4)."""
    requests: int = 0
    texts: int = 0
    characters: int = 0


def normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        raise EmbeddingError("embedding API returned a zero vector")
    return [x / norm for x in vector]


class GeminiEmbedder:
    def __init__(self, client: genai.Client | None = None, model: str | None = None, dim: int | None = None,
                 sleep=time.sleep):
        s = get_settings()
        self.model = model or s.embedding_model
        self.dim = dim or s.embedding_dim
        self._client = client or genai.Client(api_key=s.required_gemini_key())
        self._sleep = sleep
        self.usage = EmbeddingUsage()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            out.extend(self._embed(texts[i:i + BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._client.models.embed_content(model=self.model, contents=texts, config=config)
                break
            except errors.APIError as exc:
                retryable = exc.code == 429 or (exc.code or 0) >= 500
                if not retryable or attempt == MAX_ATTEMPTS:
                    raise EmbeddingError(f"embedding request failed ({exc.code}): {exc.message}") from exc
                wait = min(60, 2 ** attempt)  # free-tier rate limits: back off and retry
                log.warning("Embedding API %s, retry %d/%d in %ds", exc.code, attempt, MAX_ATTEMPTS, wait)
                self._sleep(wait)
        vectors = [e.values for e in resp.embeddings]
        if len(vectors) != len(texts):
            raise EmbeddingError(f"expected {len(texts)} embeddings, got {len(vectors)}")
        for v in vectors:
            if len(v) != self.dim:
                raise EmbeddingError(f"embedding dimension {len(v)} != expected {self.dim} (vector column size)")
        self.usage.requests += 1
        self.usage.texts += len(texts)
        self.usage.characters += sum(len(t) for t in texts)
        return [normalize(v) for v in vectors]


def to_pgvector(vector: list[float]) -> str:
    """pgvector text format, used for inserts and RPC parameters over the REST API."""
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"
