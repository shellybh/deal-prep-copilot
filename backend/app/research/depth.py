"""Research depth parameters (D17 as amended by D37).

Lives in code until Phase 4 adds `system_settings_versions`; then these become the seed row and
admins edit them within ranges. Nothing else in the research layer hard-codes these numbers.

- `max_queries` is a cap for the whole run, extra research rounds included (D37).
- `initial_queries` is what the first round may use; the rest is kept for the Orchestrator's extra rounds.
- `credit_cap` stops searching when reached; the run continues with what it has (D37).
- `max_per_outlet` / `min_hebrew_sources`: selection rules for the kept sources (diversity).
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class DepthConfig:
    name: str
    max_queries: int
    initial_queries: int
    search_depth: str          # "basic" for all levels in the MVP (D37)
    news_days: int             # news time range; "last 48 h" is always searched on top
    results_per_query: int
    max_sources: int           # kept after dedup + ranking
    extract_top: int           # full-page extraction for the top-ranked results
    credit_cap: int
    max_extra_rounds: int
    max_per_outlet: int = 3      # source diversity: the company's own site can't fill the list
    min_hebrew_sources: int = 2  # keep Hebrew results that were found (D37), if any


DEPTHS: dict[str, DepthConfig] = {
    "quick": DepthConfig("quick", max_queries=6, initial_queries=6, search_depth="basic", news_days=30,
                         results_per_query=5, max_sources=10, extract_top=0, credit_cap=8, max_extra_rounds=0),
    "standard": DepthConfig("standard", max_queries=12, initial_queries=8, search_depth="basic", news_days=90,
                            results_per_query=5, max_sources=20, extract_top=3, credit_cap=20, max_extra_rounds=1),
    "in_depth": DepthConfig("in_depth", max_queries=20, initial_queries=12, search_depth="basic", news_days=365,
                            results_per_query=7, max_sources=35, extract_top=8, credit_cap=40, max_extra_rounds=2),
}

DEFAULT_DEPTH = "standard"
_ALIASES = {"in-depth": "in_depth", "indepth": "in_depth", "deep": "in_depth"}


def get_depth(name: str | None = None, **overrides) -> DepthConfig:
    key = (name or DEFAULT_DEPTH).strip().lower()
    key = _ALIASES.get(key, key)
    if key not in DEPTHS:
        raise ValueError(f"Unknown research depth {name!r}. Use one of: {', '.join(DEPTHS)}")
    cfg = DEPTHS[key]
    return replace(cfg, **overrides) if overrides else cfg
