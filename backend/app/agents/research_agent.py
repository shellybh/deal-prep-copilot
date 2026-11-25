"""Research Agent (D36): one tool-calling agent for the Internal, Web and Competitive Intelligence roles.

Extends the 2B agent: same `create_agent` loop and bounds, but the tools write every result into the run's
`SourceRegistry` under one `CreditBudget` for the whole run, and the agent returns notes, not a briefing.
Company, website, country and depth are fixed by the request (closures), so the model can't drift to a
similarly named entity in its tool arguments.

`ResearchContext` is also used by the Orchestrator's extra research rounds (code, no LLM).
"""
from __future__ import annotations

import functools
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Callable, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.errors import GraphRecursionError

from app.agents.contracts import ResearchRequest
from app.agents.llm import UsageLog, model_name
from app.agents.registry import SourceRegistry
from app.agents.role_prompts import research as P
from app.agents.tailoring import profile
from app.research.depth import DepthConfig, get_depth
from app.research.provider import CreditBudget, FatalSearchError, SearchError

log = logging.getLogger(__name__)

AGENT = "research"
INTERNAL_TOOL = "search_internal_docs"
INFO_TOOL = "search_company_info"
NEWS_TOOL = "search_company_news"
COMP_TOOL = "search_competitors"
FETCH_TOOL = "fetch_page"
REQUIRED_TOOLS = (INFO_TOOL, NEWS_TOOL, COMP_TOOL, INTERNAL_TOOL)
INFO_TOPICS = ("profile", "financial", "people", "press", "israel")
NEWS_PURPOSES = {"news_recent", "news"}
MAX_INTERNAL_CALLS = 4
INTERNAL_K = {"quick": 6, "standard": 10, "in_depth": 15}     # D17 RAG top-k
RECURSION_BACKSTOP = 60
TOOL_SNIPPET = 300
Topic = Literal["profile", "financial", "people", "press", "israel"]


