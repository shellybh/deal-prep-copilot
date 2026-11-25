"""Deal-Prep Copilot CLI (D33; Phase 4-lite full run, D36).

Default: the full run (`run_research`): identification -> Research Agent -> completeness / extra round ->
Analysis & Writing Agent -> quality checks, saved to Supabase. `--single` runs the Phase 2B single agent
(eval baseline and fallback).

Run from the backend folder:
    python agent.py --company "Snowflake" --goal "intro call about real-time analytics"
    python agent.py --company "monday.com" --website https://monday.com --country Israel --language he
    python agent.py --company "Acme" --meeting-type partnership --depth quick --no-save
    python agent.py --company "QuantaLake" --single --language he --k 8

Exit codes: 0 briefing printed (completed or partial) · 1 agent / API error or failed run ·
2 config or argument error · 3 company not identified (no briefing; run again with --website)
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agents.briefing import (LANGUAGES, AgentError, BriefingResult, CompanyNotIdentified,  # noqa: E402
                                 run_briefing)
from app.agents.contracts import ResearchRequest  # noqa: E402
from app.agents.identify import InvalidWebsite, parse_website  # noqa: E402
from app.core.config import ConfigError, get_settings  # noqa: E402


EXIT_NOT_IDENTIFIED = 3


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a deal-prep briefing for a company.")
    parser.add_argument("--company", required=True, help="company name, e.g. \"Snowflake\"")
    parser.add_argument("--language", choices=LANGUAGES, default="en", help="briefing language (default: en)")
    parser.add_argument("--website", help="optional company website (URL or domain), removes name ambiguity")
    parser.add_argument("--meeting-type", choices=("sales", "partnership"), default="sales")
    parser.add_argument("--goal", default="", help="meeting goal, e.g. 'first discovery call'")
    parser.add_argument("--country", help="optional country, e.g. Israel (sets search languages, D37)")
    parser.add_argument("--depth", choices=("quick", "standard", "in_depth"), default="standard")
    parser.add_argument("--context", help="optional extra context from you (shown as user-provided)")
    parser.add_argument("--context-type", choices=("internal_information", "assumption", "requires_verification"),
                        help="classification of --context (required with it)")
    parser.add_argument("--no-save", action="store_true", help="don't write the run to Supabase")
    parser.add_argument("--out", help="also write the briefing Markdown to this file")
    parser.add_argument("--single", action="store_true", help="run the Phase 2B single agent instead (baseline)")
    parser.add_argument("--k", type=int, default=5, help="--single only: internal results per search (1-20)")
    args = parser.parse_args(argv)
    if not args.company.strip():
        parser.error("--company must not be empty")
    if not 1 <= args.k <= 20:
        parser.error("--k must be between 1 and 20")
    try:
        parse_website(args.website)
    except InvalidWebsite as exc:
        parser.error(f"--website: {exc}")
    if args.context and not args.context_type:
        parser.error("--context needs --context-type")
    return args


def build_request(args: argparse.Namespace) -> ResearchRequest:
    return ResearchRequest(company=args.company, meeting_type=args.meeting_type, meeting_goal=args.goal,
                           country=args.country, website=args.website, depth=args.depth, language=args.language,
                           user_context=args.context, user_context_type=args.context_type)


def run_footer(r) -> str:
    t = r.usage.totals()
    q = r.briefing.quality if r.briefing else None
    lines = ["-" * 60, f"Run {r.run_id}: {r.status.upper()} in {r.duration_s:.1f}s"]
    for st in r.stages:
        lines.append(f"  {st.stage:<23} {st.status:<11} {st.detail or ''}".rstrip())
    lines.append(f"Website: {r.request.website or 'not provided'}"
                 + (f" | {r.identification.summary()}" if r.identification else ""))
    if r.findings:
        f = r.findings
        cited = len(r.briefing.sources) if r.briefing else 0
        lines.append(f"Sources: {len(f.internal.source_ids)} internal, {len(f.web.source_ids)} web, "
                     f"{len(f.competitive.source_ids)} competitive; {cited} cited | rounds {f.rounds} | "
                     f"search languages {', '.join(f.search_languages) or '-'}")
    lines.append(f"Usage: {t['llm_calls']} LLM calls, tokens in/out {t['input_tokens']}/{t['output_tokens']}, "
                 f"{t['tavily_credits']} Tavily credits")
    if q:
        lines.append(f"Quality: {len(q.sections_missing)} sections missing, {len(q.generic_dropped)} generic "
                     f"removed, {q.facts_without_source} unsourced facts, {q.conflicts} conflicts, "
                     f"{q.low_confidence} low confidence")
    if r.briefing:
        lines.append("Prompts: " + ", ".join(r.briefing.meta.prompt_versions.values()))
    lines += [f"WARNING: {w}" for w in r.warnings]
    if r.findings:
        lines += [f"NOTE: {e}" for e in r.findings.errors]
    if r.error:
        lines.append(f"ERROR: {r.error}")
    return "\n".join(lines)


def footer(r: BriefingResult) -> str:
    calls = ", ".join(f"{name} x{n}" for name, n in Counter(r.tool_calls).items()) or "none"
    lines = [
        "-" * 60,
        f"Tools called: {calls}" + (" (agent was reminded to call a required tool)" if r.nudged else ""),
        f"Website: {r.website_domain or 'not provided'}"
        + (f" | {r.identification.summary()}" if r.identification else ""),
        f"Sources returned: {len(r.sources.internal_citations)} internal, {len(r.sources.news_urls)} news",
        f"Model: {r.model} | prompt {r.prompt_version} | tokens in/out: {r.input_tokens}/{r.output_tokens}",
        f"Duration: {r.duration_s:.1f}s",
    ]
    lines += [f"WARNING: {e}" for e in r.sources.tool_errors]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Hebrew output on the Windows console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    try:
        s = get_settings()
        s.required_gemini_key()
        s.required_tavily_key()
        if not args.single:
            return run_full(args)
        print(f"Researching {args.company} ({args.language}, model {s.chat_model})...\n", file=sys.stderr)
        result = run_briefing(args.company, language=args.language, k=args.k, website=args.website)
    except ConfigError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    except CompanyNotIdentified as exc:
        print(f"NOT IDENTIFIED: {exc}. No briefing was written.", file=sys.stderr)
        return EXIT_NOT_IDENTIFIED
    except AgentError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # API errors from Gemini / Supabase: clear message, no traceback, no secrets
        print(f"FAILED: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return 1
    print(result.text)
    print()
    print(footer(result))
    return 0


def run_full(args: argparse.Namespace) -> int:
    from app.agents.orchestrator import Deps, run_research
    from app.agents.store import MemoryRunStore, SupabaseRunStore
    request = build_request(args)
    store = MemoryRunStore() if args.no_save else SupabaseRunStore()
    print(f"Researching {request.company} ({request.meeting_type}, {request.depth}, {request.language})...",
          file=sys.stderr)

    def progress(st):
        if st.status != "pending":
            print(f"  [{st.status}] {st.stage}" + (f": {st.detail}" if st.detail else ""), file=sys.stderr)
    try:
        result = run_research(request, Deps(store=store), on_stage=progress)
    except CompanyNotIdentified as exc:
        print(f"NOT IDENTIFIED: {exc}. No briefing was written.", file=sys.stderr)
        return EXIT_NOT_IDENTIFIED
    if result.markdown:
        print(result.markdown)
    if args.out:
        Path(args.out).write_text((result.markdown or "") + "\n" + run_footer(result) + "\n", encoding="utf-8")
    print(run_footer(result))
    return 0 if result.status in ("completed", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
