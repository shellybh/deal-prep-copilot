"""Orchestrator completeness check and extra research rounds (D17, D36 §3, D40 §1). Code only, no LLM.

Criteria (each failed one is a gap):
- internal:    the internal KB was searched at least once
- profile:     >= 1 relevant web source from a profile query (or an official page)
- news:        the news queries ran (finding no news is a valid result, not a gap to re-search)
- financial:   >= 1 source from a financial query
- people:      >= 1 source from a people query
- competitors: >= N competitive sources, N = 2 / 3 / 5 for Quick / Standard / In-depth (D17 "competitors profiled")

An extra round only runs searches that can change the answer: purposes that were never queried (the agent
skipped a tool or the query cap cut them) and the internal search if it never ran. A purpose that was queried
and returned nothing stays a gap: the same query would return the same thing. The number of rounds comes from
the depth (D17: 0 / 1 / 2) and the per-run credit cap (D37) still applies.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.research_agent import NEWS_PURPOSES, ResearchContext

MIN_COMPETITIVE = {"quick": 2, "standard": 3, "in_depth": 5}
WEB_CRITERIA = ("profile", "financial", "people")


@dataclass
class Completeness:
    gaps: dict[str, str] = field(default_factory=dict)        # criterion -> human-readable reason
    actionable: set[str] = field(default_factory=set)         # what an extra round can still search

    @property
    def complete(self) -> bool:
        return not self.gaps


def check(ctx: ResearchContext) -> Completeness:
    reg, depth = ctx.registry, ctx.request.depth
    out = Completeness()
    if not reg.internal_queries:
        out.gaps["internal"] = "the internal knowledge base was not searched"
        out.actionable.add("internal")
    for purpose in WEB_CRITERIA:
        found = reg.with_purpose(purpose)
        if purpose == "profile":
            found = found or [r for r in reg.sources.values() if r.source_type == "official"]
        if not found:
            queried = purpose in reg.queried_purposes
            out.gaps[purpose] = (f"no relevant {purpose} sources found" if queried
                                 else f"{purpose} was not searched")
            if not queried:
                out.actionable.add(purpose)
    if not (NEWS_PURPOSES & reg.queried_purposes):
        out.gaps["news"] = "news was not searched"
        out.actionable.add("news")
    need = MIN_COMPETITIVE.get(depth, 3)
    have = len(reg.findings.competitive.source_ids)
    if have < need:
        queried = "competitors" in reg.queried_purposes
        out.gaps["competitors"] = f"{have} of {need} competitive sources" + ("" if queried else " (not searched)")
        if not queried:
            out.actionable.add("competitors")
    if ctx.web_disabled or reg.budget_exhausted:
        out.actionable &= {"internal"}               # no more web searches possible
    return out


def extra_round(ctx: ResearchContext, gaps: Completeness) -> list[str]:
    """Runs the actionable searches. Returns what was searched (for the stage detail)."""
    done = []
    if "internal" in gaps.actionable:
        ctx.internal_search(ctx.request.company)
        done.append("internal")
    web = gaps.actionable - {"internal"}
    if web:
        purposes = set()
        for p in web:
            purposes |= NEWS_PURPOSES if p == "news" else {p}
        remaining = max(ctx.cfg.max_queries - len(ctx.registry.queried_purposes), 1)
        ctx.web_search(purposes, limit=remaining)
        done += sorted(web)
    ctx.registry.findings.rounds += 1
    ctx.registry.findings.credits_used = ctx.budget.used
    return done


def record_gaps(ctx: ResearchContext, gaps: Completeness) -> None:
    """Write the final gaps into the findings sections (input for the writer's Missing information)."""
    f = ctx.registry.findings
    for key, reason in gaps.gaps.items():
        section = f.internal if key == "internal" else f.competitive if key == "competitors" else f.web
        if reason not in section.gaps:
            section.gaps.append(f"{key}: {reason}")
