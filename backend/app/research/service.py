"""External research service (Phase 3). Agents call this through `app/tools.py`.

One call: build queries (D37 languages, depth caps) → search → `Source` records (tier, language, dates
never invented) → URL + near-duplicate dedup across languages → rank → optional page extraction.

Errors are surfaced, not hidden: a bad key / plan limit raises at once; other failed queries are listed
in `errors`, and if every query fails the call raises. The per-run credit cap ends searching early and
is reported (`budget_exhausted`), the run continues with what it has.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.research.dates import trusted_date
from app.research.depth import DepthConfig, get_depth
from app.research.languages import LanguagePlan
from app.research.provider import BudgetExceeded, CreditBudget, FatalSearchError, SearchError, SearchProvider
from app.research.queries import QuerySpec, build_queries
from app.research.sources import Source, detect_language, source_id
from app.research.tiering import classify_source
from app.research.urls import domain_of, normalize_url, same_story

log = logging.getLogger(__name__)

RECENT = timedelta(hours=48)
SNIPPET_CHARS = 500
CONTENT_CHARS = 6000
_CORP_SUFFIXES = {"inc", "ltd", "llc", "plc", "corp", "corporation", "co", "company", "group", "gmbh", "sa", "ag",
                  "בע", "מ", "בעמ", "technologies",   # בע"מ is split by the tokenizer
                  "technology", "software", "holdings"}
_TOKEN = re.compile(r"[\w\u0590-\u05ff]+", re.UNICODE)
_WINDOW_RANK = {"last_48h": 0, None: 1, "in_range": 1, "date_unknown": 2}


@dataclass
class ExternalResearchResult:
    company: str
    depth: str
    sources: list[Source] = field(default_factory=list)
    search_languages: list[str] = field(default_factory=list)
    local_language: str | None = None
    local_language_searched: bool = True
    queries_run: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    budget_exhausted: bool = False
    credits_used: int = 0
    usage: dict = field(default_factory=dict)

    @property
    def recent_news(self) -> list[Source]:
        return [s for s in self.sources if s.window == "last_48h"]

    def to_dict(self) -> dict:
        return {
            "company": self.company, "depth": self.depth, "search_languages": self.search_languages,
            "local_language": self.local_language, "local_language_searched": self.local_language_searched,
            "budget_exhausted": self.budget_exhausted, "credits_used": self.credits_used,
            "errors": self.errors, "notes": self.notes, "queries_run": self.queries_run,
            "recent_news_ids": [s.id for s in self.recent_news],
            "sources": [s.to_dict() for s in self.sources],
        }


def company_terms(company: str, aliases=()) -> list[str]:
    """Words that must appear for a result to count as being about the company: the name without its
    TLD / corporate suffix ('monday.com' → 'monday', 'Acme Ltd' → 'acme'), plus any aliases
    (e.g. a Hebrew name from company identification, Phase 4)."""
    terms = []
    for name in [company, *aliases]:
        name = (name or "").strip().lower()
        if not name:
            continue
        name = re.sub(r"\.(com|io|ai|co|net|org|co\.il)$", "", name)
        words = [w for w in _TOKEN.findall(name) if w not in _CORP_SUFFIXES]
        if words:
            terms.append(" ".join(words))
    return list(dict.fromkeys(terms))


def is_relevant(text: str, terms: list[str]) -> bool:
    low = " ".join(_TOKEN.findall((text or "").lower()))
    return any(re.search(rf"(?<![\w\u0590-\u05ff]){re.escape(t)}(?![\w\u0590-\u05ff])", low) for t in terms)


def mentions_company(s: Source, terms: list[str], full_names: list[str]) -> bool:
    """Short name in the title or URL, or the full name in the snippet. ('monday' alone in a snippet is
    usually the weekday: "...said on Monday".)"""
    if is_relevant(f"{s.title} {s.url}", terms):
        return True
    return is_relevant(s.snippet, [" ".join(_TOKEN.findall(n)) for n in full_names])


def _site(s: Source, company_domain: str | None) -> str:
    """Outlet key for the per-outlet cap: all of the company's own subdomains count as one site."""
    if company_domain and (s.outlet == company_domain or s.outlet.endswith("." + company_domain)):
        return company_domain
    return s.outlet


def _quality(s: Source) -> tuple:
    """Which copy of a duplicate to keep: better tier, has a date, longer snippet."""
    return (s.tier, s.published_at is None, -len(s.snippet))


def _rank(s: Source) -> tuple:
    """Final order: preferred first (priority only), then last-48h news, tier, newest, score."""
    ts = s.published_at.timestamp() if s.published_at else float("-inf")
    return (not s.is_preferred, _WINDOW_RANK.get(s.window, 1), s.tier, -ts, -(s.provider_score or 0))


