"""search_live_news / Tavily adapter with mocked HTTP (no network)."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.research.news import (WINDOW_30D, WINDOW_48H, WINDOW_UNKNOWN, NewsSearchError, TavilyProvider,
                               classify, parse_date, search_news)

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def rfc(hours_ago: float) -> str:
    return format_datetime(NOW - timedelta(hours=hours_ago), usegmt=True)


def item(url, hours_ago=None, title="t"):
    r = {"url": url, "title": title, "content": "some  text\nhere"}
    if hours_ago is not None:
        r["published_date"] = rfc(hours_ago)
    return r


class FakeProvider:
    def __init__(self, by_days: dict[int, list[dict]]):
        self.by_days = by_days
        self.calls: list[int] = []

    def search_news(self, query, days, max_results):
        self.calls.append(days)
        return self.by_days.get(days, [])


def test_recent_items_no_fallback():
    p = FakeProvider({2: [item("https://www.a.com/1", 5), item("https://b.com/2", 30)]})
    r = search_news("Acme", p, now=NOW)
    assert p.calls == [2]
    assert r.searched_windows == ["48h"] and not r.used_fallback
    assert [i.window for i in r.items] == [WINDOW_48H, WINDOW_48H]
    assert r.items[0].outlet == "a.com"
    assert r.items[0].snippet == "some text here"


def test_fallback_to_30_days_when_48h_has_no_dated_recent_items():
    # days=2 is not strict: a 3-day-old item and an undated one come back. Neither counts as recent.
    p = FakeProvider({2: [item("https://a.com/old", 72), item("https://a.com/nodate")],
                      30: [item("https://a.com/older", 24 * 10), item("https://a.com/old", 72)]})
    r = search_news("Acme", p, now=NOW)
    assert p.calls == [2, 30]
    assert r.used_fallback
    windows = {i.url: i.window for i in r.items}
    assert windows == {"https://a.com/old": WINDOW_30D, "https://a.com/older": WINDOW_30D,
                       "https://a.com/nodate": WINDOW_UNKNOWN}  # deduplicated
    assert [i.url for i in r.items][-1] == "https://a.com/nodate"   # unknown dates last
    assert [i.url for i in r.items][0] == "https://a.com/old"       # newest first


def test_null_dates_kept_never_invented():
    p = FakeProvider({2: [item("https://a.com/x")], 30: []})
    r = search_news("Acme", p, now=NOW)
    assert len(r.items) == 1
    assert r.items[0].published_at is None and r.items[0].window == WINDOW_UNKNOWN


def test_items_older_than_30_days_dropped_and_limit_applied():
    p = FakeProvider({2: [item(f"https://a.com/{n}", n) for n in range(1, 9)] + [item("https://a.com/ancient", 24 * 40)]})
    r = search_news("Acme", p, max_results=3, now=NOW)
    assert [i.url for i in r.items] == ["https://a.com/1", "https://a.com/2", "https://a.com/3"]


def test_empty_everywhere():
    r = search_news("Acme", FakeProvider({}), now=NOW)
    assert r.items == [] and r.used_fallback


def test_parse_date_formats():
    assert parse_date("Tue, 03 Nov 2026 15:00:00 GMT") == datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
    assert parse_date("2026-11-03T15:00:00Z") == datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
    assert parse_date("yesterday") is None and parse_date(None) is None and parse_date("") is None


def test_future_date_treated_as_unknown():
    assert classify(NOW + timedelta(days=3), NOW) == WINDOW_UNKNOWN


def _provider(handler, **kw):
    return TavilyProvider(api_key="test-key", http=httpx.Client(transport=httpx.MockTransport(handler)),
                          sleep=lambda s: None, **kw)


def test_tavily_request_shape_and_usage():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = request.read()
        return httpx.Response(200, json={"results": [item("https://a.com/1", 1)]})

    p = _provider(handler)
    assert len(p.search_news("Acme", days=2, max_results=10)) == 1
    assert seen["auth"] == "Bearer test-key"
    assert b'"topic":"news"' in seen["body"].replace(b" ", b"")
    assert p.usage.requests == 1 and p.usage.credits == 1


@pytest.mark.parametrize("status,msg", [(401, "TAVILY_API_KEY"), (432, "credit limit"), (400, "400")])
def test_tavily_errors_surface_clearly(status, msg):
    p = _provider(lambda r: httpx.Response(status, json={}))
    with pytest.raises(NewsSearchError, match=msg):
        p.search_news("Acme", 2, 5)


def test_tavily_retries_429_then_succeeds():
    responses = iter([httpx.Response(429), httpx.Response(200, json={"results": []})])
    p = _provider(lambda r: next(responses))
    assert p.search_news("Acme", 2, 5) == []
    assert p.usage.requests == 2 and p.usage.credits == 1


def test_tavily_gives_up_after_repeated_5xx():
    p = _provider(lambda r: httpx.Response(503))
    with pytest.raises(NewsSearchError, match="503"):
        p.search_news("Acme", 2, 5)
