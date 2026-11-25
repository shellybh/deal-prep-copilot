"""Briefing -> Markdown (code, not the model): one-page summary, detailed appendix, numbered sources.

Labels: facts carry no tag (only their citation); analysis, recommendations, user-provided
context and unverified claims are tagged. Low confidence and conflicts are shown, not hidden.
The Streamlit UI (Phase 5) reuses `render_markdown` and the label tables.
"""
from __future__ import annotations

import re

from app.agents.contracts import Briefing, Claim, InsightOut, SourceRecord

_RAW_ID = re.compile(r"\b([IW]\d+)\b")

SECTION_TITLES = {
    "en": {"company_overview": "Company Overview", "recent_developments": "Recent Developments",
           "financial_overview": "Financial Overview", "key_people": "Key People",
           "industry_overview": "Industry Overview", "competitor_intelligence": "Competitor Intelligence",
           "internal_intelligence": "Internal Intelligence", "business_opportunities": "Business Opportunities",
           "risks_challenges": "Risks & Challenges", "meeting_strategy": "Meeting Strategy",
           "recommended_questions": "Recommended Questions", "next_steps": "Suggested Next Steps"},
    "he": {"company_overview": "סקירת החברה", "recent_developments": "התפתחויות אחרונות",
           "financial_overview": "מידע פיננסי", "key_people": "אנשי מפתח", "industry_overview": "סקירת ענף",
           "competitor_intelligence": "מודיעין תחרותי", "internal_intelligence": "מידע פנימי רלוונטי",
           "business_opportunities": "הזדמנויות עסקיות", "risks_challenges": "סיכונים ואתגרים",
           "meeting_strategy": "אסטרטגיית הפגישה", "recommended_questions": "שאלות מומלצות",
           "next_steps": "צעדים מומלצים להמשך"},
}
TEXT = {
    "en": {"title": "Deal-Prep Briefing", "summary": "One-page summary", "appendix": "Detailed appendix",
           "sources": "Sources", "missing": "Missing information", "date": "Research date", "depth": "Depth",
           "meeting": "Meeting", "goal": "Goal", "languages": "Search languages", "website": "Website",
           "partial": "Partial briefing: some research stages failed ({stages}). Sections that depend on them "
                      "may be incomplete.",
           "fallback": "Written by the fallback model ({model}) because the main model was overloaded. "
                       "Wording may be less polished; facts and citations follow the same checks.",
           "ai_analysis": "AI analysis", "ai_recommendation": "recommendation", "unverified": "unverified",
           "user_provided": "user-provided", "low": "low confidence", "conflict": "sources disagree",
           "importance": "Importance", "why": "Why it matters", "how": "How to address", "rationale": "Rating",
           "date_unknown": "date unknown", "internal": "Internal", "external": "Web", "tier": "tier",
           "sales": "Sales Opportunity", "partnership": "Strategic Partnership",
           "quality": "Quality checks", "generic_removed": "generic statements removed"},
    "he": {"title": "תדריך הכנה לפגישה", "summary": "תקציר בעמוד אחד", "appendix": "נספח מפורט",
           "sources": "מקורות", "missing": "חסר מידע", "date": "תאריך המחקר", "depth": "עומק",
           "meeting": "פגישה", "goal": "מטרה", "languages": "שפות החיפוש", "website": "אתר",
           "partial": "תדריך חלקי: חלק משלבי המחקר נכשלו ({stages}). ייתכן שסעיפים שתלויים בהם חסרים.",
           "fallback": "נכתב במודל הגיבוי ({model}) כי המודל הראשי היה עמוס. הניסוח עשוי להיות פחות מלוטש; "
                       "העובדות והציטוטים עוברים את אותן בדיקות.",
           "ai_analysis": "ניתוח AI", "ai_recommendation": "המלצה", "unverified": "לא מאומת",
           "user_provided": "מידע מהמשתמש", "low": "ודאות נמוכה", "conflict": "המקורות סותרים",
           "importance": "חשיבות", "why": "למה זה חשוב", "how": "איך להתייחס", "rationale": "נימוק הדירוג",
           "date_unknown": "תאריך לא ידוע", "internal": "פנימי", "external": "רשת", "tier": "רמה",
           "sales": "הזדמנות מכירה", "partnership": "שותפות אסטרטגית",
           "quality": "בדיקות איכות", "generic_removed": "משפטים כלליים הוסרו"},
}
CONTEXT_TYPE = {"en": {"internal_information": "internal information", "assumption": "assumption",
                       "requires_verification": "requires verification"},
                "he": {"internal_information": "מידע פנימי", "assumption": "הנחה",
                       "requires_verification": "דורש אימות"}}


class Citations:
    """Source ID -> [n] in first-cited order (matches the Sources list)."""

    def __init__(self, sources: list[SourceRecord]):
        self.num = {s.id: n for n, s in enumerate(sources, 1)}

    def refs(self, ids: list[str]) -> str:
        nums = [self.num[i] for i in ids if i in self.num]
        return " " + "".join(f"[{n}]" for n in nums) if nums else ""

    def text(self, s: str) -> str:
        """Run IDs the model wrote inside the text ("... [I1]", "(W3, W4)") -> [n], unknown ones removed."""
        def sub(m):
            n = self.num.get(m.group(1))
            return f"\x00{n}\x01" if n else "\x02"
        out = _RAW_ID.sub(sub, s)
        # a bracket / parenthesis group holding only IDs becomes plain refs: "(W3, W4)" -> "[1][2]"
        # ... also a range "[I1-I16]"
        group = re.compile(r"[\[(]\s*((?:(?:\x00\d+\x01|\x02)[\s,;\-–]*)+)[\])]")
        out = group.sub(lambda m: re.sub(r"[\s,;\-–\x02]", "", m.group(1)), out)
        out = out.replace("\x02", "").replace("\x00", "[").replace("\x01", "]")
        out = re.sub(r"\s+([.,;:])", r"\1", re.sub(r" {2,}", " ", out))
        return out.strip()


