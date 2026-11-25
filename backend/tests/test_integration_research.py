"""Live Phase 3 smoke test against Tavily (python -m pytest -m integration tests/test_integration_research.py).
Costs about 13 credits: two Quick runs (6 each) + one page extract (1). Skipped without TAVILY_API_KEY."""
import os

import pytest

from app.research.provider import TavilyClient
from app.research.service import ExternalResearchService

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not os.getenv("TAVILY_API_KEY"), reason="TAVILY_API_KEY not set")]


@pytest.fixture(scope="module")
def svc():
    return ExternalResearchService(TavilyClient())


def _check_common(r):
    assert r.sources, "no sources returned"
    assert not r.errors, r.errors
    assert len({s.normalized_url for s in r.sources}) == len(r.sources)      # deduplicated
    for s in r.sources:
        assert 1 <= s.tier <= 4 and s.url and s.outlet
        assert s.published_at is None or s.published_at.tzinfo is not None   # dated or explicitly undated


def test_israeli_company_hebrew_and_english(svc):
    r = svc.research_company("monday.com", country="Israel", website="monday.com", depth="quick")
    _check_common(r)
    assert r.search_languages == ["he", "en"] and r.local_language_searched
    assert {s.language for s in r.sources} >= {"en"}
    assert any(s.source_type == "official" for s in r.sources) or any(s.tier <= 2 for s in r.sources)
    assert r.credits_used <= 8


def test_foreign_company_english_plus_one_hebrew_query_and_extract(svc):
    r = svc.research_company("Snowflake", country="United States", website="snowflake.com", depth="quick")
    _check_common(r)
    assert r.search_languages == ["en", "he"]
    assert sum(q["language"] == "he" for q in r.queries_run) == 1
    page = svc.fetch_pages([r.sources[0].url])
    assert page["pages"] or page["failed"]                                     # either way, nothing hidden
