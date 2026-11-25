"""Analysis & Writing Agent (D36): `analyze()` (Strategic Analyst) then `write()` (Briefing Writer).

Structured output, no tools. Each function has its own prompt file and contract, so either can become its own
graph node later without changes. `assemble()` turns the drafts into a validated `Briefing` (code, no LLM):
unknown source IDs removed, confidence computed (D21), empty sections marked missing, cited sources only.
"""
from __future__ import annotations

import json
from datetime import datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.confidence import confidence_for, to_claim
from app.agents.contracts import (ANALYSIS_SECTIONS, SECTION_KEYS, WRITER_SECTIONS, Analysis, Briefing,
                                  BriefingMeta, BriefingSection, InsightOut, ResearchRequest, WriterOutput)
from app.agents.llm import UsageLog, structured_call
from app.agents.registry import SourceRegistry
from app.agents.role_prompts import analysis as PA
from app.agents.role_prompts import writer as PW
from app.agents.tailoring import prompt_block

LANGUAGE_NAMES = {"en": "English", "he": "Hebrew"}
CONTEXT_LABELS = {"internal_information": "internal information (from the user, not verified by research)",
                  "assumption": "an assumption of the user", "requires_verification": "requires verification"}
SECTION_HINTS = {
    "company_overview": "what the company does, products, customers, size, HQ",
    "recent_developments": "news and developments, newest first, with dates",
    "financial_overview": "revenue, profitability, results, funding, valuation - each with period and source",
    "key_people": "management and founders: name, role, professional background",
    "industry_overview": "sourced points about the company's industry",
    "competitor_intelligence": "direct, indirect and emerging competitors: what they offer, their own sourced advantages (not ours)",
    "internal_intelligence": "what our internal documents say that applies to this company",
    "meeting_strategy": "goals for the meeting, topics to raise, what we should emphasize, what to handle carefully",
    "recommended_questions": "questions tailored to this company and the meeting goal",
    "next_steps": "possible next steps after the meeting",
}


def _website_line(r: ResearchRequest) -> str:
    return f" (website: {r.website})" if r.website else ""


def _context_line(r: ResearchRequest) -> str:
    if not r.user_context:
        return ""
    return f"User context ({CONTEXT_LABELS[r.user_context_type]}): {r.user_context}\n"


def _gaps(reg: SourceRegistry) -> str:
    f = reg.findings
    gaps = f.internal.gaps + f.web.gaps + f.competitive.gaps
    if f.local_language_note:
        gaps.append(f.local_language_note)
    return "; ".join(gaps) or "none"


def _sources_json(reg: SourceRegistry) -> str:
    return json.dumps(reg.for_prompt(), ensure_ascii=False)


def analyze(reg: SourceRegistry, request: ResearchRequest, llm: BaseChatModel, usage: UsageLog) -> Analysis:
    system = PA.SYSTEM.format(meeting_block=prompt_block(request.meeting_type, request.meeting_goal),
                              language=LANGUAGE_NAMES[request.language], company=request.company)
    user = PA.USER.format(company=request.company, website_line=_website_line(request),
                          notes=reg.findings.notes or "(none)", gaps=_gaps(reg),
                          user_context=_context_line(request), sources=_sources_json(reg))
    return structured_call(llm, Analysis, [SystemMessage(system), HumanMessage(user)], agent="analysis", usage=usage)


def write(reg: SourceRegistry, request: ResearchRequest, analysis: Analysis | None, llm: BaseChatModel,
          usage: UsageLog, research_date: datetime) -> WriterOutput:
    section_list = "\n".join(f"- {k}: {SECTION_HINTS[k]}" for k in WRITER_SECTIONS)
    system = PW.SYSTEM.format(company=request.company, language=LANGUAGE_NAMES[request.language],
                              meeting_block=prompt_block(request.meeting_type, request.meeting_goal),
                              section_list=section_list)
    analysis_json = analysis.model_dump_json() if analysis else '{"note": "the analysis step failed; no analysis"}'
    user = PW.USER.format(company=request.company, website_line=_website_line(request),
                          research_date=research_date.date().isoformat(), gaps=_gaps(reg),
                          user_context=_context_line(request), analysis=analysis_json, sources=_sources_json(reg))
    return structured_call(llm, WriterOutput, [SystemMessage(system), HumanMessage(user)], agent="writer",
                           usage=usage)


def _insights(items, reg: SourceRegistry, stats: dict) -> list[InsightOut]:
    out = []
    for i in items:
        ids = [s for s in dict.fromkeys(i.evidence_source_ids) if reg.get(s)]
        stats["unknown_ids"] = stats.get("unknown_ids", 0) + len(set(i.evidence_source_ids) - set(ids))
        out.append(InsightOut(**{**i.model_dump(), "evidence_source_ids": ids},
                              confidence=confidence_for(ids, reg)))
    return out


def join_reasons(items: list[str]) -> str:
    """Analysis `missing` notes -> one readable reason: each a sentence, exact repeats dropped
    (elbit run 2026-11-24 showed "... בפרט.; חסר מידע ...")."""
    out: list[str] = []
    for x in items:
        x = x.strip().rstrip(";").strip()
        if not x:
            continue
        if x[-1] not in ".!?":
            x += "."
        if x not in out:
            out.append(x)
    return " ".join(out)


def assemble(reg: SourceRegistry, request: ResearchRequest, analysis: Analysis | None,
             written: WriterOutput | None, meta: BriefingMeta) -> Briefing:
    drafts = {}
    for sd in (written.sections if written else []):
        if sd.key in WRITER_SECTIONS and sd.key not in drafts:
            drafts[sd.key] = sd
    stats: dict = {}
    sections = []
    for key in SECTION_KEYS:
        if key in ANALYSIS_SECTIONS:
            items = (analysis.opportunities if key == "business_opportunities" else analysis.risks) if analysis else []
            insights = _insights(items, reg, stats)
            reason = None if insights else ("the analysis step failed" if analysis is None
                                            else join_reasons(analysis.missing) or "nothing specific and sourced found")
            sections.append(BriefingSection(key=key, status="complete" if insights else "missing_info",
                                            missing_reason=reason, insights=insights))
            continue
        sd = drafts.get(key)
        claims = [to_claim(c, reg, stats) for c in (sd.claims if sd else []) if c.text.strip()]
        reason = None if claims else ((sd.missing_reason if sd and sd.missing_reason else None)
                                      or ("the writing step failed" if written is None else "no information found"))
        sections.append(BriefingSection(key=key, status="complete" if claims else "missing_info",
                                        missing_reason=reason, claims=claims))
    summary = [to_claim(c, reg, stats) for c in (written.summary if written else []) if c.text.strip()]
    b = Briefing(meta=meta, summary=summary, sections=sections)
    b.quality.unknown_source_ids_removed = stats.get("unknown_ids", 0)
    return b


def cited_sources(briefing: Briefing, reg: SourceRegistry) -> list:
    """Only the sources the briefing cites are kept and persisted, in first-cited order."""
    ids: list[str] = []
    for c in briefing.all_claims():
        ids += c.source_ids + c.conflicting_source_ids
    for s in briefing.sections:
        for i in s.insights:
            ids += i.evidence_source_ids
    return [reg.get(i) for i in dict.fromkeys(ids) if reg.get(i)]