@dataclass
class ResearchContext:
    """Everything one run's research needs. Shared by the agent's tools and the extra rounds."""
    request: ResearchRequest
    registry: SourceRegistry
    usage: UsageLog
    service: object                                   # ExternalResearchService (or a fake in tests)
    internal_fn: Callable[..., list[dict]]
    cfg: DepthConfig = None
    budget: CreditBudget = None
    aliases: list[str] = field(default_factory=list)
    fetches: int = 0
    web_disabled: str | None = None                  # set after a fatal Tavily error
    tool_calls: list[str] = field(default_factory=list)
    # The agent runs parallel tool calls in threads: one lock keeps the registry IDs, the credit budget and
    # the per-call credit accounting consistent (found in the first live run: credits counted twice).
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self):
        self.cfg = self.cfg or get_depth(self.request.depth)
        self.budget = self.budget or CreditBudget(self.cfg.credit_cap)

    # ---- web ----
    def web_search(self, purposes: set[str], limit: int | None = None) -> dict:
        r = self.request
        purposes = set(purposes)
        if self.web_disabled:
            return {"error": f"web search unavailable: {self.web_disabled}", "sources": []}
        before = self.budget.used
        try:
            result = self.service.research_company(
                r.company, country=r.country, website=r.website, depth=self.cfg, purposes=purposes, limit=limit,
                budget=self.budget, extract=False, aliases=self.aliases)
        except FatalSearchError as exc:
            self.web_disabled = str(exc)
            self.registry.findings.errors.append(f"web: {exc}")
            return {"error": f"web search unavailable: {exc}. Do not call web tools again.", "sources": []}
        except SearchError as exc:
            self.registry.findings.errors.append(f"web ({', '.join(sorted(purposes))}): {exc}")
            return {"error": str(exc), "sources": []}
        finally:
            self.usage.tavily(AGENT, self.budget.used - before)
        self.registry.queried_purposes |= {q["purpose"] for q in result.queries_run}
        if result.budget_exhausted:
            self.registry.budget_exhausted = True
        f = self.registry.findings
        f.search_languages = sorted(set(f.search_languages) | set(result.search_languages))
        if not result.local_language_searched and result.local_language:
            f.local_language_note = (f"Searched in {' and '.join(f.search_languages) or 'English'} only; "
                                     f"sources in the local language ({result.local_language}) were not checked.")
        f.errors += [f"web: {e}" for e in result.errors]
        recs = [self.registry.add_web(s) for s in result.sources]
        out = {"sources": [self._web_view(rec) for rec in recs]}
        if result.budget_exhausted:
            out["note"] = "The research credit budget is used up. Continue with what you have."
        if not recs:
            out["note"] = (out.get("note", "") + " NO RELEVANT RESULTS for these topics. Report this as a gap.").strip()
        return out

    @staticmethod
    def _web_view(rec) -> dict:
        return {"id": rec.id, "title": rec.title, "outlet": rec.outlet, "tier": rec.tier,
                "date": rec.published_at.date().isoformat() if rec.published_at else "date unknown",
                "window": rec.window, "snippet": rec.text[:TOOL_SNIPPET]}

    def fetch(self, source_id: str) -> dict:
        rec = self.registry.get(source_id)
        if rec is None or rec.kind != "external":
            return {"error": f"unknown web source id {source_id}"}
        if self.fetches >= max(self.cfg.extract_top, 0):
            return {"error": "page fetch limit for this depth reached"}
        if self.web_disabled:
            return {"error": f"web unavailable: {self.web_disabled}"}
        before = self.budget.used
        try:
            data = self.service.fetch_pages([rec.url], budget=self.budget)
        except SearchError as exc:
            return {"error": str(exc)}
        finally:
            self.usage.tavily(AGENT, self.budget.used - before)
        self.fetches += 1
        pages = data.get("pages") or []
        if not pages or not pages[0].get("content"):
            return {"error": "the page could not be read"}
        self.registry.set_page_text(rec.id, pages[0]["content"])
        return {"id": rec.id, "content": self.registry.get(rec.id).text}

    # ---- internal ----
    def internal_search(self, query: str) -> dict:
        self.registry.internal_queries.append(query)
        try:
            chunks = self.internal_fn(query, k=INTERNAL_K.get(self.request.depth, 10))
        except Exception as exc:  # DB / embedding errors: report, don't crash the run
            self.registry.findings.errors.append(f"internal: {type(exc).__name__}: {str(exc)[:200]}")
            return {"error": f"internal search failed ({type(exc).__name__})", "results": []}
        recs = [self.registry.add_internal(c) for c in chunks]
        if not recs:
            return {"results": [], "note": f"NO RESULTS in the internal knowledge base for '{query}'."}
        return {"results": [{"id": r.id, "citation": r.citation, "content": r.text} for r in recs]}


