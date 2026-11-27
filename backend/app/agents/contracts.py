"""Phase 4-lite data contracts (D36, D38). Documented in ARCHITECTURE.md §6.0.4.

Two families:
- **LLM output schemas** (`*Draft`, `Analysis`, `WriterOutput`, `GenericVerdict`): what the models return through
  structured output. Kept small and flat (Gemini structured output), source IDs are the short run IDs (I1, W3).
- **Run contracts** (`ResearchRequest`, `SourceRecord`, `Claim`, `ResearchFindings`, `Briefing`, `StageStatus`):
  validated, persisted, rendered. Confidence and conflict flags are computed in code (D21), not by the model.

Built so the agents can be split later (D36 §5): `ResearchFindings` has one section per research role, and
`analyze()` / `write()` each have their own input and output contracts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.agents.identify import InvalidWebsite, parse_website

MeetingType = Literal["sales", "partnership"]
Depth = Literal["quick", "standard", "in_depth"]
Language = Literal["en", "he"]
ContextType = Literal["internal_information", "assumption", "requires_verification"]
Focus = Literal["competitors", "opportunities", "financial", "people", "news", "risks", "questions"]
InfoType = Literal["external_fact", "internal_document", "user_provided", "ai_analysis", "ai_recommendation",
                   "unverified"]
Confidence = Literal["high", "medium", "low"]
Importance = Literal["High", "Medium", "Low"]
StageName = Literal["company_identification", "internal_research", "external_research", "competitor_analysis",
                    "strategic_analysis", "briefing_writing", "quality_checks"]
StageState = Literal["pending", "in_progress", "completed", "failed", "skipped"]
RunStatus = Literal["running", "completed", "partial", "failed"]
SectionKey = Literal["company_overview", "recent_developments", "financial_overview", "key_people",
                     "industry_overview", "competitor_intelligence", "internal_intelligence",
                     "business_opportunities", "risks_challenges", "meeting_strategy", "recommended_questions",
                     "next_steps"]
FindingsSectionName = Literal["internal", "web", "competitive"]

STAGES: tuple[StageName, ...] = ("company_identification", "internal_research", "external_research",
                                 "competitor_analysis", "strategic_analysis", "briefing_writing", "quality_checks")
SECTION_KEYS: tuple[SectionKey, ...] = (
    "company_overview", "recent_developments", "financial_overview", "key_people", "industry_overview",
    "competitor_intelligence", "internal_intelligence", "business_opportunities", "risks_challenges",
    "meeting_strategy", "recommended_questions", "next_steps")
# Sections 8 and 9 come from analyze(); write() covers the rest.
ANALYSIS_SECTIONS: tuple[SectionKey, ...] = ("business_opportunities", "risks_challenges")
WRITER_SECTIONS: tuple[SectionKey, ...] = tuple(k for k in SECTION_KEYS if k not in ANALYSIS_SECTIONS)
FACT_TYPES = ("external_fact", "internal_document")
ANALYSIS_TYPES = ("ai_analysis", "ai_recommendation")
MAX_COMPARE = 3


# ---------- request ----------

class ResearchRequest(BaseModel):
    """Request form fields. `website` is stored as the bare domain (Phase 3.5)."""
    company: str = Field(min_length=1, max_length=200)
    meeting_type: MeetingType = "sales"
    meeting_goal: str = Field(default="", max_length=1000)
    country: str | None = Field(default=None, max_length=80)
    website: str | None = None
    focus: list[Focus] = Field(default_factory=list)
    depth: Depth = "standard"
    language: Language = "en"
    compare_with: list[str] = Field(default_factory=list)
    user_context: str | None = Field(default=None, max_length=4000)
    user_context_type: ContextType | None = None

    @field_validator("company", "meeting_goal", mode="before")
    @classmethod
    def _squash(cls, v):
        return " ".join(str(v).split()) if v is not None else v

    @field_validator("country", "user_context", mode="before")
    @classmethod
    def _blank_none(cls, v):
        return None if v is None or not str(v).strip() else str(v).strip()

    @field_validator("website", mode="before")
    @classmethod
    def _domain(cls, v):
        try:
            return parse_website(v)
        except InvalidWebsite as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("compare_with")
    @classmethod
    def _compare(cls, v):
        names = list(dict.fromkeys(" ".join(n.split()) for n in v if n and n.strip()))
        if len(names) > MAX_COMPARE:
            raise ValueError(f"at most {MAX_COMPARE} companies to compare")
        return names

    @model_validator(mode="after")
    def _context_needs_type(self):
        if self.user_context and not self.user_context_type:
            raise ValueError("user_context needs a classification (user_context_type)")
        if not self.user_context:
            self.user_context_type = None
        return self


# ---------- sources ----------

class SourceRecord(BaseModel):
    """One source in a run, internal or external, under a short run ID (I1, W1) the models cite."""
    id: str
    kind: Literal["internal", "external"]
    section: FindingsSectionName
    title: str
    # external
    url: str | None = None
    normalized_url: str | None = None
    outlet: str | None = None
    published_at: datetime | None = None
    tier: int | None = Field(default=None, ge=1, le=4)
    source_type: str | None = None
    window: str | None = None
    language: str | None = None
    also_reported_by: list[str] = Field(default_factory=list)
    purposes: list[str] = Field(default_factory=list)
    # internal
    citation: str | None = None
    file_name: str | None = None
    document_id: str | None = None
    version: int | None = None
    # text shown to the models (snippet, extracted page or chunk), truncated
    text: str = ""


class FindingsSection(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ResearchFindings(BaseModel):
    """Research Agent output (+ extra rounds). One section per research role (D36 §5)."""
    company: str
    internal: FindingsSection = Field(default_factory=FindingsSection)
    web: FindingsSection = Field(default_factory=FindingsSection)
    competitive: FindingsSection = Field(default_factory=FindingsSection)
    sources: dict[str, SourceRecord] = Field(default_factory=dict)
    notes: str = ""                       # the Research Agent's own short summary
    search_languages: list[str] = Field(default_factory=list)
    local_language_note: str | None = None
    rounds: int = 1
    credits_used: int = 0
    tool_calls: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def section(self, name: FindingsSectionName) -> FindingsSection:
        return getattr(self, name)


# ---------- LLM output schemas ----------

class ClaimDraft(BaseModel):
    text: str = Field(description="One short statement in the briefing language.")
    info_type: Literal["external_fact", "internal_document", "user_provided", "ai_analysis",
                       "ai_recommendation"]
    source_ids: list[str] = Field(default_factory=list, description="Run source IDs such as W3 or I1.")
    is_opinion: bool = Field(default=False, description="True if the source states an opinion, not a fact.")
    conflict_source_ids: list[str] = Field(
        default_factory=list, description="Sources that contradict this claim (both sides are shown).")


class Insight(BaseModel):
    """Opportunity or risk."""
    title: str
    description: str
    evidence_source_ids: list[str] = Field(default_factory=list)
    importance: Importance
    importance_rationale: str
    why_it_matters: str
    how_to_address: str


class Analysis(BaseModel):
    """analyze() output: Strategic Analyst role."""
    opportunities: list[Insight] = Field(default_factory=list)
    risks: list[Insight] = Field(default_factory=list)
    fit_assessment: list[ClaimDraft] = Field(default_factory=list)
    recommendations: list[ClaimDraft] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list, description="What the analysis could not cover and why.")


class SectionDraft(BaseModel):
    key: str = Field(description="One of the section keys given in the prompt.")
    claims: list[ClaimDraft] = Field(default_factory=list)
    missing_reason: str | None = Field(default=None, description="Why the section has no content, if empty.")


class WriterOutput(BaseModel):
    """write() output: Briefing Writer role."""
    summary: list[ClaimDraft] = Field(description="One-page summary: 5 to 8 of the most important points.")
    sections: list[SectionDraft]
    company_name: str | None = Field(
        default=None, description="The company's official name as it writes it on its own website or in "
                                  "its sources (e.g. 'Elbit Systems', 'monday.com'), for the briefing title.")


class GenericVerdict(BaseModel):
    """Quality-check judge (small model): which items are generic (D40)."""
    generic_ids: list[str] = Field(default_factory=list)
    reasons: dict[str, str] = Field(default_factory=dict)


# ---------- briefing ----------

class Claim(BaseModel):
    text: str
    info_type: InfoType
    source_ids: list[str] = Field(default_factory=list)
    confidence: Confidence | None = None   # None for user-provided context
    is_conflict: bool = False
    conflicting_source_ids: list[str] = Field(default_factory=list)


class InsightOut(Insight):
    confidence: Confidence = "low"


class BriefingSection(BaseModel):
    key: SectionKey
    status: Literal["complete", "missing_info"]
    missing_reason: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    insights: list[InsightOut] = Field(default_factory=list)   # sections 8 and 9 only

    @property
    def is_empty(self) -> bool:
        return not self.claims and not self.insights


class StageStatus(BaseModel):
    stage: StageName
    status: StageState = "pending"
    detail: str | None = None
    attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class QualityReport(BaseModel):
    """Automated checks + citation integrity + the generic-statement judge."""
    sections_missing: list[str] = Field(default_factory=list)
    unknown_source_ids_removed: int = 0
    uncited_analysis_dropped: int = 0
    facts_without_source: int = 0           # relabeled "unverified"
    info_type_relabeled: int = 0            # e.g. "external fact" that only cites internal docs
    generic_dropped: list[str] = Field(default_factory=list)
    generic_check_ran: bool = False
    conflicts: int = 0
    low_confidence: int = 0
    duplicate_sources_merged: int = 0
    notes: list[str] = Field(default_factory=list)


class BriefingMeta(BaseModel):
    company: str
    language: Language
    meeting_type: MeetingType
    meeting_goal: str = ""
    depth: Depth
    website: str | None = None
    research_date: datetime
    search_languages: list[str] = Field(default_factory=list)
    local_language_note: str | None = None
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)
    is_partial: bool = False
    incomplete_stages: list[str] = Field(default_factory=list)
    # set when the strong model was overloaded (503) or out of its daily quota and the small model wrote the briefing
    fallback_writer: str | None = None
    user_context: str | None = None
    user_context_type: ContextType | None = None


class Briefing(BaseModel):
    meta: BriefingMeta
    summary: list[Claim] = Field(default_factory=list)
    sections: list[BriefingSection]
    sources: list[SourceRecord] = Field(default_factory=list)   # cited sources only
    quality: QualityReport = Field(default_factory=QualityReport)

    @model_validator(mode="after")
    def _all_sections(self):
        keys = [s.key for s in self.sections]
        if sorted(keys) != sorted(SECTION_KEYS):
            raise ValueError("a briefing has each of the 12 sections exactly once")
        self.sections.sort(key=lambda s: SECTION_KEYS.index(s.key))
        return self

    def section(self, key: SectionKey) -> BriefingSection:
        return next(s for s in self.sections if s.key == key)

    def all_claims(self) -> list[Claim]:
        return self.summary + [c for s in self.sections for c in s.claims]
