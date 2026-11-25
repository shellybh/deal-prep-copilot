"""`Source` data contract for external results. Phase 4 adds the internal-document variant
and persists only the sources a briefing cites."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["official", "news", "government_regulatory", "financial", "professional_industry", "other"]
Window = Literal["last_48h", "in_range", "date_unknown"]

_HE = re.compile(r"[\u0590-\u05ff]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """'he' when Hebrew letters dominate, 'en' for Latin script, else 'other'. Cheap and deterministic."""
    he, latin = len(_HE.findall(text or "")), len(_LATIN.findall(text or ""))
    if he == 0 and latin == 0:
        return "other"
    return "he" if he >= latin * 0.5 else "en"


def source_id(normalized_url: str) -> str:
    return "web_" + hashlib.sha1(normalized_url.encode()).hexdigest()[:12]


class Source(BaseModel):
    id: str
    kind: Literal["external"] = "external"
    url: str
    normalized_url: str
    title: str
    outlet: str                                 # host without www.
    published_at: datetime | None = None        # None = unknown. Never invented.
    retrieved_at: datetime
    language: Literal["he", "en", "other"]
    source_type: SourceType
    tier: int = Field(ge=1, le=4)               # D21 step 1; preferred sources keep their real tier
    snippet: str = ""
    content: str | None = None                  # extracted page text (top results only), truncated
    window: Window | None = None                # news only: last 48 h / within the depth's range / undated
    is_preferred: bool = False                  # matched a preferred URL / category query (priority only)
    query_purposes: list[str] = Field(default_factory=list)
    query_languages: list[str] = Field(default_factory=list)
    also_reported_by: list[str] = Field(default_factory=list)   # same story at other outlets (URLs)
    provider_score: float | None = None

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