def dedupe(sources: list[Source]) -> list[Source]:
    by_url: dict[str, Source] = {}
    for s in sources:
        cur = by_url.get(s.normalized_url)
        if cur is None:
            by_url[s.normalized_url] = s
            continue
        keep, other = (cur, s) if _quality(cur) <= _quality(s) else (s, cur)
        keep.is_preferred = keep.is_preferred or other.is_preferred
        keep.query_purposes = sorted(set(keep.query_purposes) | set(other.query_purposes))
        keep.query_languages = sorted(set(keep.query_languages) | set(other.query_languages))
        if keep.window is None and other.window is not None:
            keep.window = other.window
        by_url[s.normalized_url] = keep

    kept: list[Source] = []
    for s in sorted(by_url.values(), key=_quality):
        twin = next((k for k in kept if same_story(k.title, s.title)), None)
        if twin is None:
            kept.append(s)
            continue
        twin.is_preferred = twin.is_preferred or s.is_preferred
        if s.outlet != twin.outlet and s.url not in twin.also_reported_by:
            twin.also_reported_by.append(s.url)          # corroboration signal for D21 step 3
    return kept


def select_sources(sources: list[Source], cfg: DepthConfig, company_domain: str | None = None) -> list[Source]:
    """Ranked, capped list with diversity: at most `max_per_outlet` per outlet (overflow only fills
    leftover slots), and up to `min_hebrew_sources` Hebrew sources kept when any were found."""
    ranked = sorted(sources, key=_rank)
    per_outlet: dict[str, int] = {}
    picked, overflow = [], []
    for s in ranked:
        site = _site(s, company_domain)
        if per_outlet.get(site, 0) < cfg.max_per_outlet:
            per_outlet[site] = per_outlet.get(site, 0) + 1
            picked.append(s)
        else:
            overflow.append(s)
    chosen = (picked + overflow)[:cfg.max_sources]
    hebrew_missing = [s for s in picked + overflow if s.language == "he" and s not in chosen]
    need = cfg.min_hebrew_sources - sum(s.language == "he" for s in chosen)
    for s in hebrew_missing[:max(need, 0)]:
        # replace the lowest-ranked non-Hebrew, non-preferred source
        victim = next((c for c in reversed(chosen) if c.language != "he" and not c.is_preferred), None)
        if victim is None:
            break
        chosen.remove(victim)
        chosen.append(s)
    return sorted(chosen, key=_rank)


