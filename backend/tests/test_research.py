"""Phase 3 external research: provider, languages, queries, URLs, tiers, dedup, service (no network)."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.research.dates import parse_date, trusted_date
from app.research.depth import DEPTHS, get_depth
from app.research.languages import language_plan, normalize_country
from app.research.provider import (BudgetExceeded, CreditBudget, FatalSearchError, ResponseCache, SearchError,
                                   TavilyClient, Usage, extract_cost, search_cost)
from app.research.queries import build_queries
from app.research.service import ExternalResearchService, company_terms, dedupe, is_relevant, select_sources
from app.research.sources import Source, detect_language
from app.research.tiering import category_domains, classify_source
from app.research.urls import domain_of, normalize_url, same_story

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def rfc(hours_ago: float) -> str:
    return format_datetime(NOW - timedelta(hours=hours_ago), usegmt=True)


def res(url, title="Some title here", hours_ago=None, content="body text", score=0.5):
    r = {"url": url, "title": title, "content": content, "score": score}
    if hours_ago is not None:
        r["published_date"] = rfc(hours_ago)
    return r


class FakeProvider:
    """SearchProvider double. `results(query_spec_kwargs) -> list[dict]` decides what each call returns."""

    def __init__(self, results=None, fail=None, extract=None, cost=1):
        self.usage = Usage()
        self.calls: list[dict] = []
        self.extract_calls: list[list[str]] = []
        self._results = results or (lambda call: [])
        self._fail = fail or (lambda call: None)
        self._extract = extract or (lambda urls: {"results": [], "failed_results": []})
        self._cost = cost

    def search(self, query, *, topic="general", days=None, max_results=5, search_depth="basic",
               include_domains=None, country=None, budget=None):
        call = {"query": query, "topic": topic, "days": days, "max_results": max_results,
                "search_depth": search_depth, "include_domains": include_domains, "country": country}
        if budget:
            budget.check(self._cost)
        self.calls.append(call)
        err = self._fail(call)
        if err:
            raise err
        if budget:
            budget.charge(self._cost)
        self.usage.credits += self._cost
        self.usage.searches += 1
        return self._results(call)

    def extract(self, urls, *, extract_depth="basic", budget=None):
        if budget:
            budget.check(extract_cost(len(urls)))
            budget.charge(extract_cost(len(urls)))
        self.extract_calls.append(list(urls))
        return self._extract(urls)


def service(provider):
    return ExternalResearchService(provider, now=lambda: NOW)


# ---------------------------------------------------------------- URLs
@pytest.mark.parametrize("raw,expected", [
    ("https://www.Example.com/a/?utm_source=x&b=2&a=1#top", "https://example.com/a?a=1&b=2"),
    ("http://example.com/", "https://example.com/"),
    ("https://example.com:443/x/", "https://example.com/x"),
    ("https://example.com/story/amp/", "https://example.com/story"),
    ("https://amp.example.com/story?gclid=1&fbclid=2", "https://example.com/story"),
    ("example.com/news//item", "https://example.com/news/item"),
    ("https://example.com:8080/x", "https://example.com:8080/x"),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_domain_of():
    assert domain_of("https://www.monday.com/pricing") == "monday.com"
    assert domain_of("monday.com") == "monday.com"
    assert domain_of("") is None and domain_of(None) is None


def test_same_story_across_outlets_and_short_titles():
    assert same_story("Acme raises $50M Series C to expand in Europe - Reuters",
                      "Acme raises $50M Series C to expand in Europe | TechCrunch")
    assert not same_story("Acme raises $50M Series C to expand in Europe", "Acme cuts 10% of staff after weak quarter")
    assert not same_story("monday.com", "monday.com")                  # short generic titles never merge
    assert same_story("אקמה מגייסת 50 מיליון דולר בסבב C", "אקמה מגייסת 50 מיליון דולר בסבב C - גלובס")


# ---------------------------------------------------------------- dates
def test_dates_never_invented():
    assert parse_date("Tue, 03 Nov 2026 15:00:00 GMT") == datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
    assert parse_date("2026-11-03") == datetime(2026, 11, 3, tzinfo=timezone.utc)
    assert parse_date("last week") is None and parse_date(None) is None
    assert trusted_date(rfc(-24 * 5), NOW) is None             # 5 days in the future → unknown
    assert trusted_date(rfc(3), NOW) is not None


# ---------------------------------------------------------------- languages (D37)
@pytest.mark.parametrize("raw,code", [("Israel", "IL"), ("ישראל", "IL"), ("il", "IL"), ("  United   States ", "US"),
                                      ('ארה"ב', "US"), ("Germany", "DE"), ("Narnia", None), (None, None), ("", None)])
def test_normalize_country(raw, code):
    assert normalize_country(raw) == code


def test_language_plan_israel_full_hebrew_and_english():
    p = language_plan("ישראל")
    assert p.full_languages == ("he", "en") and not p.extra_hebrew_query
    assert p.search_languages == ["he", "en"] and p.local_language_searched


def test_language_plan_foreign_english_plus_one_hebrew_query():
    us = language_plan("USA")
    assert us.full_languages == ("en",) and us.extra_hebrew_query and us.search_languages == ["en", "he"]
    assert us.local_language_searched                       # English is the local language
    de = language_plan("Germany")
    assert de.local_language == "de" and not de.local_language_searched
    unknown = language_plan("Narnia")
    assert unknown.local_language is None and not unknown.local_language_searched
    assert unknown.search_languages == ["en", "he"]


# ---------------------------------------------------------------- depth + queries
def test_depth_config_and_aliases():
    assert get_depth().name == "standard" and get_depth("In-Depth").name == "in_depth"
    assert all(d.search_depth == "basic" for d in DEPTHS.values())          # D37
    assert all(d.initial_queries <= d.max_queries for d in DEPTHS.values())
    assert get_depth("quick", credit_cap=3).credit_cap == 3
    with pytest.raises(ValueError):
        get_depth("extreme")


@pytest.mark.parametrize("depth", ["quick", "standard", "in_depth"])
def test_foreign_company_gets_one_hebrew_query_at_every_depth(depth):
    plan = build_queries("Snowflake", get_depth(depth), country="United States")
    he = [q for q in plan.queries if q.language == "he"]
    assert len(he) == 1 and he[0].text == "Snowflake ישראל" and he[0].purpose == "israel"
    assert len(plan.queries) == min(get_depth(depth).initial_queries, 8)   # foreign company: 8 queries exist


def test_israeli_company_full_hebrew_set_and_48h_news():
    plan = build_queries("monday.com", get_depth("in_depth"), country="Israel")
    langs = {q.language for q in plan.queries}
    assert langs == {"he", "en"}
    assert sum(q.language == "he" for q in plan.queries) >= 4
    recent = [q for q in plan.queries if q.purpose == "news_recent"]
    assert recent and recent[0].topic == "news" and recent[0].days == 2
    news = [q for q in plan.queries if q.purpose == "news"]
    assert all(q.days == 365 for q in news)                  # depth news range
    assert len({q.text for q in news}) == len(news)          # Hebrew news query isn't a copy of the English one
    assert any("חדשות" in q.text for q in news if q.language == "he")


def test_quick_cap_and_priority_order():
    plan = build_queries("Acme", get_depth("quick"), country="US")
    assert len(plan.queries) == 6 and plan.dropped
    assert [q.purpose for q in plan.queries][:3] == ["profile", "news_recent", "israel"]


def test_purpose_filter_and_limit():
    plan = build_queries("Acme", get_depth("standard"), country="IL", purposes={"competitors"})
    assert {q.purpose for q in plan.queries} == {"competitors"} and len(plan.queries) == 2   # en + he
    assert len(build_queries("Acme", get_depth("in_depth"), limit=50).queries) <= get_depth("in_depth").max_queries


def test_preferred_urls_and_categories_add_targeted_queries_early():
    plan = build_queries("Acme", get_depth("standard"), country="US", website="acme.io",
                         preferred_urls=["https://www.globes.co.il/x", "globes.co.il"],
                         preferred_categories=["official", "nonsense"])
    pref = [q for q in plan.queries if q.purpose == "preferred"]
    assert pref[0].include_domains == ("globes.co.il",)            # deduplicated
    assert "acme.io" in pref[1].include_domains and "prnewswire.com" in pref[1].include_domains
    assert len(pref) == 2                                            # unknown category ignored
    assert [q.purpose for q in plan.queries].index("preferred") == 2


def test_empty_company_rejected():
    with pytest.raises(ValueError):
        build_queries("  ", get_depth())


# ---------------------------------------------------------------- tiers (D21 step 1)
@pytest.mark.parametrize("host,company,stype,tier", [
    ("ir.acme.com", "acme.com", "official", 1),
    ("www.sec.gov", None, "government_regulatory", 1),
    ("maya.tase.co.il", None, "government_regulatory", 1),
    ("data.gov.il", None, "government_regulatory", 1),
    ("www.globes.co.il", None, "news", 2),
    ("calcalistech.com", None, "news", 2),
    ("finance.yahoo.com", None, "professional_industry", 3),
    ("news.theglobeandmail.com", None, "news", 2),
    ("prnewswire.com", None, "official", 2),
    ("techcrunch.com", None, "professional_industry", 3),
    ("reddit.com", None, "other", 4),
    ("random-blog.net", None, "other", 4),
    ("", None, "other", 4),
])
def test_classify_source(host, company, stype, tier):
    c = classify_source(host, company)
    assert (c.source_type, c.tier) == (stype, tier)


def test_category_domains():
    assert "globes.co.il" in category_domains("news")
    assert category_domains("official", company_domain="acme.io")[0] == "acme.io"
    assert category_domains("unknown") == []


# ---------------------------------------------------------------- language detection
def test_detect_language():
    assert detect_language("מנדיי מדווחת על צמיחה") == "he"
    assert detect_language("monday.com reports growth") == "en"
    assert detect_language("monday.com מדווחת על צמיחה ברבעון") == "he"
    assert detect_language("123 456") == "other"


# ---------------------------------------------------------------- provider (mocked HTTP)
def _client(handler, **kw):
    return TavilyClient(api_key="test-key", http=httpx.Client(transport=httpx.MockTransport(handler)),
                        sleep=lambda s: None, **kw)


def test_search_request_shape():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"results": [res("https://a.com/1")]})

    c = _client(handler)
    out = c.search("Acme", include_domains=["a.com"], country="israel", days=None)
    assert len(out) == 1 and seen["url"].endswith("/search")
    body = json.loads(seen["body"])
    assert body["include_domains"] == ["a.com"] and body["country"] == "israel"
    assert "days" not in body and body["search_depth"] == "basic"
    c.search("Acme", topic="news", days=2, country="israel")
    assert "country" not in json.loads(seen["body"])             # country only for the general topic
    assert c.usage.credits == 2 and c.usage.searches == 2


def test_costs():
    assert search_cost("basic") == 1 and search_cost("advanced") == 2
    assert extract_cost(0) == 0 and extract_cost(1) == 1 and extract_cost(5) == 1 and extract_cost(6) == 2
    assert extract_cost(5, "advanced") == 2


def test_budget_blocks_before_sending():
    calls = []
    c = _client(lambda r: calls.append(1) or httpx.Response(200, json={"results": []}))
    b = CreditBudget(limit=1)
    c.search("Acme", budget=b)
    with pytest.raises(BudgetExceeded):
        c.search("Acme 2", budget=b)
    assert len(calls) == 1 and b.used == 1 and b.remaining == 0


@pytest.mark.parametrize("status,exc,msg", [(401, FatalSearchError, "TAVILY_API_KEY"),
                                            (432, FatalSearchError, "credit limit"),
                                            (400, SearchError, "400")])
def test_provider_errors_surface(status, exc, msg):
    c = _client(lambda r: httpx.Response(status, json={}))
    with pytest.raises(exc, match=msg):
        c.search("Acme")


def test_retry_then_success_charges_once():
    responses = iter([httpx.Response(503), httpx.Response(200, json={"results": []})])
    c = _client(lambda r: next(responses))
    b = CreditBudget(limit=5)
    c.search("Acme", budget=b)
    assert c.usage.requests == 2 and c.usage.credits == 1 and b.used == 1


def test_extract_shape_and_cost():
    def handler(request):
        assert str(request.url).endswith("/extract")
        return httpx.Response(200, json={"results": [{"url": "https://a.com", "raw_content": "x"}],
                                         "failed_results": [{"url": "https://b.com", "error": "timeout"}]})

    c = _client(handler)
    out = c.extract(["https://a.com", "https://b.com"])
    assert out["results"][0]["raw_content"] == "x" and out["failed_results"][0]["error"] == "timeout"
    assert c.usage.credits == 1
    assert c.extract([]) == {"results": [], "failed_results": []}


def test_cache_reuses_responses_without_credits(tmp_path):
    calls = []
    c = _client(lambda r: calls.append(1) or httpx.Response(200, json={"results": [res("https://a.com")]}),
                cache=ResponseCache(tmp_path))
    b = CreditBudget(limit=1)
    first = c.search("Acme", budget=b)
    second = c.search("Acme", budget=b)                          # cache hit: no request, no charge
    assert first == second and len(calls) == 1 and c.usage.cache_hits == 1 and b.used == 1
    c.search("Other", budget=CreditBudget(limit=5))
    assert len(calls) == 2


# ---------------------------------------------------------------- dedup
def _src(url, title, tier=2, published=None, outlet=None, preferred=False, window=None, snippet="s"):
    norm = normalize_url(url)
    return Source(id="x", url=url, normalized_url=norm, title=title, outlet=outlet or domain_of(norm),
                  published_at=published, retrieved_at=NOW, language="en", source_type="news", tier=tier,
                  snippet=snippet, is_preferred=preferred, window=window, query_purposes=["profile"],
                  query_languages=["en"])


def test_dedupe_same_url_merges_flags():
    a = _src("https://www.a.com/x?utm_source=1", "Acme story one two three", preferred=True)
    b = _src("https://a.com/x/", "Acme story one two three", published=NOW, window="last_48h")
    out = dedupe([a, b])
    assert len(out) == 1 and out[0].is_preferred and out[0].window == "last_48h" and out[0].published_at


def test_dedupe_same_story_keeps_best_and_records_corroboration():
    blog = _src("https://blog.net/acme", "Acme raises $50M Series C to expand in Europe", tier=4)
    reuters = _src("https://reuters.com/acme", "Acme raises $50M Series C to expand in Europe - Reuters", tier=2)
    out = dedupe([blog, reuters])
    assert len(out) == 1 and out[0].outlet == "reuters.com" and out[0].also_reported_by == ["https://blog.net/acme"]


# ---------------------------------------------------------------- service
def test_research_company_end_to_end_with_fake_provider():
    def results(call):
        if call["topic"] == "news" and call["days"] == 2:
            return [res("https://www.globes.co.il/news/1", "Acme signs deal with Bank Leumi for AI rollout", 5),
                    res("https://old.com/x", "Old Acme item from two years ago today", 24 * 800)]   # dropped
        if call["topic"] == "news":
            return [res("https://reuters.com/acme-q3", "Acme Q3 revenue grows 30 percent year over year", 24 * 20),
                    res("https://nodate.com/acme", "Acme opens a new office in London this month")]
        if "ישראל" in call["query"]:
            return [res("https://www.calcalist.co.il/acme", "אקמה פותחת מרכז פיתוח בתל אביב", 24 * 3,
                        content="אקמה פותחת מרכז פיתוח חדש")]
        return [res("https://acme.io/about", "About Acme - the data company for teams"),
                res("https://acme.io/about/", "About Acme - the data company for teams")]       # duplicate URL

    p = FakeProvider(results=results)
    r = service(p).research_company("Acme", country="US", website="https://acme.io", depth="quick")
    by_url = {s.normalized_url: s for s in r.sources}
    assert "https://old.com/x" not in by_url
    assert sum(1 for s in r.sources if s.outlet == "acme.io") == 1
    assert by_url["https://acme.io/about"].source_type == "official" and by_url["https://acme.io/about"].tier == 1
    assert by_url["https://globes.co.il/news/1"].window == "last_48h"
    assert by_url["https://nodate.com/acme"].window == "date_unknown" and by_url["https://nodate.com/acme"].published_at is None
    assert by_url["https://calcalist.co.il/acme"].language == "he"
    assert r.sources[0].window == "last_48h"                       # 48 h news ranked first
    assert [s.url for s in r.recent_news] == ["https://www.globes.co.il/news/1"]
    assert r.search_languages == ["en", "he"] and r.local_language_searched
    assert len(p.calls) == 6 and r.credits_used == 6 and not r.errors
    assert all(c["search_depth"] == "basic" for c in p.calls)
    d = r.to_dict()
    assert d["sources"][0]["published_at"] and d["recent_news_ids"]


def test_local_language_not_searched_is_noted():
    r = service(FakeProvider()).research_company("Siemens", country="Germany", depth="quick")
    assert not r.local_language_searched and any("(de)" in n for n in r.notes)


def test_preferred_source_gets_priority_not_credibility():
    def results(call):
        if call["include_domains"]:
            return [res("https://myblog.example/acme", "Acme deep dive written by a fan of the product")]
        return [res("https://reuters.com/acme", "Acme expands its partner program in Europe again")]

    r = service(FakeProvider(results=results)).research_company(
        "Acme", country="US", depth="quick", preferred_urls=["https://myblog.example"])
    first = r.sources[0]
    assert first.outlet == "myblog.example" and first.is_preferred
    assert first.tier == 4 and first.source_type == "other"        # real tier kept


def test_budget_stops_search_and_is_reported():
    p = FakeProvider(results=lambda c: [res(f"https://a.com/{len(c['query'])}", c["query"] + " unique title words")])
    r = service(p).research_company("Acme", country="US", depth="standard", budget=CreditBudget(limit=3),
                                    extract=False)
    assert len(p.calls) == 3 and r.budget_exhausted and r.credits_used == 3
    assert any("credit cap" in n for n in r.notes)


def test_partial_failures_listed_fatal_and_total_failures_raise():
    def fail_competitors(call):
        return SearchError("Tavily search failed (400).") if "competitors" in call["query"] else None

    r = service(FakeProvider(fail=fail_competitors)).research_company("Acme", country="US", depth="quick")
    assert len(r.errors) == 1 and r.errors[0].startswith("competitors (en)")

    with pytest.raises(SearchError, match="All external searches failed"):
        service(FakeProvider(fail=lambda c: SearchError("Tavily search failed (503)."))).research_company(
            "Acme", depth="quick")
    with pytest.raises(FatalSearchError):
        service(FakeProvider(fail=lambda c: FatalSearchError("bad key"))).research_company("Acme", depth="quick")


def test_extract_top_sources_attaches_content_and_reports_failures():
    def results(call):
        return [res("https://reuters.com/a", "Acme story number one with enough words"),
                res("https://reddit.com/r/acme", "Reddit thread about Acme and its many features")]

    def extract(urls):
        return {"results": [{"url": "https://reuters.com/a", "raw_content": "Full article " * 1000}],
                "failed_results": [{"url": "https://x", "error": "timeout"}]}

    p = FakeProvider(results=results, extract=extract)
    r = service(p).research_company("Acme", country="US", depth="standard")
    assert p.extract_calls == [["https://reuters.com/a"]]           # tier 4 not extracted
    art = next(s for s in r.sources if s.outlet == "reuters.com")
    assert art.content and len(art.content) == 6000
    assert any("Could not extract" in n for n in r.notes)


def test_max_sources_cap():
    p = FakeProvider(results=lambda c: [res(f"https://site{uuid.uuid4().hex}.com/x",
                                            "Acme " + " ".join(uuid.uuid4().hex[j:j + 4] for j in range(0, 24, 4)))
                                        for _ in range(5)])
    r = service(p).research_company("Acme", country="US", depth="quick")
    assert len(r.sources) == get_depth("quick").max_sources


def test_select_sources_caps_each_outlet_and_keeps_hebrew():
    own = [_src(f"https://acme.io/p{i}", f"Acme page number {i} about products", tier=1) for i in range(6)]
    news = [_src(f"https://reuters.com/{i}", f"Reuters story {i} about Acme growth", tier=2) for i in range(2)]
    he = _src("https://calcalist.co.il/acme", "אקמה פותחת מרכז פיתוח בתל אביב", tier=2)
    he = he.model_copy(update={"language": "he"})
    blog = _src("https://blog.net/a", "Blog post about Acme pricing tiers", tier=4)
    cfg = get_depth("quick", max_sources=6, max_per_outlet=3, min_hebrew_sources=1)
    out = select_sources(own + news + [blog, he], cfg)
    assert len(out) == 6
    assert sum(s.outlet == "acme.io" for s in out) == 3            # own site capped
    assert any(s.language == "he" for s in out)                    # Hebrew kept
    assert {s.outlet for s in out} >= {"reuters.com", "calcalist.co.il"}


def test_select_sources_overflow_fills_leftover_slots():
    own = [_src(f"https://acme.io/p{i}", f"Acme page number {i} about products", tier=1) for i in range(5)]
    out = select_sources(own, get_depth("quick", max_per_outlet=2))
    assert len(out) == 5                                           # nothing else to show: overflow used


def test_company_terms_and_relevance():
    assert company_terms("monday.com") == ["monday"]
    assert company_terms("Acme Technologies Ltd", aliases=["אקמה בע\"מ"]) == ["acme", "אקמה"]
    assert is_relevant("Monday.com stock falls after Q3", ["monday"])
    assert not is_relevant("Netanyahu presses Trump on Iran", ["monday"])
    assert not is_relevant("Mondays are hard", ["monday"])                 # whole words only
    assert is_relevant("אקמה מגייסת 50 מיליון", ["acme", "אקמה"])


def test_off_topic_results_dropped_and_noted():
    def results(call):
        return [res("https://jpost.com/x", "Netanyahu presses Trump to renew strikes on Iran"),
                res("https://reuters.com/acme", "Acme expands into Europe with new office"),
                res("https://acme.io/careers", "Careers - join the team")]                 # own site: kept
    r = service(FakeProvider(results=results)).research_company("Acme", country="US", website="acme.io",
                                                                depth="quick")
    outlets = {s.outlet for s in r.sources}
    assert outlets == {"reuters.com", "acme.io"}
    assert any("off-topic" in n for n in r.notes)


def test_company_subdomains_share_the_outlet_cap():
    own = [_src(f"https://{sub}.acme.io/p{i}", f"Acme page {sub} number {i} about products", tier=1)
           for sub in ("www", "ir", "docs") for i in range(2)]
    out = select_sources(own, get_depth("quick", max_sources=3, max_per_outlet=2), company_domain="acme.io")
    assert len(out) == 3   # 2 from the cap + 1 overflow (nothing else to show)


def test_weekday_in_snippet_is_not_a_mention():
    def results(call):
        return [res("https://jpost.com/x", "Netanyahu presses Trump on Iran", content="He said on Monday that..."),
                res("https://calcalistech.com/y", "Wave of senior departures hits Monday", content="The company..."),
                res("https://z.com/q", "Israeli SaaS leader cuts staff", content="monday.com announced cuts")]
    r = service(FakeProvider(results=results)).research_company("monday.com", country="IL", depth="quick")
    assert {s.outlet for s in r.sources} == {"calcalistech.com", "z.com"}


def test_hebrew_news_queries_target_israeli_hebrew_outlets():
    plan = build_queries("monday.com", get_depth("in_depth"), country="IL")
    he_news = next(q for q in plan.queries if q.language == "he" and q.purpose == "news")
    assert "globes.co.il" in he_news.include_domains and "calcalist.co.il" in he_news.include_domains
    assert classify_source("globes.co.il").tier == 2           # hebrew_media is not a tier group
