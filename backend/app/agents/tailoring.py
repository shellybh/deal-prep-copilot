"""Meeting-type tailoring (D40 §2): config in code, injected into the analysis and writing prompts.

One prompt per role; the meeting type only changes these values. Adding a meeting type = one entry here.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.contracts import MeetingType


@dataclass(frozen=True)
class MeetingProfile:
    label: str
    seller_role: str
    emphasis: tuple[str, ...]
    opportunity_lens: str
    risk_lens: str
    question_focus: str


MEETING_TYPES: dict[str, MeetingProfile] = {
    "sales": MeetingProfile(
        label="Sales Opportunity",
        seller_role="We want to sell our products to this company.",
        emphasis=("the customer's likely needs, backed by sources", "sales opportunities",
                  "which of our products and solutions fit, from our internal documents",
                  "competitors (theirs and ours) and how we compare", "barriers and risks to the deal"),
        opportunity_lens="where our products answer a sourced need, event or initiative of this company",
        risk_lens="what could block or slow the deal: incumbent competitors, budget signals, timing, fit gaps",
        question_focus="discovery questions about their needs, current tools, decision process and timeline"),
    "partnership": MeetingProfile(
        label="Strategic Partnership",
        seller_role="We are exploring a strategic partnership with this company.",
        emphasis=("strategic fit", "synergies between their products / markets and ours",
                  "concrete ways to work together", "mutual value: what each side gains",
                  "partnership risks and opportunities"),
        opportunity_lens="joint offerings, shared customers or markets, integrations, co-selling",
        risk_lens="overlap or competition with us, conflicting partnerships, strategic or financial instability",
        question_focus="questions about their partner strategy, priorities, resources and success criteria"),
}


def profile(meeting_type: MeetingType) -> MeetingProfile:
    return MEETING_TYPES[meeting_type]


def prompt_block(meeting_type: MeetingType, goal: str) -> str:
    p = profile(meeting_type)
    lines = [f"Meeting type: {p.label}. {p.seller_role}",
             f"Meeting goal (from the user): {goal or 'not given'}",
             "Emphasize: " + "; ".join(p.emphasis) + ".",
             f"Opportunities = {p.opportunity_lens}.",
             f"Risks = {p.risk_lens}.",
             f"Recommended questions = {p.question_focus}."]
    return "\n".join(lines)
