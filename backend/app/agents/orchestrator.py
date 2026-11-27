"""Orchestrator (D8, D36 §3): LangGraph graph code, not an LLM supervisor. Entry point `run_research()`.

Flow: identify -> research -> completeness -> [extra round -> completeness]* -> analyze -> write
-> quality. The number of extra rounds comes from the depth (D17) and is enforced here; the completeness
criteria are code (D40 §1). Nodes are registered by name in `NODES`; splitting an agent later = new nodes and
edges, the state and stage reporting don't change (D36 §5).

Failure policy: each stage retries a limited number of times; a stage that still fails is marked
`failed` and the run continues with what it has, ending `partial`. No research data at all, or no briefing,
ends `failed`. A company that can't be identified stops the run before research (Phase 3.5).
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agents import completeness as C
from app.agents import identify
from app.agents.analysis_writer import analyze, assemble, cited_sources, write
from app.agents.briefing import CompanyNotIdentified
from app.agents.contracts import (STAGES, Analysis, Briefing, BriefingMeta, ResearchFindings, ResearchRequest,
                                  RunStatus, StageName, StageStatus, WriterOutput)
from app.agents.identify import Identification
from app.agents.llm import (DAILY_QUOTA_MSG, UsageLog, build_chat_model, is_daily_quota, is_overloaded,
                            model_name)
from app.agents.quality import run_quality_checks
from app.agents.registry import SourceRegistry
from app.agents.render import render_markdown
from app.agents.research_agent import (COMP_TOOL, INFO_TOOL, NEWS_TOOL, ResearchContext,
                                       run_research_agent)
from app.agents.role_prompts import analysis as PA
from app.agents.role_prompts import quality as PQ
from app.agents.role_prompts import research as PR
from app.agents.role_prompts import writer as PW
from app.agents.store import MemoryRunStore, RunStore
from app.research.depth import get_depth

log = logging.getLogger(__name__)
PROMPT_VERSIONS = {"research": PR.VERSION, "analysis": PA.VERSION, "writer": PW.VERSION, "quality": PQ.VERSION}
RESEARCH_STAGES: tuple[StageName, ...] = ("internal_research", "external_research", "competitor_analysis")
StageCallback = Callable[[StageStatus], None]


@dataclass
class Deps:
    """Injectable dependencies (fakes in tests). Missing ones are built on first use."""
    strong_llm: BaseChatModel | None = None
    small_llm: BaseChatModel | None = None
    service: object | None = None
    internal_fn: Callable[..., list[dict]] | None = None
    identify_fn: Callable[[str, str | None], Identification] | None = None
    store: RunStore | None = None
    research_llm: BaseChatModel | None = None      # default: RESEARCH_MODEL_TIER (small, D41)
    research_max_model_calls: int = 8
    research_attempts: int = 2
    llm_attempts: int = 2
    # Strong model overloaded (503) on every writing attempt -> one try on the small model, marked in the briefing.
    writer_fallback: bool = True
    # Wait before a stage retry: long enough to leave the strong model's per-minute window (free tier: 5 RPM).
    retry_wait_s: float = 20.0

    def strong(self) -> BaseChatModel:
        # No hidden SDK retries on the strong model (free tier: 20 requests/day, rejected ones counted too,
        # AI Studio 2026-11-11). Retries happen only in Run.attempt(): logged, and none after a daily-quota 429.
        self.strong_llm = self.strong_llm or build_chat_model("strong", max_retries=1)
        return self.strong_llm

    def research(self) -> BaseChatModel:
        if self.research_llm is None:
            from app.core.config import get_settings
            tier = get_settings().research_model_tier
            self.research_llm = self.strong() if tier == "strong" else self.small()
        return self.research_llm

    def small(self) -> BaseChatModel:
        self.small_llm = self.small_llm or build_chat_model("small", temperature=0.0)
        return self.small_llm

    def research_service(self):
        if self.service is None:
            from app.tools import research_service
            self.service = research_service()
        return self.service

    def internal(self) -> Callable[..., list[dict]]:
        if self.internal_fn is None:
            from app.tools import search_internal_docs
            self.internal_fn = search_internal_docs
        return self.internal_fn


@dataclass
class RunResult:
    run_id: str
    status: RunStatus
    request: ResearchRequest
    stages: list[StageStatus]
    usage: UsageLog
    findings: ResearchFindings | None = None
    briefing: Briefing | None = None
    markdown: str | None = None
    identification: Identification | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    duration_s: float = 0.0


class RunState(TypedDict, total=False):
    ctx: ResearchContext
    gaps: C.Completeness
    rounds_left: int
    analysis: Analysis | None
    written: WriterOutput | None
    briefing: Briefing | None
    no_data: bool


class Run:
    """Holds the per-run mutable parts the graph nodes share: stages, usage, store, callback."""

    def __init__(self, request: ResearchRequest, deps: Deps, on_stage: StageCallback | None):
        self.id = str(uuid.uuid4())
        self.request, self.deps, self.on_stage = request, deps, on_stage
        self.store = deps.store if deps.store is not None else MemoryRunStore()
        self.usage = UsageLog()
        self.stages = {s: StageStatus(stage=s) for s in STAGES}
        self.warnings: list[str] = []
        self.research_date = datetime.now(timezone.utc)
        self.identification: Identification | None = None

    # ---- persistence that never breaks a run ----
    def safe(self, what: str, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:
            log.warning("persistence (%s) failed: %s", what, exc)
            msg = f"could not save {what} ({type(exc).__name__})"
            if msg not in self.warnings:
                self.warnings.append(msg)
            return None

    def set_stage(self, name: StageName, status: str, detail: str | None = None) -> None:
        st = self.stages[name]
        now = datetime.now(timezone.utc)
        if status == "in_progress":
            st.started_at = st.started_at or now
            st.attempts += 1
        elif status in ("completed", "failed", "skipped"):
            st.finished_at = now
        st.status, st.detail = status, detail
        self.safe("stage status", self.store.save_stage, self.id, st)
        if self.on_stage:
            try:
                self.on_stage(st.model_copy())
            except Exception as exc:  # a UI callback must not break the run
                log.warning("stage callback failed: %s", exc)

    def attempt(self, name: StageName, attempts: int, fn):
        """Run `fn` up to `attempts` times. Returns (ok, value). The caller sets the final status."""
        last = None
        for n in range(attempts):
            self.set_stage(name, "in_progress", None if n == 0 else f"retry {n} after: {last}")
            try:
                return True, fn()
            except CompanyNotIdentified:
                raise
            except Exception as exc:
                last = f"{type(exc).__name__}: {str(exc)[:200]}"
                log.warning("stage %s attempt %d failed: %s", name, n + 1, last)
                if is_daily_quota(exc):   # retrying only burns more calls; the quota resets tomorrow
                    log.warning("daily quota details: %s", str(exc)[:3000])   # quotaId / value / retryDelay
                    return False, DAILY_QUOTA_MSG
                if n + 1 < attempts and self.deps.retry_wait_s:
                    time.sleep(self.deps.retry_wait_s)
        return False, last


# ---------- nodes ----------

def build_graph(run: Run):
    deps, req = run.deps, run.request

    def node_identify(state: RunState) -> RunState:
        fn = deps.identify_fn or identify.identify_company
        ok, ident = run.attempt("company_identification", 1, lambda: fn(req.company, req.website))
        if not ok:   # the check itself crashed: continue like an undecided check
            run.set_stage("company_identification", "completed", f"check failed ({ident}); continued")
            return {}
        run.identification = ident
        run.usage.tavily("identification", ident.credits_used)
        if ident.identified is False:
            run.set_stage("company_identification", "failed", "company not identified")
            raise CompanyNotIdentified(ident)
        if req.website is None and ident.domain_inferred:
            # No website given: use the company's own domain found by the check, so its pages count as
            # official (tier 1) in research and confidence. The stored request keeps what the user typed.
            req.website = ident.domain
        run.set_stage("company_identification", "completed", ident.summary())
        return {}

    def node_research(state: RunState) -> RunState:
        ctx = state["ctx"]
        for s in RESEARCH_STAGES[1:]:          # internal_research is started (and counted) by attempt()
            run.set_stage(s, "in_progress")
        ok, err = run.attempt("internal_research", deps.research_attempts,
                              lambda: run_research_agent(ctx, deps.research(), deps.research_max_model_calls))
        if not ok:
            ctx.registry.findings.errors.append(f"research agent failed: {err}")
        return {"rounds_left": ctx.cfg.max_extra_rounds}

    def node_completeness(state: RunState) -> RunState:
        return {"gaps": C.check(state["ctx"])}

    def route_after_completeness(state: RunState) -> str:
        gaps = state["gaps"]
        if gaps.actionable and state.get("rounds_left", 0) > 0:
            return "extra_research"
        return "close_research"

    def node_extra(state: RunState) -> RunState:
        ctx = state["ctx"]
        done = C.extra_round(ctx, state["gaps"])
        log.info("extra research round: %s", ", ".join(done))
        return {"rounds_left": state["rounds_left"] - 1}

    def node_close_research(state: RunState) -> RunState:
        ctx = state["ctx"]
        C.record_gaps(ctx, state["gaps"])
        _finalize_research_stages(run, ctx)
        ctx.registry.findings.credits_used = ctx.budget.used
        no_data = not ctx.registry.sources
        if no_data:
            for s in ("strategic_analysis", "briefing_writing", "quality_checks"):
                run.set_stage(s, "skipped", "no research data collected")
        return {"no_data": no_data}

    def route_after_research(state: RunState) -> str:
        return END if state.get("no_data") else "analyze"

    def node_analyze(state: RunState) -> RunState:
        reg = state["ctx"].registry
        ok, val = run.attempt("strategic_analysis", deps.llm_attempts,
                              lambda: analyze(reg, req, deps.strong(), run.usage))
        if ok:
            run.set_stage("strategic_analysis", "completed",
                          f"{len(val.opportunities)} opportunities, {len(val.risks)} risks")
            return {"analysis": val}
        run.set_stage("strategic_analysis", "failed", val)
        return {"analysis": None}

    def node_write(state: RunState) -> RunState:
        reg = state["ctx"].registry
        if run.stages["strategic_analysis"].detail == DAILY_QUOTA_MSG:
            # the writer uses the same model: another strong call would only be a second daily-quota 429
            ok, val = False, DAILY_QUOTA_MSG
        else:
            ok, val = run.attempt("briefing_writing", deps.llm_attempts,
                                  lambda: write(reg, req, state.get("analysis"), deps.strong(), run.usage,
                                                run.research_date))
        fallback, reason = None, None
        if not ok and deps.writer_fallback and (is_overloaded(val or "") or val == DAILY_QUOTA_MSG):
            # Strong model overloaded (503) or out of its daily quota: the small model (separate, much larger daily
            # limit) writes instead of losing the research already paid for (2026-11-24: 4 of 6 runs hit 503 on
            # flash; rejected requests count toward the 20/day quota, so a 429 can follow a run of 503s).
            reason = "main model's daily quota reached" if val == DAILY_QUOTA_MSG else "main model overloaded"
            log.warning("writer: %s, trying the fallback model once", reason)
            ok, val = run.attempt("briefing_writing", 1,
                                  lambda: write(reg, req, state.get("analysis"), deps.small(), run.usage,
                                                run.research_date))
            fallback = model_name(deps.small()) if ok else None
        if not ok:
            run.set_stage("briefing_writing", "failed", val)
            run.set_stage("quality_checks", "skipped", "no briefing to check")
            return {"written": None, "briefing": None}
        briefing = assemble(reg, req, state.get("analysis"), val, _meta(run, state["ctx"]))
        briefing.meta.company = display_name(req.company, val.company_name)
        briefing.meta.fallback_writer = fallback
        run.set_stage("briefing_writing", "completed",
                      f"written by the fallback model {fallback} ({reason})" if fallback else None)
        return {"written": val, "briefing": briefing}

    def route_after_write(state: RunState) -> str:
        return "quality" if state.get("briefing") is not None else END

    def node_quality(state: RunState) -> RunState:
        b, reg = state["briefing"], state["ctx"].registry
        ok, val = run.attempt("quality_checks", 1,
                              lambda: run_quality_checks(b, reg, req.company, _judge(deps, run), run.usage))
        if ok:
            detail = f"{len(val.sections_missing)} sections missing, {len(val.generic_dropped)} generic removed"
            run.set_stage("quality_checks", "completed", detail)
        else:
            run.set_stage("quality_checks", "failed", val)
        return {}

    nodes = {"identify": node_identify, "research": node_research, "completeness": node_completeness,
             "extra_research": node_extra, "close_research": node_close_research, "analyze": node_analyze,
             "write": node_write, "quality": node_quality}
    g = StateGraph(RunState)
    for name, fn in nodes.items():
        g.add_node(name, fn)
    g.add_edge(START, "identify")
    g.add_edge("identify", "research")
    g.add_edge("research", "completeness")
    g.add_conditional_edges("completeness", route_after_completeness, ["extra_research", "close_research"])
    g.add_edge("extra_research", "completeness")
    g.add_conditional_edges("close_research", route_after_research, ["analyze", END])
    g.add_edge("analyze", "write")
    g.add_conditional_edges("write", route_after_write, ["quality", END])
    g.add_edge("quality", END)
    return g.compile()


NODES = ("identify", "research", "completeness", "extra_research", "close_research", "analyze", "write", "quality")


def _judge(deps: Deps, run: Run) -> BaseChatModel | None:
    try:
        return deps.small()
    except Exception as exc:
        run.warnings.append(f"generic-statement judge unavailable ({type(exc).__name__})")
        return None


def _finalize_research_stages(run: Run, ctx: ResearchContext) -> None:
    reg, calls = ctx.registry, set(ctx.tool_calls)
    f = reg.findings
    internal_err = any(e.startswith("internal") for e in f.errors)
    if reg.internal_queries:
        n = len(f.internal.source_ids)
        if internal_err and not n:
            run.set_stage("internal_research", "failed", "internal search failed")
        else:
            run.set_stage("internal_research", "completed", f"{len(reg.internal_queries)} queries, {n} excerpts")
    else:
        run.set_stage("internal_research", "skipped", "not searched")

    web_ids = f.web.source_ids
    if ctx.web_disabled and not web_ids:
        run.set_stage("external_research", "failed", ctx.web_disabled)
    elif {INFO_TOOL, NEWS_TOOL} & calls or reg.queried_purposes - {"competitors"}:
        run.set_stage("external_research", "completed",
                      f"{len(web_ids)} sources, {ctx.budget.used} credits, {f.rounds} round(s)")
    elif any(e.startswith("research agent failed") for e in f.errors):
        run.set_stage("external_research", "failed", "research agent failed")
    else:
        run.set_stage("external_research", "skipped", "not searched")

    comp = f.competitive.source_ids
    if "competitors" in reg.queried_purposes or COMP_TOOL in calls:
        run.set_stage("competitor_analysis", "completed", f"{len(comp)} competitive sources")
    elif ctx.web_disabled or any(e.startswith("research agent failed") for e in f.errors):
        run.set_stage("competitor_analysis", "failed", ctx.web_disabled or "research agent failed")
    else:
        run.set_stage("competitor_analysis", "skipped", "not searched")


def display_name(typed: str, written: str | None) -> str:
    """Title name: the writer's official name ('elbit' → 'Elbit Systems') when it plausibly names the same
    company (shares a word with what was typed, or the typed name isn't Latin, e.g. 'אלביט'); else as typed."""
    name = " ".join((written or "").split())
    if not name or len(name) > 100:
        return typed
    typed_words = {w for w in re.findall(r"[a-z0-9]+", typed.lower()) if len(w) >= 2}
    if not typed_words:
        return name
    name_l = name.lower()
    return name if any(w in name_l for w in typed_words) else typed


def _meta(run: Run, ctx: ResearchContext) -> BriefingMeta:
    r, f = run.request, ctx.registry.findings
    failed = [s for s, st in run.stages.items() if st.status == "failed"]
    return BriefingMeta(company=r.company, language=r.language, meeting_type=r.meeting_type,
                        meeting_goal=r.meeting_goal, depth=r.depth, website=r.website,
                        research_date=run.research_date, search_languages=f.search_languages,
                        local_language_note=f.local_language_note, prompt_versions=PROMPT_VERSIONS,
                        is_partial=bool(failed), incomplete_stages=failed, user_context=r.user_context,
                        user_context_type=r.user_context_type)


def run_research(request: ResearchRequest, deps: Deps | None = None,
                 on_stage: StageCallback | None = None) -> RunResult:
    """One full research run. Raises `CompanyNotIdentified` (after saving the failed run) when the company
    can't be identified; every other failure ends in a `RunResult` with status `partial` or `failed`."""
    deps = deps or Deps()
    run = Run(request, deps, on_stage)
    started = time.perf_counter()
    run.safe("run", run.store.create_run, run.id, request, {
        "prompt_versions": PROMPT_VERSIONS, "depth_config": asdict(get_depth(request.depth))})
    for st in run.stages.values():
        run.safe("stage status", run.store.save_stage, run.id, st)

    state: RunState = {}
    error = None
    try:
        ctx = ResearchContext(request=request, registry=SourceRegistry(request.company), usage=run.usage,
                              service=_LazyService(deps), internal_fn=lambda q, k=10: deps.internal()(q, k=k))
        state = build_graph(run).invoke({"ctx": ctx}, {"recursion_limit": 40})
    except CompanyNotIdentified as exc:
        _finish(run, "failed", None, None, str(exc), started)
        raise
    except Exception as exc:  # unexpected: never lose the run record
        log.exception("research run crashed")
        error = f"{type(exc).__name__}: {str(exc)[:300]}"

    briefing: Briefing | None = state.get("briefing")
    findings = state["ctx"].registry.findings if state.get("ctx") else None
    markdown = None
    if briefing is not None:
        failed = [s for s, st in run.stages.items() if st.status == "failed"]
        briefing.meta.is_partial, briefing.meta.incomplete_stages = bool(failed), failed
        briefing.sources = cited_sources(briefing, state["ctx"].registry)
        briefing.meta.models = {role: model_name(m) for role, m in
                                (("research", deps.research_llm), ("analysis_writing", deps.strong_llm),
                                 ("quality_judge", deps.small_llm)) if m is not None}
        markdown = render_markdown(briefing)
        status: RunStatus = "partial" if failed else "completed"
    else:
        status = "failed"
        error = error or ("no research data collected" if state.get("no_data") else
                          run.stages["briefing_writing"].detail or "no briefing was produced")
    result = _finish(run, status, briefing, markdown, error, started, findings)
    return result


class _LazyService:
    """Builds the Tavily-backed service only when the first web call happens."""

    def __init__(self, deps: Deps):
        self._deps = deps

    def __getattr__(self, name):
        return getattr(self._deps.research_service(), name)


def _finish(run: Run, status: RunStatus, briefing, markdown, error, started, findings=None) -> RunResult:
    if briefing is not None:
        run.safe("briefing", run.store.save_briefing, run.id, briefing, markdown)
    run.safe("usage", run.store.save_usage, run.id, run.usage.events)
    run.safe("run", run.store.finish_run, run.id, status, error, run.usage.totals(), findings,
             briefing.quality if briefing else None)
    return RunResult(run_id=run.id, status=status, request=run.request, stages=list(run.stages.values()),
                     usage=run.usage, findings=findings, briefing=briefing, markdown=markdown,
                     identification=run.identification, error=error, warnings=run.warnings,
                     duration_s=time.perf_counter() - started)