class ExternalResearchService:
    def __init__(self, provider: SearchProvider, now: Callable[[], datetime] | None = None):
        self.provider = provider
        self._now = now or (lambda: datetime.now(timezone.utc))

    def research_company(self, company: str, *, country: str | None = None, website: str | None = None,
                         depth: str | DepthConfig | None = None, preferred_urls=(), preferred_categories=(),
                         purposes: set[str] | None = None, limit: int | None = None,
                         budget: CreditBudget | None = None, extract: bool = True,
                         aliases: list[str] | tuple[str, ...] = ()) -> ExternalResearchResult:
        cfg = depth if isinstance(depth, DepthConfig) else get_depth(depth)
        plan = build_queries(company, cfg, country=country, website=website, preferred_urls=preferred_urls,
                             preferred_categories=preferred_categories, purposes=purposes, limit=limit)
        budget = budget if budget is not None else CreditBudget(cfg.credit_cap)
        credits_before = budget.used
        usage_before = self.provider.usage.snapshot()
        now = self._now()
        company_domain = domain_of(website) if website else None
        pref_domains = {d for d in (domain_of(u) for u in preferred_urls) if d}
        result = ExternalResearchResult(company=" ".join(company.split()), depth=cfg.name)
        self._language_notes(result, plan.languages)

        candidates: list[Source] = []
        attempted = succeeded = 0
        for q in plan.queries:
            attempted += 1
            try:
                raw = self.provider.search(
                    q.text, topic=q.topic, days=q.days, max_results=cfg.results_per_query,
                    search_depth=cfg.search_depth, include_domains=list(q.include_domains) or None,
                    country=q.country, budget=budget)
            except BudgetExceeded as exc:
                attempted -= 1
                result.budget_exhausted = True
                result.notes.append(f"Search stopped early: {exc}")
                break
            except FatalSearchError:
                raise
            except SearchError as exc:
                result.errors.append(f"{q.purpose} ({q.language}): {exc}")
                continue
            succeeded += 1
            result.queries_run.append({**q.to_dict(), "results": len(raw)})
            for r in raw:
                s = self._to_source(r, q, cfg, company_domain, pref_domains, now)
                if s is not None:
                    candidates.append(s)
        if attempted and not succeeded:
            raise SearchError("All external searches failed: " + "; ".join(result.errors))

        terms = company_terms(company, aliases)
        full_names = [n.strip().lower() for n in [company, *aliases] if n and n.strip()]
        relevant = [s for s in candidates if s.source_type == "official" or mentions_company(s, terms, full_names)]
        if len(relevant) < len(candidates):
            result.notes.append(f"Dropped {len(candidates) - len(relevant)} results that don't mention "
                                f"{' / '.join(terms)} (off-topic).")
        result.sources = select_sources(dedupe(relevant), cfg, company_domain)
        if extract and cfg.extract_top and result.sources and not result.budget_exhausted:
            self._extract(result, cfg, budget)
        result.credits_used = budget.used - credits_before
        after = self.provider.usage.snapshot()
        result.usage = {k: after[k] - usage_before.get(k, 0) for k in after}
        log.info("External research %r (%s): %d queries, %d sources, %d credits, %d errors",
                 result.company, cfg.name, succeeded, len(result.sources), result.credits_used, len(result.errors))
        return result

    def fetch_pages(self, urls: list[str], budget: CreditBudget | None = None) -> dict:
        """Main text of selected pages. Failures are listed, not hidden."""
        data = self.provider.extract(urls, budget=budget)
        pages = [{"url": r.get("url"), "content": (r.get("raw_content") or "")[:CONTENT_CHARS]}
                 for r in data["results"]]
        return {"pages": pages, "failed": data["failed_results"]}

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _language_notes(result: ExternalResearchResult, langs: LanguagePlan) -> None:
        result.search_languages = langs.search_languages
        result.local_language = langs.local_language
        result.local_language_searched = langs.local_language_searched
        if langs.local_language is None:
            result.notes.append("Company country unknown or not in the language table: searched in English "
                                "(+ one Hebrew query); local-language sources not checked.")
        elif not langs.local_language_searched:
            result.notes.append(f"Searched in {' and '.join(langs.search_languages)} only; sources in the local "
                                f"language ({langs.local_language}) were not checked (D37).")

    @staticmethod
    def _to_source(r: dict, q: QuerySpec, cfg: DepthConfig, company_domain: str | None,
                   pref_domains: set[str], now: datetime) -> Source | None:
        url = (r.get("url") or "").strip()
        norm = normalize_url(url)
        if not norm:
            return None
        host = domain_of(norm) or ""
        cls = classify_source(host, company_domain)
        published = trusted_date(r.get("published_date"), now)
        window = None
        if q.topic == "news":
            if published is None:
                window = "date_unknown"
            elif now - published <= RECENT:
                window = "last_48h"
            elif now - published <= timedelta(days=cfg.news_days):
                window = "in_range"
            else:
                return None                       # older than the depth's news range (Tavily `days` isn't strict)
        title = " ".join((r.get("title") or "").split())
        snippet = " ".join((r.get("content") or "").split())[:SNIPPET_CHARS]
        preferred = q.purpose == "preferred" or any(host == d or host.endswith("." + d) for d in pref_domains)
        score = r.get("score")
        return Source(
            id=source_id(norm), url=url, normalized_url=norm, title=title, outlet=host, published_at=published,
            retrieved_at=now, language=detect_language(f"{title} {snippet}"), source_type=cls.source_type,
            tier=cls.tier, snippet=snippet, window=window, is_preferred=preferred,
            query_purposes=[q.purpose], query_languages=[q.language],
            provider_score=float(score) if isinstance(score, (int, float)) else None)

    def _extract(self, result: ExternalResearchResult, cfg: DepthConfig, budget: CreditBudget) -> None:
        targets = [s for s in result.sources if s.tier < 4][:cfg.extract_top]
        if not targets:
            return
        try:
            data = self.provider.extract([s.url for s in targets], budget=budget)
        except BudgetExceeded as exc:
            result.budget_exhausted = True
            result.notes.append(f"Page extraction skipped: {exc}")
            return
        except FatalSearchError:
            raise
        except SearchError as exc:
            result.errors.append(f"extract: {exc}")
            return
        by_url = {normalize_url(r.get("url") or ""): r.get("raw_content") or "" for r in data["results"]}
        for s in targets:
            text = by_url.get(s.normalized_url)
            if text:
                s.content = text[:CONTENT_CHARS]
        for f in data["failed_results"]:
            result.notes.append(f"Could not extract {f.get('url')}: {f.get('error', 'unknown error')}")
