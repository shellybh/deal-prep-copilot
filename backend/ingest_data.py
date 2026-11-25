"""Seed the knowledge base.

Ingests every Markdown file in rag_knowledge_base/ plus the CRM CSV into documents +
corporate_documents, using the connection from db_setup.py. Safe to run more than once.

Run from the backend folder:
    python ingest_data.py                      # default chunking (markdown: headings, then 1000/100)
    python ingest_data.py --chunking fixed     # baseline: 500 chars / 50 overlap
    python ingest_data.py --force              # re-embed even unchanged files
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import ConfigError, get_settings  # noqa: E402
from app.rag.chunking import STRATEGIES  # noqa: E402
from app.rag.embeddings import GeminiEmbedder  # noqa: E402
from app.rag.ingest import Ingestor  # noqa: E402
from db_setup import get_supabase  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = sorted((REPO_ROOT / "rag_knowledge_base").glob("*.md")) + [
    REPO_ROOT / "crm_historical_win_loss_data_2025_2026.csv"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the sample knowledge base into Supabase.")
    parser.add_argument("--chunking", choices=STRATEGIES, default=None,
                        help="default: CHUNKING_STRATEGY from .env, else markdown (fixed = baseline 500/50)")
    parser.add_argument("--force", action="store_true", help="re-embed files even if unchanged")
    parser.add_argument("files", nargs="*", type=Path, help="specific files (default: sample KB + CRM CSV)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    try:
        settings = get_settings()
        embedder = GeminiEmbedder()
    except ConfigError as exc:
        print(f"FAILED: {exc}")
        return 1
    ingestor = Ingestor(get_supabase(), embedder, strategy=args.chunking)
    files = args.files or DEFAULT_FILES
    print(f"Ingesting {len(files)} files | chunking={ingestor.chunking_signature} "
          f"| model={settings.embedding_model} ({settings.embedding_dim} dims)\n")

    started = time.perf_counter()
    results = []
    for path in files:
        if not path.exists():
            print(f"  FAILED     {path.name}: file not found")
            continue
        r = ingestor.ingest(path, force=args.force)
        results.append(r)
        detail = f"{r.chunks} chunks" if r.status == "indexed" else (r.error or "")
        print(f"  {r.status.upper():<10} {r.file_name}  {detail}")

    indexed = [r for r in results if r.status == "indexed"]
    unchanged = [r for r in results if r.status == "unchanged"]
    failed = len(files) - len(indexed) - len(unchanged)
    u = embedder.usage
    print(f"\nSummary: {len(indexed)} indexed, {len(unchanged)} unchanged, {failed} failed | "
          f"{sum(r.chunks for r in indexed)} chunks inserted | "
          f"embedding calls: {u.requests} ({u.texts} texts, {u.characters:,} chars) | "
          f"{time.perf_counter() - started:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
