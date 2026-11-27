"""UI logic that doesn't need Streamlit (Phase 5): stage lines, Markdown for st.markdown, RTL, error messages,
run footer, recent-briefing labels. Tested in `tests/test_ui.py`."""
from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import ValidationError

from app.agents.briefing import CompanyNotIdentified
from app.agents.contracts import StageStatus
from app.agents.llm import DAILY_QUOTA_MSG, is_daily_quota

log = logging.getLogger(__name__)

STAGE_LABELS = {
    "company_identification": "Company identification",
    "internal_research": "Internal knowledge base",
    "external_research": "Web research",
    "competitor_analysis": "Competitor research",
    "strategic_analysis": "Strategic analysis",
    "briefing_writing": "Briefing writing",
    "quality_checks": "Quality checks",
}
STATE_ICONS = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "failed": "❌", "skipped": "⏭️"}
MEETING_LABELS = {"sales": "Sales opportunity", "partnership": "Strategic partnership"}
DEPTH_LABELS = {"quick": "Quick", "standard": "Standard", "in_depth": "In-depth"}
LANGUAGE_LABELS = {"en": "English", "he": "Hebrew"}
CONTEXT_TYPE_LABELS = {"internal_information": "Internal information", "assumption": "Assumption",
                       "requires_verification": "Requires verification"}

QUOTA_TEXT = ("The daily model quota (Gemini free tier) is used up. It resets at midnight Pacific time "
              "(10:00 Israel time). Please try again then.")
NOT_IDENTIFIED_TEXT = ("Couldn't identify the company: no relevant sources were found for this name. "
                       "Add the company's website and run again.")
UNEXPECTED_TEXT = "Something went wrong while preparing the briefing. Please try again; the details are in the log."


@dataclass(frozen=True)
class Message:
    level: Literal["info", "warning", "error"]
    text: str


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


def stage_line(st: StageStatus) -> str:
    detail = f": {st.detail}" if st.detail and st.status != "pending" else ""
    return f"{STATE_ICONS.get(st.status, '•')} **{stage_label(st.stage)}**{detail}"


def stage_lines(stages) -> str:
    return "\n".join(f"- {stage_line(s)}" for s in stages)


def for_streamlit(md: str) -> str:
    """Hard line breaks for consecutive plain lines (header info lines, the numbered Sources list), which
    Markdown would otherwise join into one paragraph. List items, headings and quotes are left as they are."""
    lines = md.splitlines()
    out = []
    for n, line in enumerate(lines):
        nxt = lines[n + 1] if n + 1 < len(lines) else ""
        plain = line.strip() and not line.lstrip().startswith(("-", "*", "#", ">"))
        out.append(line + "  " if plain and nxt.strip() else line)
    return "\n".join(out)


def wrap_direction(md: str, language: str) -> str:
    """Hebrew briefings right-to-left. The blank lines let the Markdown inside the div still render."""
    if language != "he":
        return md
    return f'<div dir="rtl" style="text-align: right">\n\n{md}\n\n</div>'


def briefing_markdown(md: str, language: str) -> tuple[str, bool]:
    """(Markdown for st.markdown, needs unsafe_allow_html)."""
    body = for_streamlit(md)
    return wrap_direction(body, language), language == "he"


def quota_hit(result) -> bool:
    texts = [result.error or ""] + [s.detail or "" for s in result.stages]
    return any(DAILY_QUOTA_MSG in t for t in texts)


def error_message(exc: BaseException) -> Message:
    """An exception raised by run_research (or by building the request) -> what the UI shows."""
    if isinstance(exc, CompanyNotIdentified):
        return Message("warning", NOT_IDENTIFIED_TEXT)
    if isinstance(exc, ValidationError):
        fields = ", ".join(str(e["loc"][0]) for e in exc.errors() if e.get("loc")) or "the form"
        return Message("error", f"Please check: {fields}. {exc.errors()[0].get('msg', '')}".strip())
    if is_daily_quota(exc):
        return Message("error", QUOTA_TEXT)
    log.exception("briefing run failed in the UI", exc_info=exc)
    return Message("error", UNEXPECTED_TEXT)


def result_message(result) -> Message | None:
    """A finished run -> banner above the briefing (None for a clean completed run)."""
    if result.status == "failed":
        if quota_hit(result):
            return Message("error", QUOTA_TEXT)
        return Message("error", f"The briefing couldn't be produced: {result.error or 'unknown error'}")
    if result.status == "partial":
        failed = [stage_label(s.stage) for s in result.stages if s.status == "failed"]
        text = f"Partial briefing: some stages failed ({', '.join(failed) or 'unknown'}). " \
               "Sections that depend on them may be incomplete."
        if quota_hit(result):
            text += " " + QUOTA_TEXT
        return Message("warning", text)
    return None


def run_footer(result) -> str:
    t = result.usage.totals()
    parts = [f"{result.duration_s:.0f} s", f"{t['llm_calls']} LLM calls"]
    if result.findings:
        f = result.findings
        cited = len(result.briefing.sources) if result.briefing else 0
        parts.append(f"sources: {len(f.internal.source_ids)} internal, {len(f.web.source_ids)} web, "
                     f"{len(f.competitive.source_ids)} competitive ({cited} cited)")
    if result.briefing:
        q = result.briefing.quality
        parts.append(f"quality: {len(q.sections_missing)} sections missing, {len(q.generic_dropped)} generic "
                     f"removed, {q.low_confidence} low confidence")
    return " · ".join(parts)


