"""Company identification check before the briefing (Phase 3.5, D38 §2).

One deterministic check, not the model's judgment:
1. Web: one `profile` query at Quick depth (≈ 1 Tavily credit), no extraction. Identified if at least one
   source survives the Phase 3 relevance filter (company name in title / URL, full name in snippet, or a
   page on the company's own website).
2. Internal KB (only if the web check found nothing): a company that only our KB knows (e.g. a competitor
   battlecard) is still identified. One embedding call, no Tavily credits.

If the web search itself fails (not a bad key), the check can't decide: `identified` is None and the run
continues with a warning rather than blocking a real company.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from app.research.provider import FatalSearchError, SearchError
from app.research.service import company_terms, is_relevant
from app.research.urls import domain_of

IDENTIFY_PURPOSES = {"profile"}
IDENTIFY_DEPTH = "quick"
INTERNAL_K = 3
_DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class InvalidWebsite(ValueError):
    pass


def parse_website(raw: str | None) -> str | None:
    """'https://www.monday.com/pricing' / 'monday.com' → 'monday.com'. None / blank → None.
    Raises InvalidWebsite for anything that isn't an http(s) URL or a bare domain."""
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    scheme = value.split("://", 1)[0].lower() if "://" in value else None
    if scheme not in (None, "http", "https") or "@" in value or any(ch.isspace() for ch in value):
        raise InvalidWebsite(f"'{raw}' is not a website (use a URL like https://example.com or a domain)")
    try:
        domain = domain_of(value)
    except ValueError:
        domain = None
    if not domain or not _DOMAIN.match(domain):
        raise InvalidWebsite(f"'{raw}' is not a website (use a URL like https://example.com or a domain)")
    return domain


@dataclass
class Identification:
    company: str
    domain: str | None
    identified: bool | None          # None = the check could not run (search error)
    via: str | None = None           # "web" | "internal" | None
    web_sources: int = 0
    internal_mentions: int = 0
    credits_used: int = 0
    evidence: list[str] = field(default_factory=list)   # URLs / citations that matched
    error: str | None = None
    domain_inferred: bool = False    # True = no website was given; `domain` was found in the web results

    def summary(self) -> str:
        text = self._summary()
        return f"{text}; official site: {self.domain}" if self.domain_inferred else text

    def _summary(self) -> str:
        if self.identified is None:
            return f"identification check failed ({self.error}); continued without it"
        if not self.identified:
            return "not identified"
        if self.via == "web":
            return f"identified on the web ({self.web_sources} relevant sources)"
        return f"identified in the internal knowledge base ({self.internal_mentions} matching chunks)"


# Words a company's own domain may add after its name ('elbitsystems.com', 'snowflakeinc.com'). Anything
# else ('siemens-energy.com', 'mondaymagazine.com') is treated as a different site.
_DOMAIN_SUFFIXES = ("", "systems", "inc", "corp", "group", "global", "hq", "tech", "technologies", "software",
                    "labs", "app", "ai", "io", "data", "co", "company", "official")
_LEGAL = {"inc", "ltd", "llc", "corp", "corporation", "plc", "ag", "gmbh", "sa", "nv", "bv", "co", "company"}
_SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov"}   # 'elbit.co.il' → keep three labels


def _registrable(host: str) -> str:
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def infer_official_domain(company: str, urls: list[str | None]) -> str | None:
    """The company's own domain from the identification results when the user gave no website, so its
    pages count as official (tier 1) in the research. Deterministic: the domain's name label must be the
    company name (letters / digits only) plus at most one known suffix. Most frequent match wins.
    Non-Latin names ('אלביט') never match: no guess."""
    words = re.sub(r"\.(com|io|ai|co|net|org)$", "", company.lower().strip()).split()   # 'monday.com'
    while len(words) > 1 and re.sub(r"[^a-z]", "", words[-1]) in _LEGAL:                  # 'Siemens AG'
        words.pop()
    name = re.sub(r"[^a-z0-9]", "", "".join(words))
    if len(name) < 3:
        return None
    counts: dict[str, int] = {}
    for url in urls:
        host = domain_of(url) if url else None
        if not host:
            continue
        reg = _registrable(host)
        label = re.sub(r"[^a-z0-9]", "", reg.split(".")[0])
        if label.startswith(name) and label[len(name):] in _DOMAIN_SUFFIXES:
            counts[reg] = counts.get(reg, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _default_web(company: str, website: str | None) -> dict:
    from app.tools import research_service  # lazy: no Tavily client when tests inject fakes
    return research_service().research_company(
        company, website=website, depth=IDENTIFY_DEPTH, purposes=IDENTIFY_PURPOSES, limit=1,
        extract=False).to_dict()


def _default_internal(query: str, k: int) -> list[dict]:
    from app.tools import search_internal_docs
    return search_internal_docs(query, k=k)


def identify_company(company: str, domain: str | None = None,
                     web_fn: Callable[[str, str | None], dict] | None = None,
                     internal_fn: Callable[..., list[dict]] | None = None) -> Identification:
    web_fn = web_fn or _default_web
    internal_fn = internal_fn or _default_internal
    ident = Identification(company=company, domain=domain, identified=False)

    try:
        web = web_fn(company, domain)
    except FatalSearchError:
        raise                                     # bad key / plan limit: the whole run would fail anyway
    except SearchError as exc:
        ident.identified, ident.error = None, str(exc)
        return ident
    sources = web.get("sources") or []
    ident.credits_used = web.get("credits_used", 0)
    if sources:
        ident.identified, ident.via, ident.web_sources = True, "web", len(sources)
        ident.evidence = [s["url"] for s in sources[:3]]
        if domain is None:
            ident.domain = infer_official_domain(company, [s.get("url") for s in sources])
            ident.domain_inferred = ident.domain is not None
        return ident

    terms = company_terms(company)
    chunks = [c for c in internal_fn(company, k=INTERNAL_K) if is_relevant(c.get("content", ""), terms)]
    if chunks:
        ident.identified, ident.via, ident.internal_mentions = True, "internal", len(chunks)
        ident.evidence = [c["citation"] for c in chunks]
    return ident
