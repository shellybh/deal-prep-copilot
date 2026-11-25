"""Retrieval evaluation (TESTING.md §2.3). Re-run after any change to chunking,
embeddings or search.

Runs every query in retrieval_queries.json against the current index in three modes
(hybrid, semantic only, keyword only) and reports:
  hit@1 / hit@5  expected file is ranked 1st / in the top 5
  MRR@5          mean reciprocal rank of the expected file
  answer@5       a top-5 chunk contains the answer text (chunk-level check)

Usage (repo root, venv active):  python evals/retrieval_eval.py [--k 5] [--label fixed-500-50]
Writes evals/results/<timestamp>_<label>.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.clients import get_admin_client  # noqa: E402
from app.rag.embeddings import GeminiEmbedder  # noqa: E402
from app.rag.retrieval import retrieve  # noqa: E402

MODES = {"hybrid": (1.0, 1.0), "semantic": (0.0, 1.0), "keyword": (1.0, 0.0)}


def score(results, expected_file: str, answer: str) -> dict:
    files = [r.file_name for r in results]
    rank = files.index(expected_file) + 1 if expected_file in files else None
    return {"rank": rank, "hit1": rank == 1, "hit5": rank is not None and rank <= 5,
            "rr": 1.0 / rank if rank else 0.0,
            "answer5": any(answer.lower() in r.content.lower() for r in results[:5]),
            "top": [r.citation for r in results[:3]]}


def summarize(rows: list[dict]) -> dict:
    n = len(rows) or 1
    return {"n": len(rows),
            "hit@1": round(sum(r["hit1"] for r in rows) / n, 3),
            "hit@5": round(sum(r["hit5"] for r in rows) / n, 3),
            "MRR@5": round(sum(r["rr"] for r in rows) / n, 3),
            "answer@5": round(sum(r["answer5"] for r in rows) / n, 3)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--label", default="current-index")
    args = ap.parse_args()

    queries = json.loads((ROOT / "evals" / "retrieval_queries.json").read_text(encoding="utf-8"))
    db, embedder = get_admin_client(), GeminiEmbedder()
    started = time.perf_counter()
    q_vectors = {q["id"]: embedder.embed_query(q["query"]) for q in queries}

    report = {"label": args.label, "k": args.k, "date": datetime.now().isoformat(timespec="seconds"),
              "modes": {}, "per_query": {}}
    for mode, (ft_w, sem_w) in MODES.items():
        rows = []
        for q in queries:
            res = retrieve(db, None, q["query"], k=args.k, full_text_weight=ft_w, semantic_weight=sem_w,
                           query_embedding=q_vectors[q["id"]])
            row = {"id": q["id"], "lang": q["lang"], **score(res, q["expected_file"], q["answer_contains"])}
            rows.append(row)
            report["per_query"].setdefault(q["id"], {})[mode] = row
        report["modes"][mode] = {"all": summarize(rows),
                                 "en": summarize([r for r in rows if r["lang"] == "en"]),
                                 "he": summarize([r for r in rows if r["lang"] == "he"])}

    print(f"Retrieval eval | {args.label} | {len(queries)} queries | k={args.k}\n")
    print(f"{'mode':<9} {'subset':<4} {'hit@1':>6} {'hit@5':>6} {'MRR@5':>6} {'ans@5':>6}")
    for mode, subsets in report["modes"].items():
        for subset, m in subsets.items():
            print(f"{mode:<9} {subset:<4} {m['hit@1']:>6} {m['hit@5']:>6} {m['MRR@5']:>6} {m['answer@5']:>6}")
    misses = [(qid, m) for qid, modes in report["per_query"].items() for mode, m in modes.items()
              if mode == "hybrid" and (not m["hit1"] or not m["answer5"])]
    if misses:
        print("\nHybrid misses (not rank 1 or answer not in top 5):")
        for qid, m in misses:
            print(f"  {qid}: rank={m['rank']} answer@5={m['answer5']} top={m['top'][:2]}")

    out = ROOT / "evals" / "results"
    out.mkdir(exist_ok=True)
    path = out / f"{datetime.now():%Y%m%d-%H%M%S}_{args.label}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {path.relative_to(ROOT)} ({time.perf_counter() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
