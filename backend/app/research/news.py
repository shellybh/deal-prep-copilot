"""Live news search (Phase 2B, D1 Tavily only).

`TavilyProvider` = the Phase 3 `TavilyClient` (app/research/provider.py) plus `search_news`. `search_news`
applies our own date rules on top, because Tavily's `days` filter is not strict (found 2026-11-06):
- items dated within 48 h → window "last_48h"
- if there are none, a second search over 30 days; items dated within 30 days → "last_30_days" (older, not breaking)
- items without a parseable date are kept as "date_unknown" and never treated as recent
- items older than 30 days are dropped
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.parse import urlparse

from app.research.dates import parse_date  # noqa: F401  (re-exported: 2B callers and tests import it here)
from app.research.provider import SearchError, TavilyClient, Usage

log = logging.getLogger(__name__)

RECENT = timedelta(hours=48)
FALLBACK_DAYS = 30

WINDOW_48H = "last_48h"
WINDOW_30D = "last_30_days"
WINDOW_UNKNOWN = "date_unknown"
_WINDOW_ORDER = {WINDOW_48H: 0, WINDOW_30D: 1, WINDOW_UNKNOWN: 2}

# Phase 3 generalized the 2B adapter (app/research/provider.py). Old names kept for 2B callers.
NewsSearchError = SearchError
NewsUsage = Usage


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    outlet: str
    published_at: str | None   # ISO 8601 UTC, or None when the source gives no usable date
    snippet: str
    window: str                # last_48h | last_30_days | date_unknown

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NewsResult:
    company: str
    items: list[NewsItem] = field(default_factory=list)
    searched_windows: list[str] = field(default_factory=list)  # e.g. ["48h"] or ["48h", "30d"]

    @property
    def used_fallback(self) -> bool:
        return "30d" in self.searched_windows

    def to_dict(self) -> dict:
        return {"company": self.company, "searched_windows": self.searched_windows,
                "used_fallback": self.used_fallback, "items": [i.to_dict() for i in self.items]}


class NewsProvider(Protocol):
    def search_news(self, query: str, days: int, max_results: int) -> list[dict]: ...


class TavilyProvider(TavilyClient):
    """2B news adapter = the Phase 3 client plus the old `search_news(query, days, max_results)` call."""

    def search_news(self, query: str, days: int, max_results: int) -> list[dict]:
        return self.search(query, topic="news", days=days, max_results=max_results)


def outlet_from_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


def classify(published: datetime | None, now: datetime) -> str | None:
    """Window for an item, or None to drop it (older than 30 days)."""
    if published is None or published > now + timedelta(days=1):  # future dates are not trustworthy
        return WINDOW_UNKNOWN
    age = now - published
    if age <= RECENT:
        return WINDOW_48H
    if age <= timedelta(days=FALLBACK_DAYS):
        return WINDOW_30D
    return None


def _to_items(results: list[dict], now: datetime) -> list[tuple[NewsItem, datetime | None]]:
    out = []
    for r in results:
        url = (r.get("url") or "").strip()
        if not url:
            continue
        published = parse_date(r.get("published_date"))
        window = classify(published, now)
        if window is None:
            continue
        if window == WINDOW_UNKNOWN:
            published = None
        snippet = " ".join((r.get("content") or "").split())[:500]
        out.append((NewsItem(title=(r.get("title") or "").strip(), url=url, outlet=outlet_from_url(url),
                             published_at=published.isoformat() if published else None,
                             snippet=snippet, window=window), published))
    return out


def search_news(company: str, provider: NewsProvider, max_results: int = 5,
                now: datetime | None = None) -> NewsResult:
    company = company.strip()
    if not company:
        raise ValueError("company name is empty")
    now = now or datetime.now(timezone.utc)
    result = NewsResult(company=company)
    fetch = max(max_results * 2, 10)  # ask for more: some items get dropped by our date filter

    found = _to_items(provider.search_news(company, days=2, max_results=fetch), now)
    result.searched_windows.append("48h")
    if not any(i.window == WINDOW_48H for i, _ in found):
        found += _to_items(provider.search_news(company, days=FALLBACK_DAYS, max_results=fetch), now)
        result.searched_windows.append("30d")

    seen: set[str] = set()
    unique = []
    for item, published in found:
        key = item.url.rstrip("/").lower()
        if key not in seen:
            seen.add(key)
            unique.append((item, published))
    # newest first within each window: last_48h, then last_30_days, then date_unknown
    unique.sort(key=lambda p: (_WINDOW_ORDER[p[0].window], -(p[1].timestamp() if p[1] else 0)))
    result.items = [i for i, _ in unique[:max_results]]
    return result