def _tags(c: Claim, t: dict, ctx_type: str | None, lang: str) -> str:
    tags = []
    if c.info_type in ("ai_analysis", "ai_recommendation", "unverified"):
        tags.append(t[c.info_type])
    if c.info_type == "user_provided":
        tags.append(t["user_provided"] + (f": {CONTEXT_TYPE[lang][ctx_type]}" if ctx_type else ""))
    if c.confidence == "low" and c.info_type not in ("unverified", "user_provided"):
        tags.append(t["low"])
    if c.is_conflict:
        tags.append(t["conflict"])
    return f" _({', '.join(tags)})_" if tags else ""


_TRAILING_REFS = re.compile(r"\s*((?:\[\d+\])+)\s*([.!?]?)\s*$")


def _drop_repeated_refs(text: str, refs: str) -> str:
    """The model sometimes ends a claim with the IDs it also lists in source_ids ("... Haifa [W1][W2].").
    Those refs are appended anyway, so a trailing group already covered by them is removed (elbit run
    2026-11-24 showed "[1][2]. [1][2]"). Refs the claim doesn't list stay in the text."""
    m = _TRAILING_REFS.search(text)
    if not m or not refs:
        return text
    if set(re.findall(r"\d+", m.group(1))) <= set(re.findall(r"\d+", refs)):
        return text[:m.start()] + m.group(2)
    return text


def _claim_line(c: Claim, cites: Citations, t: dict, b: Briefing) -> str:
    conflict = cites.refs(c.conflicting_source_ids)
    tail = f" ↔{conflict}" if conflict else ""
    refs = cites.refs(c.source_ids)
    text = _drop_repeated_refs(cites.text(c.text), refs)
    return f"- {text}{refs}{tail}{_tags(c, t, b.meta.user_context_type, b.meta.language)}"


def _insight_lines(i: InsightOut, cites: Citations, t: dict) -> list[str]:
    low = f" _({t['low']})_" if i.confidence == "low" else ""
    x = cites.text
    out = [f"- **{x(i.title)}** ({t['importance']}: {i.importance}){cites.refs(i.evidence_source_ids)}{low}",
           f"  {x(i.description)}"]
    # a sub-line the generic judge blanked is left out
    for label, value in ((t["why"], i.why_it_matters), (t["how"], i.how_to_address),
                         (t["rationale"], i.importance_rationale)):
        if value.strip():
            out.append(f"  - {label}: {x(value)}")
    return out


def _source_line(n: int, s: SourceRecord, t: dict) -> str:
    if s.kind == "internal":
        return f"[{n}] {t['internal']}: {s.citation}"
    date = s.published_at.date().isoformat() if s.published_at else t["date_unknown"]
    return f"[{n}] {s.title}, {s.outlet}, {date}, {t['tier']} {s.tier}, {s.url}"


def render_markdown(b: Briefing) -> str:
    lang = b.meta.language
    t, titles = TEXT[lang], SECTION_TITLES[lang]
    cites = Citations(b.sources)
    m = b.meta
    out = [f"# {t['title']}: {m.company}", ""]
    info = [f"{t['date']}: {m.research_date.date().isoformat()}", f"{t['meeting']}: {t[m.meeting_type]}",
            f"{t['depth']}: {m.depth}"]
    if m.website:
        info.append(f"{t['website']}: {m.website}")
    if m.search_languages:
        info.append(f"{t['languages']}: {', '.join(m.search_languages)}")
    out.append(" · ".join(info))
    if m.meeting_goal:
        out.append(f"{t['goal']}: {m.meeting_goal}")
    if m.local_language_note:
        out.append(f"_{m.local_language_note}_")
    if m.is_partial:
        out += ["", f"> ⚠ {t['partial'].format(stages=', '.join(m.incomplete_stages))}"]
    if m.fallback_writer:
        out += ["", f"> ⚠ {t['fallback'].format(model=m.fallback_writer)}"]

    out += ["", f"## {t['summary']}", ""]
    out += [_claim_line(c, cites, t, b) for c in b.summary] or [f"- _{t['missing']}_"]

    out += ["", f"## {t['appendix']}"]
    for n, s in enumerate(b.sections, 1):
        out += ["", f"### {n}. {titles[s.key]}"]
        if s.status == "missing_info":
            out.append(f"- _{t['missing']}: {cites.text(s.missing_reason)}_" if s.missing_reason else f"- _{t['missing']}_")
        for c in s.claims:
            out.append(_claim_line(c, cites, t, b))
        for i in s.insights:
            out += _insight_lines(i, cites, t)

    missing = [titles[s.key] for s in b.sections if s.status == "missing_info"]
    if missing:
        out += ["", f"## {t['missing']}", "", "- " + "\n- ".join(missing)]

    out += ["", f"## {t['sources']}", ""]
    out += [_source_line(n, s, t) for n, s in enumerate(b.sources, 1)] or ["-"]
    q = b.quality
    if q.generic_dropped:
        out += ["", f"_{t['quality']}: {len(q.generic_dropped)} {t['generic_removed']}._"]
    return "\n".join(out) + "\n"
