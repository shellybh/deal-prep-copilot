"""Query builder (D17, D37).

Builds an ordered list of `QuerySpec`s for one company. Order = priority: when the depth cap cuts the
list, the least important queries go first. Preferred URLs / categories add targeted queries near the
top (search priority only); they never change a source's credibility tier.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.research.depth import DepthConfig
from app.research.languages import COUNTRY_NAMES, LanguagePlan, language_plan
from app.research.tiering import category_domains, hebrew_media_domains
from app.research.urls import domain_of

PURPOSES = ("profile", "news_recent", "news", "financial", "people", "press", "competitors", "israel",
            "preferred")
NEWS_PURPOSES = ("news_recent", "news")
RECENT_DAYS = 2   # "last 48 hours" query, always run (D17)


@dataclass(frozen=True)
class QuerySpec:
    text: str
    language: str              # en | he
    purpose: str
    topic: str = "general"     # general | news
    days: int | None = None
    include_domains: tuple[str, ...] = ()
    country: str | None = None  # Tavily `country` boost (general topic only)

    def to_dict(self) -> dict:
        d = {"text": self.text, "language": self.language, "purpose": self.purpose, "topic": self.topic}
        if self.days is not None:
            d["days"] = self.days
        if self.include_domains:
            d["include_domains"] = list(self.include_domains)
        return d


@dataclass
class QueryPlan:
    queries: list[QuerySpec]
    languages: LanguagePlan
    dropped: list[QuerySpec] = field(default_factory=list)   # cut by the cap (Phase 4 extra rounds may use them)


def _en(company: str, country_name: str | None, depth: DepthConfig, tav_country: str | None) -> dict[str, QuerySpec]:
    where = f" {country_name}" if country_name else ""
    return {
        "profile": QuerySpec(f"{company}{where} company overview products customers", "en", "profile",
                             country=tav_country),
        "news_recent": QuerySpec(company, "en", "news_recent", topic="news", days=RECENT_DAYS),
        "news": QuerySpec(company, "en", "news", topic="news", days=depth.news_days),
        "competitors": QuerySpec(f"{company} competitors alternatives market position", "en", "competitors"),
        "financial": QuerySpec(f"{company} revenue funding financial results", "en", "financial"),
        "people": QuerySpec(f"{company} CEO leadership team executives", "en", "people"),
        "press": QuerySpec(f"{company} press release announcement", "en", "press"),
    }


def _he(company: str, depth: DepthConfig) -> dict[str, QuerySpec]:
    # Tavily returns few Hebrew results for Hebrew queries alone (2C/3 finding), so news / financial /
    # people queries target Israeli Hebrew outlets. Same number of queries, same credits.
    media = tuple(hebrew_media_domains())
    return {
        "profile": QuerySpec(f"{company} חברה מוצרים לקוחות", "he", "profile", country="israel"),
        "news": QuerySpec(f"{company} חדשות", "he", "news", topic="news", days=depth.news_days, include_domains=media),
        "financial": QuerySpec(f"{company} הכנסות גיוס דוחות כספיים", "he", "financial", country="israel",
                               include_domains=media),
        "people": QuerySpec(f'{company} מנכ"ל הנהלה', "he", "people", country="israel", include_domains=media),
        "competitors": QuerySpec(f"{company} מתחרים", "he", "competitors", country="israel"),
    }


def build_queries(company: str, depth: DepthConfig, *, country: str | None = None, website: str | None = None,
                  preferred_urls: list[str] | tuple[str, ...] = (), preferred_categories: list[str] | tuple[str, ...] = (),
                  purposes: set[str] | None = None, limit: int | None = None) -> QueryPlan:
    """Ordered, capped query list. `purposes` filters (used by the single-purpose agent tools);
    `limit` defaults to the depth's `initial_queries`."""
    company = " ".join((company or "").split())
    if not company:
        raise ValueError("company name is empty")
    langs = language_plan(country)
    country_name = COUNTRY_NAMES.get(langs.country_code or "")
    en = _en(company, country_name, depth, langs.tavily_country)
    ordered: list[QuerySpec] = [en["profile"], en["news_recent"]]

    # Preferred sources first after the basics: search priority only.
    pref_domains = tuple(dict.fromkeys(d for d in (domain_of(u) for u in preferred_urls) if d))
    if pref_domains:
        ordered.append(QuerySpec(company, "en", "preferred", include_domains=pref_domains))
    company_domain = domain_of(website) if website else None
    for cat in preferred_categories:
        domains = category_domains(cat, company_domain=company_domain)
        if domains:
            ordered.append(QuerySpec(company, "en", "preferred", include_domains=tuple(domains)))

    if "he" in langs.full_languages:            # Israeli company: full Hebrew set, interleaved by priority
        he = _he(company, depth)
        ordered += [he["profile"], en["news"], he["news"], en["competitors"], en["financial"], he["financial"],
                    en["people"], he["people"], en["press"], he["competitors"]]
    else:                                        # foreign company: one Hebrew query (D37, every depth)
        ordered += [QuerySpec(f"{company} ישראל", "he", "israel", country="israel"), en["news"],
                    en["competitors"], en["financial"], en["people"], en["press"]]

    if purposes is not None:
        ordered = [q for q in ordered if q.purpose in purposes]
    cap = min(limit if limit is not None else depth.initial_queries, depth.max_queries)
    return QueryPlan(queries=ordered[:cap], languages=langs, dropped=ordered[cap:])