def briefing_label(row: dict) -> str:
    """One line in the Recent briefings list."""
    created = row.get("created_at") or ""
    try:
        date = datetime.fromisoformat(str(created).replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        date = str(created)[:10]
    label = f"{row.get('company', '?')} · {str(row.get('language', '')).upper()} · " \
            f"{MEETING_LABELS.get(row.get('meeting_type'), row.get('meeting_type', ''))} · {date}"
    return label + (" · partial" if row.get("is_partial") else "")


def file_name(company: str, language: str) -> str:
    slug = "".join(c if c.isalnum() else "_" for c in company.lower()).strip("_") or "briefing"
    return f"{slug}_{language}_briefing.md"


# ---------- demo mode (Phase 6, D39 §2) ----------

BANNER_TEXT = ("**Demo scenario:** You're a sales rep at **NexaStream**, a fictional data-analytics vendor. "
               "The internal knowledge base (pricing, competitor battle cards, case studies, playbooks) belongs "
               "to NexaStream. Enter any real company, and the copilot combines public research about it with "
               "NexaStream's internal docs to prepare you for the meeting.")
CODE_HELP = "Live research runs need an access code (ask the author). The sample briefings are open to everyone."
CODE_WRONG_TEXT = "Wrong access code. The sample briefings in the sidebar are open to everyone."
LIVE_DISABLED_TEXT = ("Live research runs are turned off on this deployment. "
                      "The sample briefings in the sidebar are open to everyone.")
CAP_TEXT = ("Today's live-run limit is reached. It resets at 10:00 Israel time (midnight Pacific). "
            "The sample briefings in the sidebar are still available.")
COUNTER_DOWN_TEXT = "Live runs are unavailable right now (the usage counter can't be reached). Please try later."

Access = Literal["open", "ok", "wrong", "disabled"]


def check_access(entered: str | None, cfg) -> Access:
    """`cfg` = DemoSettings. open: demo mode off (local dev); disabled: demo mode on but no code configured
    (fail closed); ok / wrong: the entered code compared in constant time."""
    if not cfg.mode:
        return "open"
    if not cfg.access_code:
        return "disabled"
    given = (entered or "").strip()
    if given and hmac.compare_digest(given.encode(), cfg.access_code.encode()):
        return "ok"
    return "wrong"


def usage_line(used: int, cap: int) -> str:
    return f"Live runs today: {min(used, cap)} / {cap} (resets at 10:00 Israel time)"


def _date(value) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return str(value or "")[:10]


def first_sample(rows: list[dict]) -> dict:
    """The sample shown on a visitor's first screen: the newest English one (most visitors read English),
    else the newest. `rows` are newest first."""
    return next((r for r in rows if r.get("language") == "en"), rows[0])


def sample_caption(row: dict) -> str:
    return f"Sample briefing · generated {_date(row.get('created_at'))} · not updated live"


# ---------- glossary (sidebar): sales / finance terms the briefings use without explaining ----------

GLOSSARY: list[tuple[str, str]] = [
    ("ARR", "Annual Recurring Revenue: yearly revenue from subscriptions."),
    ("RPO", "Remaining Performance Obligations: contracted revenue not yet recognized."),
    ("FY / Q1-Q4 / H1", "Fiscal year, its quarters and its first half (a company's own calendar)."),
    ("CEO / CFO / CTO / CRO", "Chief Executive / Financial / Technology / Revenue Officer."),
    ("CPTO", "Chief Product and Technology Officer."),
    ("TCO", "Total Cost of Ownership: license plus setup, operation and staff costs over time."),
    ("ROI", "Return on Investment."),
    ("GTM", "Go-to-market: how a product is sold and marketed (channels, partners, sales motion)."),
    ("POC", "Proof of Concept: a short trial on the customer's own data before buying."),
    ("MAP", "Mutual Action Plan: steps and dates both sides agree on to close a deal."),
    ("SLA", "Service Level Agreement: guaranteed uptime and support response times."),
    ("Enterprise", "The large-customer tier: bigger contracts, longer sales cycles."),
    ("Churn", "Customers who stop paying or leave."),
    ("Win-back", "Selling again to a former customer."),
    ("Battle card", "Internal one-pager on a competitor: strengths, weaknesses, how to answer them."),
    ("SOC 2 / ISO 27001 / GDPR / HIPAA", "Security and privacy standards and regulations customers ask about."),
]


GLOSSARY_CSS = """
.st-key-glossary { background: #F7E6D6; border-radius: 0.5rem; }   /* same tint as the Demo scenario banner */
.st-key-glossary, .st-key-glossary * { color: #7C2D12 !important; }
.st-key-glossary summary > span { justify-content: center; }                 /* icon + label centered */
.st-key-glossary summary > span > div { flex: 0 0 auto !important; width: auto !important; }
.st-key-glossary li, .st-key-glossary li p { font-size: 0.875rem; line-height: 1.45; }
.st-key-glossary details, .st-key-glossary summary { background: transparent !important; border: none !important; }
"""


def glossary_markdown() -> str:
    return "\n".join(f"- **{term}**: {meaning}" for term, meaning in GLOSSARY)
