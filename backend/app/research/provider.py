"""Search provider layer (Phase 3, D1 Tavily only, D37 credit budget).

Agents and the research service depend on the `SearchProvider` protocol only. `TavilyClient` is the one
implementation: `/search` + `/extract` over httpx, retries 429/5xx, clear errors, usage counters, an
optional per-run `CreditBudget` and an optional `ResponseCache` (eval/tests only, D37).

Credit rates (Tavily docs, verify on the pricing page): basic search 1, advanced search 2,
extract 1 per 5 successful URLs (basic) or 2 per 5 (advanced). Counts here are estimates.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

TAVILY_BASE_URL = "https://api.tavily.com"
MAX_ATTEMPTS = 3


class SearchError(RuntimeError):
    """A provider call failed. The message is safe to show (no secrets)."""


class FatalSearchError(SearchError):
    """Retrying or continuing won't help: bad API key or plan credit limit reached."""


class BudgetExceeded(SearchError):
    """The per-run credit cap (D37) would be exceeded by the next call. No request was sent."""


@dataclass
class Usage:
    """Per-client counters for cost tracking. `credits` are estimates from the published rates."""
    requests: int = 0      # HTTP responses received (incl. retried ones)
    credits: int = 0
    searches: int = 0
    extracts: int = 0
    cache_hits: int = 0

    def snapshot(self) -> dict:
        return dict(self.__dict__)


@dataclass
class CreditBudget:
    """Credit cap for one research run (D37). `limit=None` = unlimited."""
    limit: int | None = None
    used: int = 0

    @property
    def remaining(self) -> int | None:
        return None if self.limit is None else max(self.limit - self.used, 0)

    def check(self, cost: int) -> None:
        if self.limit is not None and self.used + cost > self.limit:
            raise BudgetExceeded(f"Tavily credit cap reached ({self.used}/{self.limit} used, next call costs {cost}).")

    def charge(self, cost: int) -> None:
        self.used += cost


class ResponseCache:
    """JSON files keyed by endpoint + request body. For eval and tests only (D37): re-runs cost nothing."""

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(path: str, body: dict) -> str:
        raw = json.dumps({"path": path, "body": body}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, path: str, body: dict) -> dict | None:
        f = self.dir / f"{self.key(path, body)}.json"
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, path: str, body: dict, data: dict) -> None:
        f = self.dir / f"{self.key(path, body)}.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def search_cost(search_depth: str) -> int:
    return 2 if search_depth == "advanced" else 1


def extract_cost(n_urls: int, extract_depth: str = "basic") -> int:
    return math.ceil(n_urls / 5) * (2 if extract_depth == "advanced" else 1) if n_urls else 0


class SearchProvider(Protocol):
    usage: Usage

    def search(self, query: str, *, topic: str = "general", days: int | None = None, max_results: int = 5,
               search_depth: str = "basic", include_domains: list[str] | None = None,
               country: str | None = None, budget: CreditBudget | None = None) -> list[dict]: ...

    def extract(self, urls: list[str], *, extract_depth: str = "basic",
                budget: CreditBudget | None = None) -> dict: ...


class TavilyClient:
    def __init__(self, api_key: str | None = None, http: httpx.Client | None = None, sleep=time.sleep,
                 cache: ResponseCache | None = None):
        self._api_key = api_key or get_settings().required_tavily_key()
        self._http = http or httpx.Client(timeout=30)
        self._sleep = sleep
        self.cache = cache
        self.usage = Usage()

    # ------------------------------------------------------------ public API
    def search(self, query: str, *, topic: str = "general", days: int | None = None, max_results: int = 5,
               search_depth: str = "basic", include_domains: list[str] | None = None,
               country: str | None = None, budget: CreditBudget | None = None) -> list[dict]:
        body: dict = {"query": query, "topic": topic, "max_results": max_results, "search_depth": search_depth}
        if days is not None:
            body["days"] = days
        if include_domains:
            body["include_domains"] = list(include_domains)
        if country and topic == "general":     # Tavily: `country` boosts one country, general topic only
            body["country"] = country
        data = self._post("/search", body, search_cost(search_depth), budget, "search")
        self.usage.searches += 1
        return data.get("results") or []

    def extract(self, urls: list[str], *, extract_depth: str = "basic",
                budget: CreditBudget | None = None) -> dict:
        """Returns {"results": [{"url", "raw_content"}], "failed_results": [{"url", "error"}]}."""
        urls = [u for u in urls if u]
        if not urls:
            return {"results": [], "failed_results": []}
        body = {"urls": urls, "extract_depth": extract_depth}
        data = self._post("/extract", body, extract_cost(len(urls), extract_depth), budget, "extract")
        self.usage.extracts += 1
        return {"results": data.get("results") or [], "failed_results": data.get("failed_results") or []}

    # ------------------------------------------------------------ transport
    def _post(self, path: str, body: dict, cost: int, budget: CreditBudget | None, what: str) -> dict:
        if self.cache:
            cached = self.cache.get(path, body)
            if cached is not None:
                self.usage.cache_hits += 1
                return cached
        if budget:
            budget.check(cost)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._http.post(TAVILY_BASE_URL + path, json=body, headers=headers)
            except httpx.HTTPError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise SearchError(f"Tavily request failed: {type(exc).__name__}") from exc
                self._sleep(2 ** attempt)
                continue
            self.usage.requests += 1
            if resp.status_code == 200:
                self.usage.credits += cost
                if budget:
                    budget.charge(cost)
                data = resp.json()
                if self.cache:
                    self.cache.put(path, body, data)
                return data
            if resp.status_code in (401, 403):
                raise FatalSearchError(f"Tavily rejected the API key ({resp.status_code}). Check TAVILY_API_KEY.")
            if resp.status_code == 432:
                raise FatalSearchError("Tavily plan credit limit reached (432).")
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < MAX_ATTEMPTS:
                log.warning("Tavily %s %s, retry %d/%d", what, resp.status_code, attempt, MAX_ATTEMPTS)
                self._sleep(2 ** attempt)
                continue
            raise SearchError(f"Tavily {what} failed ({resp.status_code}).")
        raise SearchError(f"Tavily {what} failed.")  # unreachable


def default_cache() -> ResponseCache | None:
    """Cache only when TAVILY_CACHE_DIR is set (eval runs). Normal runs always hit Tavily."""
    directory = get_settings().tavily_cache_dir
    return ResponseCache(directory) if directory else None