def make_tools(ctx: ResearchContext) -> list[BaseTool]:
    def serial(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with ctx.lock:
                return fn(*args, **kwargs)
        return wrapper

    def log_call(name: str):
        ctx.tool_calls.append(name)

    @serial
    def search_company_info(topics: list[Topic] | None = None, aliases: list[str] | None = None) -> str:
        """Public web information about the company. topics: any of profile, financial, people, press, israel
        (default: all). aliases: other names of the company, e.g. its Hebrew name."""
        log_call(INFO_TOOL)
        if aliases:
            ctx.aliases = list(dict.fromkeys([*ctx.aliases, *[a.strip() for a in aliases if a and a.strip()]]))
        chosen = {t for t in (topics or INFO_TOPICS) if t in INFO_TOPICS} or set(INFO_TOPICS)
        return json.dumps(ctx.web_search(chosen), ensure_ascii=False)

    @serial
    def search_company_news() -> str:
        """Recent news about the company: last 48 hours first, then the research depth's time range."""
        log_call(NEWS_TOOL)
        return json.dumps(ctx.web_search(NEWS_PURPOSES), ensure_ascii=False)

    @serial
    def search_competitors() -> str:
        """Web sources about the company's competitors, alternatives and market position."""
        log_call(COMP_TOOL)
        return json.dumps(ctx.web_search({"competitors"}), ensure_ascii=False)

    @serial
    def search_internal_docs(query: str) -> str:
        """Search our internal knowledge base. Input: a short English search query."""
        log_call(INTERNAL_TOOL)
        if ctx.tool_calls.count(INTERNAL_TOOL) > MAX_INTERNAL_CALLS:
            return json.dumps({"error": f"internal search limit ({MAX_INTERNAL_CALLS}) reached"})
        return json.dumps(ctx.internal_search(query), ensure_ascii=False)

    @serial
    def fetch_page(source_id: str) -> str:
        """Read the main text of one important web source by its ID (e.g. W2)."""
        log_call(FETCH_TOOL)
        return json.dumps(ctx.fetch(source_id), ensure_ascii=False)

    tools = [StructuredTool.from_function(search_company_info, name=INFO_TOOL),
             StructuredTool.from_function(search_company_news, name=NEWS_TOOL),
             StructuredTool.from_function(search_competitors, name=COMP_TOOL),
             StructuredTool.from_function(search_internal_docs, name=INTERNAL_TOOL)]
    if ctx.cfg.extract_top > 0:
        tools.append(StructuredTool.from_function(fetch_page, name=FETCH_TOOL))
    return tools


def system_prompt(ctx: ResearchContext) -> str:
    r = ctx.request
    p = profile(r.meeting_type)
    fetch = (f"- `fetch_page(source_id)`: full text of one web source. Use it for at most {ctx.cfg.extract_top} "
             "of the most important sources." if ctx.cfg.extract_top > 0 else "")
    return P.SYSTEM.format(
        company=r.company,
        website_line=f" (website: {r.website}; other entities with a similar name are not this company)"
        if r.website else "",
        country_line=f", country: {r.country}" if r.country else "",
        meeting_line=f"Meeting: {p.label}. Goal: {r.meeting_goal or 'not given'}.",
        fetch_line=fetch, max_internal=MAX_INTERNAL_CALLS)


def _final_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not m.tool_calls:
            return (m.text if isinstance(m.text, str) else m.text()).strip()
    return ""


def run_research_agent(ctx: ResearchContext, llm: BaseChatModel, max_model_calls: int = 8) -> None:
    """Runs the agent; results land in `ctx.registry`. Hitting the step limit keeps what was collected."""
    tools = make_tools(ctx)
    agent = create_agent(llm, tools, system_prompt=system_prompt(ctx),
                         middleware=[ModelCallLimitMiddleware(run_limit=max_model_calls, exit_behavior="error")])
    config = {"recursion_limit": RECURSION_BACKSTOP}
    messages: list[BaseMessage] = [HumanMessage(P.USER.format(company=ctx.request.company))]
    name = model_name(llm)
    try:
        messages = agent.invoke({"messages": messages}, config=config)["messages"]
        missing = [t for t in REQUIRED_TOOLS if t not in ctx.tool_calls]
        if missing:
            ctx.usage.llm_messages(AGENT, name, messages)
            n_before = len(messages)
            nudge = HumanMessage(P.NUDGE.format(missing=" and ".join(missing)))
            messages = agent.invoke({"messages": messages + [nudge]}, config=config)["messages"]
            ctx.usage.llm_messages(AGENT, name, messages[n_before:])
            ctx.registry.findings.notes = _final_text(messages)
            return
    except (ModelCallLimitExceededError, GraphRecursionError):
        ctx.registry.findings.errors.append(f"research agent hit its step limit ({max_model_calls} model calls); "
                                            "continuing with the sources collected")
        return
    finally:
        ctx.registry.findings.tool_calls = list(ctx.tool_calls)
        ctx.registry.findings.credits_used = ctx.budget.used
    ctx.usage.llm_messages(AGENT, name, messages)
    ctx.registry.findings.notes = _final_text(messages)
