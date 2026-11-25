"""Claim confidence and conflicts (D21 steps 3, 5, 6). Deterministic: the model never sets confidence.

- high   = cites a Tier 1 source (official / regulator / exchange), or >= 2 independent Tier 2-3 outlets
           (corroboration counts distinct outlets, including same-story reports `also_reported_by`)
- medium = one Tier 2-3 outlet
- low    = only Tier 4 sources, an opinion, or no valid source
Internal documents are our own records: a claim backed by them is high for what it says about our side.
An analysis / recommendation gets the confidence of the facts it rests on.
User-provided context has no confidence (it is labeled by its own classification).
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.agents.contracts import Claim, ClaimDraft, Confidence
from app.agents.registry import SourceRegistry


def _outlet(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def confidence_for(source_ids: list[str], registry: SourceRegistry, is_opinion: bool = False) -> Confidence:
    recs = [r for r in (registry.get(i) for i in source_ids) if r is not None]
    if not recs or is_opinion:
        return "low"
    if any(r.kind == "internal" for r in recs):
        return "high"
    if any(r.tier == 1 for r in recs):
        return "high"
    outlets = set()
    for r in recs:
        if r.tier in (2, 3):
            outlets.add(r.outlet)
            outlets |= {_outlet(u) for u in r.also_reported_by}
    outlets.discard("")
    if len(outlets) >= 2:
        return "high"
    if outlets:
        return "medium"
    return "low"


def to_claim(draft: ClaimDraft, registry: SourceRegistry, stats: dict | None = None) -> Claim:
    """Draft -> Claim: unknown IDs removed, confidence + conflict computed. Further checks in quality.py."""
    ids = [i for i in dict.fromkeys(draft.source_ids) if registry.get(i)]
    if stats is not None:
        stats["unknown_ids"] = stats.get("unknown_ids", 0) + len(set(draft.source_ids) - set(ids))
    conflicts = [i for i in dict.fromkeys(draft.conflict_source_ids) if registry.get(i) and i not in ids]
    conf = None if draft.info_type == "user_provided" else confidence_for(ids, registry, draft.is_opinion)
    return Claim(text=draft.text.strip(), info_type=draft.info_type, source_ids=ids, confidence=conf,
                 is_conflict=bool(conflicts), conflicting_source_ids=conflicts)
