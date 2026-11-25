"""Phase 3.5: company identification, optional website, prompt v3 rules (no network)."""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import agent as cli
from app.agents.briefing import AgentError, BriefingResult, CompanyNotIdentified, SourceLog, run_briefing
from app.agents.identify import Identification, InvalidWebsite, identify_company, parse_website
from app.agents.prompts import PROMPT_VERSION, system_prompt, user_prompt
from app.research.provider import FatalSearchError, SearchError
from tests.test_agent import ScriptedLLM, call, fake_tools


# ---- website parsing ----

@pytest.mark.parametrize("raw, domain", [
    ("monday.com", "monday.com"),
    ("https://www.monday.com/pricing?x=1", "monday.com"),
    ("HTTP://Snowflake.COM", "snowflake.com"),
    ("calcalist.co.il", "calcalist.co.il"),
    (None, None), ("  ", None),
])
def test_parse_website_ok(raw, domain):
    assert parse_website(raw) == domain


@pytest.mark.parametrize("raw", ["not a url", "ftp://monday.com", "monday", "https://", "localhost", "a b.com",
                                 "mailto:x@y.com"])
def test_parse_website_rejects(raw):
    with pytest.raises(InvalidWebsite):
        parse_website(raw)


# ---- identify_company ----

WEB_HIT = {"sources": [{"url": "https://acme.com/about"}, {"url": "https://news.com/acme"}], "credits_used": 1}
WEB_EMPTY = {"sources": [], "credits_used": 1}


def test_identified_on_web_skips_internal():
    def internal(q, k):
        raise AssertionError("internal check should not run")
    r = identify_company("Acme", "acme.com", web_fn=lambda c, d: WEB_HIT, internal_fn=internal)
    assert (r.identified, r.via, r.web_sources, r.credits_used) == (True, "web", 2, 1)
    assert r.evidence[0] == "https://acme.com/about"


def test_domain_reaches_web_search():
    seen = {}

    def web(c, d):
        seen["args"] = (c, d)
        return WEB_HIT
    identify_company("Acme", "acme.com", web_fn=web, internal_fn=lambda q, k: [])
    assert seen["args"] == ("Acme", "acme.com")


def test_internal_kb_mention_identifies_kb_only_company():
    chunks = [{"citation": "battlecard_quantalake.md § Snapshot", "content": "QuantaLake is an open-source lakehouse"},
              {"citation": "pricing.md § Tiers", "content": "Starter tier $1,200"}]
    r = identify_company("QuantaLake", web_fn=lambda c, d: WEB_EMPTY, internal_fn=lambda q, k: chunks)
    assert (r.identified, r.via, r.internal_mentions) == (True, "internal", 1)
    assert r.evidence == ["battlecard_quantalake.md § Snapshot"]


def test_fictional_company_not_identified():
    chunks = [{"citation": "pricing.md § Tiers", "content": "Starter tier $1,200"}]   # unrelated nearest chunk
    r = identify_company("Zorbex Dynamics", web_fn=lambda c, d: WEB_EMPTY, internal_fn=lambda q, k: chunks)
    assert r.identified is False and r.via is None and r.summary() == "not identified"


def test_search_error_is_undecided_not_blocking():
    def web(c, d):
        raise SearchError("All external searches failed: 500")
    r = identify_company("Acme", web_fn=web, internal_fn=lambda q, k: [])
    assert r.identified is None and "500" in r.error


def test_fatal_search_error_propagates():
    def web(c, d):
        raise FatalSearchError("Tavily rejected the API key (401)")
    with pytest.raises(FatalSearchError):
        identify_company("Acme", web_fn=web, internal_fn=lambda q, k: [])


# ---- run_briefing ----

def briefing_llm():
    return ScriptedLLM(script=[
        AIMessage(content="", tool_calls=[call("search_live_news", {"company_name": "Acme"}, "1"),
                                          call("search_internal_docs", {"query": "Acme"}, "2")]),
        AIMessage(content="# Deal-Prep Briefing: Acme"),
    ], seen=[])


def test_not_identified_stops_before_any_llm_call():
    llm = ScriptedLLM(script=[], seen=[])
    with pytest.raises(CompanyNotIdentified, match="--website") as e:
        run_briefing("Zorbex", llm=llm, tools=fake_tools(SourceLog()),
                     identify_fn=lambda c, d: Identification(c, d, False))
    assert llm.seen == [] and e.value.identification.company == "Zorbex"
    assert isinstance(e.value, AgentError)


def test_website_normalized_passed_to_identification_and_prompt():
    seen = {}

    def ident(c, d):
        seen["domain"] = d
        return Identification(c, d, True, via="web", web_sources=3)
    llm = briefing_llm()
    sources = SourceLog()
    r = run_briefing("Acme", website="https://www.acme.com/x", llm=llm, tools=fake_tools(sources),
                     sources=sources, identify_fn=ident)
    assert seen["domain"] == "acme.com" and r.website_domain == "acme.com"
    first_human = next(m for m in llm.seen[0] if isinstance(m, HumanMessage))
    assert "website is acme.com" in first_human.content
    assert r.identification.via == "web" and r.prompt_version == PROMPT_VERSION


def test_undecided_identification_continues():
    r = run_briefing("Acme", llm=briefing_llm(), tools=fake_tools(SourceLog()),
                     identify_fn=lambda c, d: Identification(c, d, None, error="500"))
    assert r.text.startswith("# Deal-Prep Briefing") and "check failed" in r.identification.summary()


