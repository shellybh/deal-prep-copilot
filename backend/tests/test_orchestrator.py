"""Phase 4-lite: contracts, registry, confidence, completeness, quality checks and the graph (no network)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from app.agents import completeness as C
from app.agents.analysis_writer import assemble
from app.agents.briefing import CompanyNotIdentified
from app.agents.confidence import confidence_for, to_claim
from app.agents.contracts import (SECTION_KEYS, WRITER_SECTIONS, Analysis, Briefing, BriefingMeta,
                                  BriefingSection, ClaimDraft, GenericVerdict, Insight, ResearchRequest,
                                  SectionDraft, WriterOutput)
from app.agents.identify import Identification
from app.agents.llm import UsageLog
from app.agents import orchestrator as orchestrator_mod
from app.agents.orchestrator import Deps, run_research
from app.agents.quality import run_quality_checks
from app.agents.registry import SourceRegistry
from app.agents.render import render_markdown
from app.agents.research_agent import ResearchContext
from app.agents.store import MemoryRunStore
from app.research.provider import CreditBudget
from app.research.service import ExternalResearchResult
from app.research.sources import Source
from app.research.urls import normalize_url

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


# ---------------------------------------------------------------- fakes

def src(url, title, purposes, tier=2, published=NOW - timedelta(hours=5), source_type="news", snippet="snip"):
    n = normalize_url(url)
    return Source(id="x", url=url, normalized_url=n, title=title, outlet=n.split("/")[2].removeprefix("www."),
                  published_at=published, retrieved_at=NOW, language="en", source_type=source_type, tier=tier,
                  snippet=snippet, query_purposes=list(purposes))


WEB = {
    "profile": [src("https://acme.com/about", "About Acme", ["profile"], tier=1, source_type="official")],
    "financial": [src("https://reuters.com/acme-q3", "Acme Q3 revenue $10M", ["financial"])],
    "people": [src("https://acme.com/team", "Acme leadership", ["people"], tier=1, source_type="official")],
    "press": [],
    "israel": [],
    "news_recent": [src("https://ft.com/acme-deal", "Acme signs deal", ["news_recent"])],
    "news": [],
    "competitors": [src(f"https://g2.com/acme-vs-{n}", f"Acme vs Rival{n}", ["competitors"], tier=3)
                    for n in range(4)],
}


class FakeService:
    """research_company returns canned sources per purpose and charges 1 credit per purpose."""

    def __init__(self, web=None, empty=()):
        self.web = WEB if web is None else web
        self.empty = set(empty)
        self.calls: list[set] = []

    def research_company(self, company, *, purposes=None, budget=None, **kw):
        purposes = set(purposes or [])
        self.calls.append(purposes)
        res = ExternalResearchResult(company=company, depth="standard", search_languages=["en", "he"])
        for p in sorted(purposes):
            budget.check(1)
            budget.charge(1)
            res.queries_run.append({"purpose": p})
            if p not in self.empty:
                res.sources += [s.model_copy() for s in self.web.get(p, [])]
        res.credits_used = len(purposes)
        return res

    def fetch_pages(self, urls, budget=None):
        return {"pages": [{"url": urls[0], "content": "full page text"}], "failed": []}


CHUNKS = [{"citation": "battlecard_rival0.md § Snapshot", "file_name": "battlecard_rival0.md",
           "document_id": "d1", "version": 1, "content": "Rival0 is weak on compliance; Acme uses Rival0."}]


def internal_fn(query, k=10):
    return CHUNKS


def tc(name, args, i):
    return {"name": name, "args": args, "id": str(i), "type": "tool_call"}


RESEARCH_SCRIPT = [
    AIMessage(content="", tool_calls=[tc("search_company_info", {}, 1), tc("search_company_news", {}, 2),
                                      tc("search_competitors", {}, 3),
                                      tc("search_internal_docs", {"query": "Acme"}, 4)],
              usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}),
    AIMessage(content="INTERNAL: battlecard I1\nWEB: W1 W2\nCOMPETITIVE: W5\nGAPS: none",
              usage_metadata={"input_tokens": 200, "output_tokens": 30, "total_tokens": 230}),
]


def good_analysis():
    return Analysis(
        opportunities=[Insight(title="Compliance gap at Rival0", description="Acme uses Rival0 [I1]",
                               evidence_source_ids=["I1", "W99"], importance="High",
                               importance_rationale="decides the deal", why_it_matters="switch trigger",
                               how_to_address="lead with compliance")],
        risks=[Insight(title="Big new deal", description="Acme signed a deal", evidence_source_ids=["W4"],
                       importance="Medium", importance_rationale="r", why_it_matters="w", how_to_address="h")],
        fit_assessment=[ClaimDraft(text="Good fit", info_type="ai_analysis", source_ids=["W1"])],
        recommendations=[ClaimDraft(text="Ask about Rival0", info_type="ai_recommendation", source_ids=["I1"])])


def good_writer():
    sections = []
    for k in WRITER_SECTIONS:
        if k == "key_people":
            sections.append(SectionDraft(key=k, claims=[], missing_reason="no public leadership data"))
        elif k == "financial_overview":
            sections.append(SectionDraft(key=k, claims=[ClaimDraft(text="Q3 2026 revenue $10M",
                                                                   info_type="external_fact",
                                                                   source_ids=["W2"])]))
        else:
            sections.append(SectionDraft(key=k, claims=[ClaimDraft(text=f"{k} fact", info_type="external_fact",
                                                                   source_ids=["W1"])]))
    return WriterOutput(summary=[ClaimDraft(text="Acme signed a deal", info_type="external_fact",
                                            source_ids=["W4"]),
                                 ClaimDraft(text="Competition is intense", info_type="ai_analysis",
                                            source_ids=["W5"])],
                        sections=sections)


class FakeLLM(BaseChatModel):
    """Tool-calling script for the Research Agent + a queue of structured outputs (or exceptions)."""
    script: list = []
    structured: list = []
    model: str = "fake-strong"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self.script.pop(0) if self.script else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema, include_raw=False, **kwargs):
        def run(_messages):
            item = self.structured.pop(0)
            if isinstance(item, Exception):
                raise item
            raw = AIMessage(content="", usage_metadata={"input_tokens": 50, "output_tokens": 20,
                                                        "total_tokens": 70})
            return {"raw": raw, "parsed": item, "parsing_error": None}
        return RunnableLambda(run)


def ident_ok(company, domain=None):
    return Identification(company, domain, True, via="web", web_sources=2, credits_used=1)


def make_deps(structured=None, judge=None, script=None, service=None, store=None, **kw):
    strong = FakeLLM(script=list(script if script is not None else RESEARCH_SCRIPT),
                     structured=list(structured if structured is not None else [good_analysis(), good_writer()]))
    small = FakeLLM(script=[], structured=list(judge if judge is not None else [GenericVerdict(), GenericVerdict()]),
                    model="fake-small")
    return Deps(strong_llm=strong, small_llm=small, research_llm=strong, service=service or FakeService(), internal_fn=internal_fn,
                identify_fn=kw.pop("identify_fn", ident_ok), store=store or MemoryRunStore(), retry_wait_s=0, **kw)


REQ = ResearchRequest(company="Acme", meeting_type="sales", meeting_goal="first call", website="https://acme.com")


# ---------------------------------------------------------------- contracts

def test_request_validation():
    r = ResearchRequest(company="  Acme   Ltd ", website="https://www.acme.com/x", country=" ")
    assert (r.company, r.website, r.country, r.depth, r.language) == ("Acme Ltd", "acme.com", None, "standard", "en")
    with pytest.raises(ValidationError, match="classification"):
        ResearchRequest(company="Acme", user_context="they use X")
    with pytest.raises(ValidationError):
        ResearchRequest(company="Acme", website="not a url")
    with pytest.raises(ValidationError):
        ResearchRequest(company="Acme", compare_with=["a", "b", "c", "d"])
    with pytest.raises(ValidationError):
        ResearchRequest(company="")
    with pytest.raises(ValidationError):
        ResearchRequest(company="Acme", meeting_type="lunch")
    assert ResearchRequest(company="Acme", compare_with=["B", " B ", "C"]).compare_with == ["B", "C"]


def _meta():
    return BriefingMeta(company="Acme", language="en", meeting_type="sales", depth="standard", research_date=NOW)


def test_briefing_needs_all_12_sections_and_sorts_them():
    secs = [BriefingSection(key=k, status="missing_info") for k in reversed(SECTION_KEYS)]
    b = Briefing(meta=_meta(), sections=secs)
    assert [s.key for s in b.sections] == list(SECTION_KEYS)
    with pytest.raises(ValidationError, match="12 sections"):
        Briefing(meta=_meta(), sections=secs[:-1])


# ---------------------------------------------------------------- registry + confidence

def test_registry_ids_dedup_and_sections():
    reg = SourceRegistry("Acme")
    a = reg.add_web(WEB["profile"][0])
    again = reg.add_web(WEB["profile"][0].model_copy(update={"query_purposes": ["people"]}))
    comp = reg.add_web(WEB["competitors"][0])
    i = reg.add_internal(CHUNKS[0])
    assert (a.id, again.id, comp.id, i.id) == ("W1", "W1", "W2", "I1")
    assert a.purposes == ["people", "profile"]
    assert reg.findings.web.source_ids == ["W1"] and reg.findings.competitive.source_ids == ["W2"]
    assert reg.findings.internal.source_ids == ["I1"]
    assert reg.add_internal(CHUNKS[0]).id == "I1"


def test_confidence_rules():
    reg = SourceRegistry("Acme")
    official = reg.add_web(WEB["profile"][0]).id                       # tier 1
    news1 = reg.add_web(WEB["financial"][0]).id                        # tier 2 reuters
    news2 = reg.add_web(WEB["news_recent"][0]).id                      # tier 2 ft
    blog = reg.add_web(src("https://blog.x.com/a", "Acme blog", ["profile"], tier=4)).id
    internal = reg.add_internal(CHUNKS[0]).id
    assert confidence_for([official], reg) == "high"
    assert confidence_for([news1], reg) == "medium"
    assert confidence_for([news1, news2], reg) == "high"            # two independent outlets
    assert confidence_for([blog], reg) == "low"
    assert confidence_for([internal], reg) == "high"
    assert confidence_for([], reg) == "low"
    assert confidence_for([official], reg, is_opinion=True) == "low"
    reg.get(news1).also_reported_by.append("https://bbc.com/x")
    assert confidence_for([news1], reg) == "high"                   # corroborated by a second outlet


def test_to_claim_drops_unknown_ids_and_flags_conflicts():
    reg = SourceRegistry("Acme")
    w1, w2 = reg.add_web(WEB["financial"][0]).id, reg.add_web(WEB["news_recent"][0]).id
    stats = {}
    c = to_claim(ClaimDraft(text=" Revenue $10M ", info_type="external_fact", source_ids=[w1, "W77", w1],
                            conflict_source_ids=[w2, "W88"]), reg, stats)
    assert (c.text, c.source_ids, c.is_conflict, c.conflicting_source_ids) == ("Revenue $10M", [w1], True, [w2])
    assert stats["unknown_ids"] == 1
    assert to_claim(ClaimDraft(text="x", info_type="user_provided"), reg).confidence is None


# ---------------------------------------------------------------- completeness

def ctx_for(req=REQ, service=None):
    return ResearchContext(request=req, registry=SourceRegistry(req.company), usage=UsageLog(),
                           service=service or FakeService(), internal_fn=internal_fn)


def test_completeness_complete_after_full_research():
    ctx = ctx_for()
    ctx.web_search({"profile", "financial", "people", "press", "israel"})
    ctx.web_search({"news_recent", "news"})
    ctx.web_search({"competitors"})
    ctx.internal_search("Acme")
    assert C.check(ctx).complete


def test_completeness_actionable_only_for_unsearched():
    service = FakeService(empty={"financial"})
    ctx = ctx_for(service=service)
    ctx.web_search({"profile", "financial"})          # financial queried, nothing found
    g = C.check(ctx)
    assert set(g.gaps) == {"internal", "financial", "people", "news", "competitors"}
    assert g.actionable == {"internal", "people", "news", "competitors"}   # not financial: same query again
    C.extra_round(ctx, g)
    assert service.calls[-1] == {"people", "news_recent", "news", "competitors"}
    g2 = C.check(ctx)
    assert set(g2.gaps) == {"financial"} and not g2.actionable
    C.record_gaps(ctx, g2)
    assert ctx.registry.findings.web.gaps == ["financial: no relevant financial sources found"]


def test_completeness_competitor_minimum_by_depth():
    ctx = ctx_for(ResearchRequest(company="Acme", depth="in_depth"))
    ctx.web_search({"competitors"})                   # 4 sources < 5 for in-depth
    assert "competitors" in C.check(ctx).gaps and "competitors" not in C.check(ctx).actionable


def test_no_web_rounds_after_budget_exhausted():
    ctx = ctx_for()
    ctx.budget = CreditBudget(0)
    out = ctx.web_search({"profile"})                 # the cap blocks the call before it is sent
    assert "error" in out and ctx.registry.findings.errors
    ctx.registry.budget_exhausted = True              # what the real service reports at the cap
    g = C.check(ctx)
    assert "profile" in g.gaps and g.actionable == {"internal"}


# ---------------------------------------------------------------- full graph

def test_full_run_completed_with_sources_and_stages():
    seen = []
    deps = make_deps()
    r = run_research(REQ, deps, on_stage=lambda st: seen.append((st.stage, st.status)))
    assert r.status == "completed", (r.error, [(s.stage, s.status, s.detail) for s in r.stages])
    assert all(s.status == "completed" for s in r.stages)
    b = r.briefing
    assert [s.key for s in b.sections] == list(SECTION_KEYS)
    # citation integrity: every cited ID exists in the briefing's sources
    ids = {s.id for s in b.sources}
    for c in b.all_claims():
        assert set(c.source_ids) <= ids
    for s in b.sections:
        for i in s.insights:
            assert set(i.evidence_source_ids) <= ids
    assert b.quality.unknown_source_ids_removed == 1                    # W99 in the analysis
    assert b.section("key_people").status == "missing_info"
    assert b.section("key_people").missing_reason == "no public leadership data"
    assert b.section("business_opportunities").insights[0].confidence == "high"
    assert ("company_identification", "in_progress") in seen and ("quality_checks", "completed") in seen
    totals = r.usage.totals()
    assert totals["llm_calls"] == 6 and totals["tavily_credits"] >= 1   # 2 research + analysis + writer + 2 judge
    assert set(r.usage.by_agent()) >= {"research", "analysis", "writer", "quality", "identification"}
    assert "## Sources" in r.markdown and "[1]" in r.markdown
    store = deps.store
    assert store.runs[r.run_id]["status"] == "completed"
    assert len(store.briefings) == 1 and store.sources and store.claims and store.usage
    assert {row["stage"] for (rid, _), row in store.stages.items() if rid == r.run_id} == {s.stage for s in r.stages}
    assert b.meta.prompt_versions["research"].startswith("research/")
    # regression (first live run): parallel tool calls double-counted credits; stages started twice
    assert r.usage.by_agent()["research"]["tavily_credits"] == r.findings.credits_used
    assert all(s.attempts <= 1 for s in r.stages)
    assert next(s for s in r.stages if s.stage == "internal_research").attempts == 1
    ids = list(r.findings.sources)
    assert len(ids) == len(set(ids)) and sorted(r.findings.web.source_ids + r.findings.competitive.source_ids,
                                                key=lambda x: int(x[1:])) == [i for i in ids if i.startswith("W")]


def test_extra_round_bounded_by_depth():
    # agent skips the competitor tool: standard depth runs one extra round with exactly that search
    script = [AIMessage(content="", tool_calls=[tc("search_company_info", {}, 1), tc("search_company_news", {}, 2),
                                                tc("search_internal_docs", {"query": "Acme"}, 3)]),
              AIMessage(content="notes"),
              AIMessage(content="still no competitors")]                 # after the one nudge
    service = FakeService()
    r = run_research(REQ, make_deps(script=script, service=service))
    assert {"competitors"} in service.calls and r.findings.rounds == 2
    # quick depth: zero extra rounds even with gaps
    service_q = FakeService()
    rq = run_research(REQ.model_copy(update={"depth": "quick"}), make_deps(script=list(script), service=service_q))
    assert {"competitors"} not in service_q.calls and rq.findings.rounds == 1
    assert any("competitors" in g for g in rq.findings.competitive.gaps)
    assert next(s for s in rq.stages if s.stage == "competitor_analysis").status == "skipped"


def test_analysis_failure_continues_as_partial():
    deps = make_deps(structured=[RuntimeError("boom"), RuntimeError("boom"), good_writer()])
    r = run_research(REQ, deps)
    assert r.status == "partial" and r.briefing is not None
    st = {s.stage: s for s in r.stages}
    assert st["strategic_analysis"].status == "failed" and st["strategic_analysis"].attempts == 2
    assert r.briefing.meta.is_partial and "strategic_analysis" in r.briefing.meta.incomplete_stages
    assert r.briefing.section("business_opportunities").status == "missing_info"
    assert "Partial briefing" in r.markdown


def test_retry_succeeds_on_second_attempt():
    deps = make_deps(structured=[RuntimeError("429"), good_analysis(), good_writer()])
    r = run_research(REQ, deps)
    st = {s.stage: s for s in r.stages}
    assert r.status == "completed" and st["strategic_analysis"].attempts == 2


def test_writer_failure_fails_run_without_briefing():
    deps = make_deps(structured=[good_analysis(), RuntimeError("x"), RuntimeError("x")])
    r = run_research(REQ, deps)
    assert r.status == "failed" and r.briefing is None and r.markdown is None
    st = {s.stage: s.status for s in r.stages}
    assert st["briefing_writing"] == "failed" and st["quality_checks"] == "skipped"
    assert deps.store.runs[r.run_id]["status"] == "failed" and not deps.store.briefings


OVERLOADED = RuntimeError("GoogleAPIError: 503 UNAVAILABLE. This model is currently experiencing high demand.")


def test_writer_overloaded_falls_back_to_small_model_once():
    # 2026-11-24: 4 of 6 live runs hit 503 on flash; the writer now tries the small model once
    deps = make_deps(structured=[good_analysis(), OVERLOADED, OVERLOADED],
                     judge=[good_writer(), GenericVerdict(), GenericVerdict()])
    r = run_research(REQ, deps)
    assert r.status == "completed" and r.briefing is not None
    assert r.briefing.meta.fallback_writer == "fake-small"
    st = {s.stage: s for s in r.stages}
    assert "fallback model fake-small" in st["briefing_writing"].detail
    assert "Written by the fallback model (fake-small)" in r.markdown
    assert not deps.small_llm.structured          # writer + 2 judge runs used the small model


def test_writer_fallback_only_on_overload():
    # another error: no fallback, the run fails as before (small model never asked to write)
    deps = make_deps(structured=[good_analysis(), RuntimeError("x"), RuntimeError("x")])
    r = run_research(REQ, deps)
    assert r.status == "failed" and len(deps.small_llm.structured) == 2
    # fallback turned off: overload fails the run
    deps = make_deps(structured=[good_analysis(), OVERLOADED, OVERLOADED], writer_fallback=False)
    assert run_research(REQ, deps).status == "failed"
    # fallback also overloaded / failing: failed, no briefing
    deps = make_deps(structured=[good_analysis(), OVERLOADED, OVERLOADED], judge=[OVERLOADED])
    r = run_research(REQ, deps)
    assert r.status == "failed" and r.briefing is None


def test_normal_run_has_no_fallback_note():
    r = run_research(REQ, make_deps())
    assert r.briefing.meta.fallback_writer is None and "fallback" not in r.markdown


def test_not_identified_raises_and_saves_failed_run():
    deps = make_deps(identify_fn=lambda c, d: Identification(c, d, False))
    with pytest.raises(CompanyNotIdentified):
        run_research(REQ, deps)
    run = next(iter(deps.store.runs.values()))
    assert run["status"] == "failed" and "not identified" in run["error"]
    assert deps.strong_llm.script == RESEARCH_SCRIPT                    # no LLM call happened


def test_no_research_data_fails_run():
    empty_service = FakeService(web={})
    deps = make_deps(service=empty_service)
    deps.internal_fn = lambda q, k=10: []
    r = run_research(REQ, deps)
    assert r.status == "failed" and r.error == "no research data collected"
    assert {s.stage: s.status for s in r.stages}["strategic_analysis"] == "skipped"


def test_store_failure_is_a_warning_not_a_crash():
    class Broken(MemoryRunStore):
        def save_briefing(self, *a):
            raise ConnectionError("db down")
    r = run_research(REQ, make_deps(store=Broken()))
    assert r.status == "completed" and any("briefing" in w for w in r.warnings)


def test_generic_judge_drops_items_and_marks_empty_section():
    judge = [GenericVerdict(generic_ids=["s1", "risks_challenges.i0"], reasons={"s1": "any company"})]
    r = run_research(REQ, make_deps(judge=judge))
    b = r.briefing
    assert [c.text for c in b.summary] == ["Acme signed a deal"]
    assert b.section("risks_challenges").status == "missing_info"
    assert len(b.quality.generic_dropped) == 2 and b.quality.generic_check_ran
    assert "generic" in r.markdown


def test_judge_blanks_generic_insight_line_and_keeps_insight():
    judge = [GenericVerdict(generic_ids=["business_opportunities.i0.why", "risks_challenges.i0.rating"],
                            reasons={"business_opportunities.i0.why": "fits any title"})]
    r = run_research(REQ, make_deps(judge=judge))
    opp = r.briefing.section("business_opportunities").insights[0]
    risk = r.briefing.section("risks_challenges").insights[0]
    assert opp.why_it_matters == "" and opp.how_to_address == "lead with compliance"
    assert risk.importance_rationale == "" and r.briefing.section("risks_challenges").status == "complete"
    assert len(r.briefing.quality.generic_dropped) == 2
    assert "switch trigger" not in r.markdown and "lead with compliance" in r.markdown


def test_judge_sees_insight_lines_and_user_provided_summary(monkeypatch):
    from app.agents import quality as Q
    seen = {}

    def spy_call(llm, schema, messages, **kw):
        seen["items"] = messages[1].content
        return GenericVerdict()
    monkeypatch.setattr(Q, "structured_call", spy_call)
    writer = good_writer()
    writer.summary.append(ClaimDraft(text="The goal is a first call", info_type="user_provided", source_ids=[]))
    run_research(REQ, make_deps(structured=[good_analysis(), writer]))
    items = seen["items"]
    assert "business_opportunities.i0.why" in items and "business_opportunities.i0.how" in items
    assert "risks_challenges.i0.rating" in items and "The goal is a first call" in items


def test_prompt_v2_rules_present():
    from app.agents.role_prompts import analysis as PA, quality as PQ, writer as PW
    assert PA.VERSION == "analysis/v5" and PW.VERSION == "writer/v5" and PQ.VERSION == "quality/v4"
    assert "Size counts the same as growth" in PQ.SYSTEM and "250,000 customers" in PQ.SYSTEM   # quality/v4
    assert "A fit gap that our own documents show IS a risk" in PA.SYSTEM.replace("\n", " ")   # analysis/v5
    # 2026-11-24 elbit run: no-CRM-history gap cited to a web source; growth-only opportunity; inline IDs
    assert "can't show what our records lack" in PA.SYSTEM.replace("\\\n", "").replace("\n", " ")
    assert "can't show what our records lack" in PW.SYSTEM.replace("\n", " ")
    assert "not in the claim text" in PW.SYSTEM
    assert "only because it is growing or large" in PQ.SYSTEM.replace("\n", " ")
    PQ.SYSTEM.format(company="Acme")
    w = PW.SYSTEM
    assert "Don't restate it" in w and "Existing relationship" in w and "whose competitor" in w
    assert '"Ask:" prefix' in w and "tier 1" in w and "Hebrew: correct spelling" in w
    assert "whereas NexaStream" in w and "its own claim" in w   # writer/v3
    assert "One event = one claim" in w.replace("\n", " ") and "what it lacks" in w   # writer/v4
    assert "Hebrew letters only" in w and "Hebrew letters only" in PA.SYSTEM            # writer/v4, analysis/v3
    assert "large backlog alone" in PA.SYSTEM and "what it lacks" in PA.SYSTEM          # analysis/v3
    assert "Existing relationship" in PA.SYSTEM and "could follow any title" in PA.SYSTEM
    assert "restates the meeting goal" in PQ.SYSTEM and "why it matters:" in PQ.SYSTEM
    PW.SYSTEM.format(company="Acme", language="English", meeting_block="m", section_list="s")
    PA.SYSTEM.format(company="Acme", language="English", meeting_block="m")


def test_judge_runs_twice_and_drops_union_of_flags():
    judge = [GenericVerdict(generic_ids=["s1"], reasons={"s1": "any company"}),
             GenericVerdict(generic_ids=["business_opportunities.i0.why"])]
    r = run_research(REQ, make_deps(judge=judge))
    assert len(r.briefing.quality.generic_dropped) == 2
    assert r.briefing.section("business_opportunities").insights[0].why_it_matters == ""


def test_failed_second_judge_run_keeps_first_verdict():
    judge = [GenericVerdict(generic_ids=["s1"]), RuntimeError("503")]
    r = run_research(REQ, make_deps(judge=judge))
    assert r.briefing.quality.generic_check_ran and len(r.briefing.quality.generic_dropped) == 1


def test_judge_failure_keeps_briefing():
    r = run_research(REQ, make_deps(judge=[RuntimeError("judge down")]))
    assert r.status == "completed" and not r.briefing.quality.generic_check_ran
    assert any("did not run" in n for n in r.briefing.quality.notes)


# ---------------------------------------------------------------- quality checks (unit)

def test_quality_relabels_and_drops():
    reg = SourceRegistry("Acme")
    w = reg.add_web(WEB["financial"][0]).id
    i = reg.add_internal(CHUNKS[0]).id
    written = WriterOutput(summary=[], sections=[
        SectionDraft(key="company_overview", claims=[
            ClaimDraft(text="no source fact", info_type="external_fact"),
            ClaimDraft(text="internal said as web", info_type="external_fact", source_ids=[i]),
            ClaimDraft(text="web said as internal", info_type="internal_document", source_ids=[w]),
            ClaimDraft(text="uncited analysis", info_type="ai_analysis")]),
    ])
    b = assemble(reg, REQ, Analysis(), written, _meta())
    q = run_quality_checks(b, reg, "Acme", None, UsageLog())
    types = [c.info_type for c in b.section("company_overview").claims]
    assert types == ["unverified", "internal_document", "external_fact"]
    assert (q.facts_without_source, q.info_type_relabeled, q.uncited_analysis_dropped) == (1, 2, 0 + 1)
    assert "key_people" in q.sections_missing and not q.generic_check_ran


def test_quality_fixes_arabic_article_in_hebrew_words():
    # monday.com 2026-11-24 "לוחות المחוונים", elbit 2026-11-16 "المיוחד"
    from app.agents.contracts import QualityReport
    from app.agents.quality import fix_foreign_script
    r = run_research(REQ.model_copy(update={"language": "he"}), make_deps())
    b = r.briefing
    b.summary[0].text = "כיצד מנהלים את לוחות المחוונים? ציוד المיוחד"
    b.sections[0].missing_reason = "מילה مرحبا זרה"
    ins = b.section("business_opportunities").insights[0]
    ins.why_it_matters = "שיפור לוחות المחוונים"
    rep = QualityReport()
    fix_foreign_script(b, rep)
    assert b.summary[0].text == "כיצד מנהלים את לוחות המחוונים? ציוד המיוחד"
    assert ins.why_it_matters == "שיפור לוחות המחוונים"
    assert "מילה مرحبا זרה" == b.sections[0].missing_reason          # not an article: left, but reported
    assert any("Fixed 3 Hebrew word" in n for n in rep.notes) and any("مرحبا" in n for n in rep.notes)
    # the exact strings of the two live runs
    b.summary[0].text = "לוחות المחוונים ו-المיוחד"
    fix_foreign_script(b, QualityReport())
    assert b.summary[0].text == "לוחות המחוונים ו-המיוחד"
    clean = QualityReport()
    fix_foreign_script(run_research(REQ, make_deps()).briefing, clean)
    assert clean.notes == []


# ---------------------------------------------------------------- rendering

def test_render_hebrew_and_english():
    r = run_research(REQ.model_copy(update={"language": "he"}), make_deps())
    md = r.markdown
    assert md.startswith("# תדריך הכנה לפגישה: Acme")
    assert "## תקציר בעמוד אחד" in md and "### 4. אנשי מפתח" in md and "חסר מידע" in md
    en = render_markdown(run_research(REQ, make_deps()).briefing)
    assert "## One-page summary" in en and "### 12. Suggested Next Steps" in en
    assert "_(AI analysis)_" in en or "recommendation" in en


def test_user_context_labeled():
    req = REQ.model_copy(update={"user_context": "They plan to replace Rival0", "user_context_type": "assumption"})
    w = good_writer()
    w.sections[0].claims.append(ClaimDraft(text="They plan to replace Rival0", info_type="user_provided"))
    r = run_research(req, make_deps(structured=[good_analysis(), w]))
    assert "_(user-provided: assumption)_" in r.markdown


# ---------------------------------------------------------------- CLI (full run)

def test_cli_full_run_args_and_exit_codes(monkeypatch, capsys, tmp_path):
    import agent as cli
    from app.agents import orchestrator

    a = cli.parse_args(["--company", "Acme", "--meeting-type", "partnership", "--depth", "quick", "--goal", "intro",
                        "--context", "they use X", "--context-type", "assumption", "--country", "Israel"])
    req = cli.build_request(a)
    assert (req.meeting_type, req.depth, req.meeting_goal, req.user_context_type, req.country) == (
        "partnership", "quick", "intro", "assumption", "Israel")
    with pytest.raises(SystemExit):
        cli.parse_args(["--company", "Acme", "--context", "x"])           # context needs a type

    class S:
        chat_model = "m"

        def required_gemini_key(self):
            return "k"

        def required_tavily_key(self):
            return "k"
    monkeypatch.setattr(cli, "get_settings", lambda: S())
    real = run_research(REQ, make_deps())
    monkeypatch.setattr(orchestrator, "run_research", lambda request, deps, on_stage=None: real)
    out_file = tmp_path / "b.md"
    assert cli.main(["--company", "Acme", "--no-save", "--out", str(out_file)]) == 0
    out = capsys.readouterr().out
    assert "# Deal-Prep Briefing: Acme" in out and "COMPLETED" in out and "Tavily credits" in out
    assert out_file.read_text(encoding="utf-8").startswith("# Deal-Prep Briefing")

    failed = run_research(REQ, make_deps(structured=[good_analysis(), RuntimeError("x"), RuntimeError("x")]))
    monkeypatch.setattr(orchestrator, "run_research", lambda request, deps, on_stage=None: failed)
    assert cli.main(["--company", "Acme", "--no-save"]) == 1

    def not_found(request, deps, on_stage=None):
        raise CompanyNotIdentified(Identification("Acme", None, False))
    monkeypatch.setattr(orchestrator, "run_research", not_found)
    assert cli.main(["--company", "Acme", "--no-save"]) == 3


def test_render_maps_raw_ids_in_text():
    from app.agents.contracts import SourceRecord
    from app.agents.render import Citations
    c = Citations([SourceRecord(id="I1", kind="internal", section="internal", title="a"),
                   SourceRecord(id="W3", kind="external", section="web", title="b")])
    assert c.text("We are a partner [I1].") == "We are a partner [1]."
    assert c.text("Deal (W3, W9) closed") == "Deal [2] closed"
    assert c.text("Q3 2026 revenue, Windows 11 W3C, cost (about $5)") == "Q3 2026 revenue, Windows 11 W3C, cost (about $5)"
    assert c.text("שותף [I1, W3].") == "שותף [1][2]."
    # a range of uncited IDs (Wix graph run 2026-11-11, missing-info note) disappears
    assert c.text("אין במסמכים הפנימיים [I5-I16] אזכור") == "אין במסמכים הפנימיים אזכור"
    assert c.text("see (I1–W3)") == "see [1][2]"


def test_render_drops_trailing_refs_already_appended():
    # elbit run 2026-11-24: "... ישראל [1][2]. [1][2]" on 34 lines
    from app.agents.render import _drop_repeated_refs
    assert _drop_repeated_refs("מטה בחיפה [1][2].", " [1][2]") == "מטה בחיפה."
    assert _drop_repeated_refs("HQ in Haifa [2]", " [1][2]") == "HQ in Haifa"
    # a trailing ref the claim doesn't list stays; refs inside the text stay
    assert _drop_repeated_refs("HQ in Haifa [3].", " [1][2]") == "HQ in Haifa [3]."
    assert _drop_repeated_refs("Won [1] and grew [2] fast.", " [1][2]") == "Won [1] and grew [2] fast."
    assert _drop_repeated_refs("No refs [1].", "") == "No refs [1]."


def test_join_reasons_makes_sentences_and_drops_repeats():
    # elbit run 2026-11-24: "... בפרט.; חסר מידע ..." with the same note twice
    from app.agents.analysis_writer import join_reasons
    assert join_reasons(["אין מסמכים.", "אין CRM", "אין מסמכים.", " ", "x;"]) == "אין מסמכים. אין CRM. x."
    assert join_reasons([]) == ""


def test_daily_quota_is_not_retried():
    quota = RuntimeError("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    deps = make_deps(structured=[quota, good_writer()], writer_fallback=False)
    r = run_research(REQ, deps)
    st = {s.stage: s for s in r.stages}
    assert st["strategic_analysis"].status == "failed" and st["strategic_analysis"].attempts == 1
    assert "daily free-tier quota" in st["strategic_analysis"].detail
    # the writer shares the analysis model: failed at once, no second 429 call
    assert st["briefing_writing"].status == "failed" and st["briefing_writing"].attempts == 0
    assert "daily free-tier quota" in st["briefing_writing"].detail
    assert st["quality_checks"].status == "skipped"
    assert len(deps.strong_llm.structured) == 1          # good_writer() was never requested
    assert r.status == "failed" and r.briefing is None
    assert "daily free-tier quota" in r.error


QUOTA = RuntimeError("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier")


def test_analysis_quota_goes_straight_to_fallback_writer():
    # analysis hit the strong model's daily quota: no second strong call, the small model writes a partial briefing
    deps = make_deps(structured=[QUOTA, good_writer()],
                     judge=[good_writer(), GenericVerdict(), GenericVerdict()])
    r = run_research(REQ, deps)
    st = {s.stage: s for s in r.stages}
    assert len(deps.strong_llm.structured) == 1          # good_writer() on the strong model never requested
    assert st["strategic_analysis"].status == "failed"
    assert st["briefing_writing"].status == "completed" and st["briefing_writing"].attempts == 1
    assert "fallback model fake-small (main model's daily quota reached)" in st["briefing_writing"].detail
    assert r.status == "partial" and r.briefing.meta.fallback_writer == "fake-small"
    assert "Written by the fallback model (fake-small)" in r.markdown and "daily quota" in r.markdown


def test_writer_quota_falls_back_once_without_retry():
    deps = make_deps(structured=[good_analysis(), QUOTA, good_writer()],
                     judge=[good_writer(), GenericVerdict(), GenericVerdict()])
    r = run_research(REQ, deps)
    st = {s.stage: s for s in r.stages}
    assert len(deps.strong_llm.structured) == 1          # one writer call on the strong model, no retry after 429
    assert r.status == "completed" and r.briefing.meta.fallback_writer == "fake-small"
    assert "daily quota reached" in st["briefing_writing"].detail
    # fallback fails too: failed, no briefing
    deps = make_deps(structured=[good_analysis(), QUOTA], judge=[QUOTA])
    r = run_research(REQ, deps)
    assert r.status == "failed" and r.briefing is None


def test_strong_model_has_no_hidden_sdk_retries(monkeypatch):
    """Every SDK attempt counts toward the 20/day quota (AI Studio showed 29 / 20 on 2026-11-11), so the strong
    model makes one request per call; retries only in Run.attempt(), after a wait past the 5 RPM window."""
    calls = []
    monkeypatch.setattr(orchestrator_mod, "build_chat_model",
                        lambda tier, **kw: calls.append((tier, kw)) or FakeLLM(model=f"fake-{tier}"))
    deps = Deps()
    deps.strong(), deps.small()
    assert calls == [("strong", {"max_retries": 1}), ("small", {"temperature": 0.0})]
    assert Deps().retry_wait_s >= 15


def test_research_model_tier_from_settings(monkeypatch):
    from dataclasses import replace

    from app.agents import orchestrator
    from app.core import config
    base = config.get_settings()
    strong, small = FakeLLM(model="s"), FakeLLM(model="l")
    for tier, expected in (("small", small), ("strong", strong)):
        monkeypatch.setattr(config, "get_settings", lambda t=tier: replace(base, research_model_tier=t))
        assert orchestrator.Deps(strong_llm=strong, small_llm=small).research() is expected
    monkeypatch.setenv("RESEARCH_MODEL_TIER", "huge")
    with pytest.raises(config.ConfigError):
        config._tier_env("RESEARCH_MODEL_TIER", "small")


# ---- inferred official domain + display name (2026-11-16) ----

from app.agents.orchestrator import display_name  # noqa: E402


@pytest.mark.parametrize("typed, written, shown", [
    ("elbit", "Elbit Systems", "Elbit Systems"),
    ("אלביט", "Elbit Systems", "Elbit Systems"),        # non-Latin input: trust the writer
    ("elbit", "Rafael Advanced Defense Systems", "elbit"),  # no shared word: keep what was typed
    ("elbit", None, "elbit"),
    ("elbit", "   ", "elbit"),
    ("elbit", "Elbit " + "x" * 120, "elbit"),
])
def test_display_name(typed, written, shown):
    assert display_name(typed, written) == shown


def test_inferred_domain_reaches_research_and_title_uses_official_name():
    def ident(company, domain=None):
        return Identification(company, "acme.com", True, via="web", web_sources=2, credits_used=1,
                              domain_inferred=True)
    writer = good_writer()
    writer.company_name = "Acme Corporation"
    req = ResearchRequest(company="acme", meeting_type="sales")
    store = MemoryRunStore()
    result = run_research(req, make_deps(structured=[good_analysis(), writer], identify_fn=ident, store=store))
    assert result.status == "completed"
    assert req.website == "acme.com"
    assert result.briefing.meta.website == "acme.com"
    assert result.markdown.startswith("# Meeting prep briefing: Acme Corporation") or \
        "Acme Corporation" in result.markdown.splitlines()[0]
    assert "official site: acme.com" in result.stages[0].detail
