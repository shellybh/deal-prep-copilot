"""Agent eval (Phase 4-lite): Phase 2B single agent (baseline) vs the two-agent graph (D36).

Same companies for both. Both final Markdown outputs are measured the same way, after the fact:
- bullets: content bullets (Sources section excluded)
- cited %: bullets with at least one citation ([n] or [file § section])
- generic: bullets the small-model judge (app/agents/role_prompts/quality.py) calls generic; median of 3 judge
  calls per output (the judge is noisy), raw counts in `generic_runs`
Plus run cost (LLM calls, tokens, Tavily credits), duration, status, and for the graph the quality report.

Run from the repo root with the Tavily cache on (re-runs cost no credits, D37):
    TAVILY_CACHE_DIR=backend/.tavily_cache python evals/agent_eval.py
    python evals/agent_eval.py --only snowflake monday --modes graph
Outputs: evals/agent_runs/<date>_<case>_{single,graph}.md and evals/results/<ts>_agent_eval.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from app.agents.briefing import CompanyNotIdentified, run_briefing  # noqa: E402
from app.agents.contracts import GenericVerdict, ResearchRequest  # noqa: E402
from app.agents.llm import UsageLog, build_chat_model, structured_call  # noqa: E402
from app.agents.orchestrator import Deps, run_research  # noqa: E402
from app.agents.role_prompts import quality as PQ  # noqa: E402
from app.agents.store import MemoryRunStore  # noqa: E402


@dataclass(frozen=True)
class Case:
    slug: str
    company: str
    language: str
    meeting_type: str = "sales"
    website: str | None = None
    country: str | None = None
    goal: str = ""
    note: str = ""


CASES = [
    Case("snowflake", "Snowflake", "en", website="snowflake.com", country="United States",
         goal="first discovery call about real-time analytics", note="US public, our partner in the KB"),
    Case("monday", "monday.com", "he", website="monday.com", country="Israel",
         goal="פגישת היכרות ראשונה", note="Israeli, nothing in the KB"),
    Case("quantalake", "QuantaLake", "en", goal="win back a prospect evaluating QuantaLake",
         note="fictional competitor, KB only"),
    Case("wix", "Wix", "he", "partnership", website="wix.com", country="Israel",
         goal="לבחון שותפות אינטגרציה", note="Israeli, partnership, Hebrew"),
    Case("siemens", "Siemens", "en", "partnership", website="siemens.com", country="Germany",
         goal="explore a data platform partnership", note="German: local-language note, similar entities"),
    Case("databricks", "Databricks", "he", website="databricks.com", country="United States",
         goal="פגישת מכירה ראשונה", note="US, Hebrew briefing over English KB"),
    Case("zorbex", "Zorbex Dynamics", "en", note="fictional: expect not identified"),
]

CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]|\[[^\]]*§[^\]]*\]")  # [1], [1, 2] (2B), [file § section]
BULLET = re.compile(r"[-*+]\s+")  # the 2B agent sometimes writes "* " bullets
INSIGHT_SUBLINE = re.compile(r"(Why it matters|How to address|Rating|למה זה חשוב|איך להתייחס|נימוק הדירוג)\s*:")


def bullets(md: str) -> list[str]:
    out, in_sources = [], False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("#"):
            # Sources, and the graph's "Missing information" list (section names only, not claims)
            in_sources = bool(re.search(r"sources|מקורות|missing information|חסר מידע|מידע חסר", s, re.I))
            continue
        m = BULLET.match(s)
        if in_sources or not m:
            continue
        text = s[m.end():].strip()
        if len(text) > 15 and not text.startswith("_"):
            out.append(text)
    return out


JUDGE_RUNS = 3  # the judge is noisy (day 1: same texts scored 4 / 2 / 4), so score = median of N runs


def judge_once(items: list[dict], company: str, llm, usage: UsageLog) -> set[str]:
    v = structured_call(llm, GenericVerdict, [SystemMessage(PQ.SYSTEM.format(company=company)),
                                              HumanMessage(PQ.USER.format(items=json.dumps(items, ensure_ascii=False)))],
                        agent="eval_judge", usage=usage)
    known = {i["id"] for i in items}
    return {g for g in v.generic_ids if g in known}


def judge(md: str, company: str, llm, usage: UsageLog, runs: int = JUDGE_RUNS) -> dict:
    """`generic` = median count over `runs` judge calls; `generic_items` = bullets flagged by a majority of runs
    (so the two can differ by one); `generic_runs` = the raw counts, to show the spread."""
    items = [{"id": f"b{n}", "text": CITE.sub("", b)[:400]} for n, b in enumerate(bullets(md))]
    if not items:
        return {"generic": 0, "generic_runs": [], "generic_items": []}
    votes = [judge_once(items, company, llm, usage) for _ in range(runs)]
    counts = sorted(len(v) for v in votes)
    texts = {i["id"]: i["text"] for i in items}
    majority = [texts[i["id"]] for i in items if sum(i["id"] in v for v in votes) * 2 > runs]
    return {"generic": counts[len(counts) // 2], "generic_runs": [len(v) for v in votes],
            "generic_items": majority}


def measure(md: str | None, company: str, llm, usage: UsageLog, runs: int = JUDGE_RUNS) -> dict:
    if not md:
        return {"bullets": 0, "cited_pct": None, "generic": None, "generic_runs": [], "generic_items": []}
    bs = bullets(md)
    cited = sum(bool(CITE.search(b)) for b in bs)
    # the graph's insight sub-lines (why / how / rating) carry no citation of their own: the insight's title
    # line does. `cited_pct_main` leaves them out, so the graph isn't penalized for its layout.
    main = [b for b in bs if not INSIGHT_SUBLINE.match(b)]
    cited_main = sum(bool(CITE.search(b)) for b in main)
    return {"bullets": len(bs), "cited_pct": round(100 * cited / len(bs)) if bs else None,
            "cited_pct_main": round(100 * cited_main / len(main)) if main else None,
            **judge(md, company, llm, usage, runs)}


def run_single(c: Case) -> dict:
    t0 = time.perf_counter()
    try:
        r = run_briefing(c.company, language=c.language, website=c.website)
    except CompanyNotIdentified as exc:
        return {"status": "not_identified", "error": str(exc), "duration_s": round(time.perf_counter() - t0, 1)}
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "duration_s": round(time.perf_counter() - t0, 1)}
    calls = len([m for m in r.tool_calls]) + 1
    return {"status": "completed", "markdown": r.text, "duration_s": round(r.duration_s, 1),
            "llm_calls": None, "tool_calls": calls, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "tavily_credits": None, "identification": r.identification.summary() if r.identification else None}


def run_graph(c: Case) -> dict:
    req = ResearchRequest(company=c.company, language=c.language, meeting_type=c.meeting_type, website=c.website,
                          country=c.country, meeting_goal=c.goal)
    t0 = time.perf_counter()
    try:
        r = run_research(req, Deps(store=MemoryRunStore()))
    except CompanyNotIdentified as exc:
        return {"status": "not_identified", "error": str(exc), "duration_s": round(time.perf_counter() - t0, 1)}
    t = r.usage.totals()
    q = r.briefing.quality if r.briefing else None
    return {"status": r.status, "markdown": r.markdown, "duration_s": round(r.duration_s, 1),
            "llm_calls": t["llm_calls"], "input_tokens": t["input_tokens"], "output_tokens": t["output_tokens"],
            "tavily_credits": t["tavily_credits"], "error": r.error,
            "stages": {s.stage: s.status for s in r.stages},
            "sections_missing": q.sections_missing if q else None,
            "judge_removed": len(q.generic_dropped) if q else None,
            "cited_sources": len(r.briefing.sources) if r.briefing else 0,
            "internal_cited": sum(s.kind == "internal" for s in r.briefing.sources) if r.briefing else 0,
            "rounds": r.findings.rounds if r.findings else None,
            "notes": (r.findings.errors if r.findings else []) + r.warnings}


def remeasure(path: Path, runs: int = JUDGE_RUNS) -> int:
    results = json.loads(path.read_text(encoding="utf-8"))
    day = datetime.strptime(path.name[:8], "%Y%m%d").strftime("%Y-%m-%d")
    judge_llm, judge_usage = build_chat_model("small", temperature=0.0), UsageLog()
    for r in results:
        md_path = ROOT / "evals" / "agent_runs" / f"{day}_{r['case']}_{r['mode']}.md"
        if md_path.exists():
            r.update(measure(md_path.read_text(encoding="utf-8"), r["company"], judge_llm, judge_usage, runs))
            print(f"{r['case']}/{r['mode']}: bullets {r['bullets']}, cited {r['cited_pct']} %, "
                  f"generic {r['generic']} (runs {r['generic_runs']})",
                  file=sys.stderr, flush=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="case slugs")
    ap.add_argument("--modes", nargs="*", default=["single", "graph"], choices=["single", "graph"])
    ap.add_argument("--remeasure", metavar="RESULTS_JSON",
                    help="re-score the saved outputs of an earlier results file (judge calls only, no runs)")
    ap.add_argument("--judge-runs", type=int, default=JUDGE_RUNS,
                    help="generic-statement judge calls per output; the score is their median (default 3)")
    args = ap.parse_args()
    if args.remeasure:
        return remeasure(Path(args.remeasure), args.judge_runs)
    cases = [c for c in CASES if not args.only or c.slug in args.only]
    judge_llm, judge_usage = build_chat_model("small", temperature=0.0), UsageLog()
    day = datetime.now().strftime("%Y-%m-%d")
    results = []
    for c in cases:
        for mode in args.modes:
            print(f"== {c.slug} / {mode}", file=sys.stderr, flush=True)
            res = run_single(c) if mode == "single" else run_graph(c)
            md = res.pop("markdown", None)
            if md:
                (ROOT / "evals" / "agent_runs" / f"{day}_{c.slug}_{mode}.md").write_text(md, encoding="utf-8")
            try:
                res.update(measure(md, c.company, judge_llm, judge_usage, args.judge_runs))
            except Exception as exc:
                res["measure_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            results.append({"case": c.slug, "company": c.company, "mode": mode, "language": c.language,
                            "meeting_type": c.meeting_type, "note": c.note, **res})
            print(json.dumps({k: v for k, v in results[-1].items() if k not in ("generic_items", "notes")},
                             ensure_ascii=False), file=sys.stderr, flush=True)
    out = ROOT / "evals" / "results" / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_agent_eval.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("| case | mode | status | bullets | cited % | generic | LLM calls | tokens in/out | credits | s |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['case']} | {r['mode']} | {r['status']} | {r.get('bullets', '-')} | {r.get('cited_pct', '-')} | "
              f"{r.get('generic', '-')} | {r.get('llm_calls') or '-'} | {r.get('input_tokens', '-')}/"
              f"{r.get('output_tokens', '-')} | {r.get('tavily_credits') or '-'} | {r.get('duration_s')} |")
    print(f"\nResults: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