def test_invalid_website_rejected_before_identification():
    def ident(c, d):
        raise AssertionError("should not run")
    with pytest.raises(AgentError, match="not a website"):
        run_briefing("Acme", website="not a url", llm=ScriptedLLM(script=[], seen=[]), tools=[], identify_fn=ident)


# ---- prompt v3 ----

def test_prompt_v3_grounding_rules():
    assert PROMPT_VERSION.endswith("/v3")
    p = system_prompt("en")
    assert "The tech market is volatile" in p and "Never write generic market" in p
    assert "Missing information" in p and "standard price list" in p
    assert user_prompt("Acme") == "Prepare a deal-prep briefing about the company: Acme"
    assert "website is acme.com" in user_prompt("Acme", "acme.com")


# ---- CLI ----

class _S:
    chat_model = "m"

    def required_gemini_key(self):
        return "k"

    def required_tavily_key(self):
        return "k"


def _result(**kw) -> BriefingResult:
    return BriefingResult(company="Acme", language="en", text="# B", model="m", prompt_version="v3",
                          tool_calls=[], sources=SourceLog(), duration_s=1.0, **kw)


def test_cli_website_flag_and_validation():
    assert cli.parse_args(["--company", "Acme"]).website is None
    assert cli.parse_args(["--company", "Acme", "--website", "acme.com"]).website == "acme.com"
    with pytest.raises(SystemExit) as e:
        cli.parse_args(["--company", "Acme", "--website", "not a url"])
    assert e.value.code == 2


def test_cli_passes_website_and_shows_it_in_footer(monkeypatch, capsys):
    seen = {}

    def fake_run(company, **kw):
        seen.update(kw)
        return _result(website_domain="acme.com",
                       identification=Identification(company, "acme.com", True, via="web", web_sources=2))
    monkeypatch.setattr(cli, "get_settings", lambda: _S())
    monkeypatch.setattr(cli, "run_briefing", fake_run)
    assert cli.main(["--company", "Acme", "--website", "https://acme.com", "--single"]) == 0
    out = capsys.readouterr().out
    assert seen["website"] == "https://acme.com"
    assert "Website: acme.com" in out and "identified on the web (2 relevant sources)" in out


def test_cli_footer_website_not_provided(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: _S())
    monkeypatch.setattr(cli, "run_briefing", lambda *a, **kw: _result())
    assert cli.main(["--company", "Acme", "--single"]) == 0
    assert "Website: not provided" in capsys.readouterr().out


def test_cli_not_identified_exit_code(monkeypatch, capsys):
    def fail(*a, **kw):
        raise CompanyNotIdentified(Identification("Zorbex", None, False))
    monkeypatch.setattr(cli, "get_settings", lambda: _S())
    monkeypatch.setattr(cli, "run_briefing", fail)
    assert cli.main(["--company", "Zorbex", "--single"]) == cli.EXIT_NOT_IDENTIFIED == 3
    captured = capsys.readouterr()
    assert "NOT IDENTIFIED" in captured.err and "--website" in captured.err and captured.out == ""


# ---- official domain inferred when no website is given (2026-11-16, Elbit run: elbitsystems.com was tier 4) ----

from app.agents.identify import infer_official_domain  # noqa: E402


@pytest.mark.parametrize("company, urls, domain", [
    ("elbit", ["https://he.wikipedia.org/wiki/x", "https://www.elbitsystems.com/business-overview",
               "https://elbitsystems.com/he"], "elbitsystems.com"),
    ("Elbit Systems", ["https://investors.elbitsystems.com/q3"], "elbitsystems.com"),
    ("Snowflake", ["https://www.snowflake.com/en/"], "snowflake.com"),
    ("Siemens AG", ["https://www.siemens.com/global"], "siemens.com"),
    ("monday.com", ["https://monday.com/p/about"], "monday.com"),
    ("Bank Hapoalim", ["https://www.bankhapoalim.co.il/he"], "bankhapoalim.co.il"),
])
def test_infer_official_domain(company, urls, domain):
    assert infer_official_domain(company, urls) == domain


@pytest.mark.parametrize("company, urls", [
    ("Siemens", ["https://www.siemens-energy.com/x"]),           # a different company
    ("monday", ["https://mondaymagazine.com/a"]),                 # unknown suffix
    ("elbit", ["https://he.wikipedia.org/wiki/x", "https://calcalistech.com/elbit"]),
    ("אלביט", ["https://www.elbitsystems.com/he"]),               # non-Latin name: no guess
    ("HP", ["https://hp.com"]),                                   # too short to match safely
    ("elbit", [None, ""]),
])
def test_infer_official_domain_no_match(company, urls):
    assert infer_official_domain(company, urls) is None


def test_identify_infers_domain_only_without_website():
    web = {"sources": [{"url": "https://www.acme.com/about"}, {"url": "https://news.com/acme"}], "credits_used": 1}
    r = identify_company("Acme", None, web_fn=lambda c, d: web, internal_fn=lambda q, k: [])
    assert (r.domain, r.domain_inferred) == ("acme.com", True)
    assert r.summary().endswith("official site: acme.com")
    given = identify_company("Acme", "acme.org", web_fn=lambda c, d: web, internal_fn=lambda q, k: [])
    assert (given.domain, given.domain_inferred) == ("acme.org", False)
    none = identify_company("Acme", None, web_fn=lambda c, d: {"sources": [{"url": "https://news.com/acme"}]},
                            internal_fn=lambda q, k: [])
    assert (none.domain, none.domain_inferred) == (None, False)
