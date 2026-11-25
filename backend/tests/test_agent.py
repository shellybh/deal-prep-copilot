"""Briefing agent + CLI with a scripted fake LLM and fake tools (no network)."""
from __future__ import annotations

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import agent as cli
from app.agents.briefing import AgentError, SourceLog, make_tools, run_briefing
from app.agents.prompts import system_prompt
from app.core.config import ConfigError
from app.research.news import NewsSearchError
from app.agents import identify
from app.agents.identify import Identification


@pytest.fixture(autouse=True)
def identified(monkeypatch):
    """No network: every company counts as identified unless a test says otherwise."""
    monkeypatch.setattr(identify, "identify_company",
                        lambda company, domain=None: Identification(company, domain, True, via="web", web_sources=1))


class ScriptedLLM(BaseChatModel):
    """Returns the scripted AIMessages in order and records the messages it was given."""
    script: list
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        msg = self.script.pop(0) if self.script else AIMessage(content="loop")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def call(name, args, id_):
    return {"name": name, "args": args, "id": id_, "type": "tool_call"}


CHUNK = {"citation": "battlecard.md § Pricing", "content": "We are cheaper."}
NEWS = {"company": "Acme", "items": [{"url": "https://n.com/1", "title": "Acme raises", "window": "last_48h"}]}


def fake_tools(sources, internal=None, news=None, k=5):
    return make_tools(sources, k=k,
                      internal_fn=internal or (lambda q, k: [CHUNK]),
                      news_fn=news or (lambda c: NEWS))


def test_both_tools_called_and_sources_logged():
    llm = ScriptedLLM(script=[
        AIMessage(content="", tool_calls=[call("search_live_news", {"company_name": "Acme"}, "1"),
                                          call("search_internal_docs", {"query": "Acme"}, "2")]),
        AIMessage(content="# Deal-Prep Briefing: Acme\n..."),
    ])
    sources = SourceLog()
    r = run_briefing("Acme", llm=llm, tools=fake_tools(sources), sources=sources)
    assert set(r.tool_calls) == {"search_live_news", "search_internal_docs"}
    assert not r.nudged
    assert r.text.startswith("# Deal-Prep Briefing")
    assert sources.internal_citations == ["battlecard.md § Pricing"]
    assert sources.news_urls == ["https://n.com/1"]


def test_missing_tool_triggers_one_nudge():
    llm = ScriptedLLM(script=[
        AIMessage(content="", tool_calls=[call("search_internal_docs", {"query": "Acme"}, "1")]),
        AIMessage(content="draft without news"),
        AIMessage(content="", tool_calls=[call("search_live_news", {"company_name": "Acme"}, "2")]),
        AIMessage(content="final with news"),
    ])
    sources = SourceLog()
    r = run_briefing("Acme", llm=llm, tools=fake_tools(sources), sources=sources)
    assert r.nudged and r.text == "final with news"
    assert "search_live_news" in r.tool_calls


def test_recursion_bound_holds():
    looping = [AIMessage(content="", tool_calls=[call("search_internal_docs", {"query": "x"}, str(i))])
               for i in range(50)]
    sources = SourceLog()
    with pytest.raises(AgentError, match="step limit"):
        run_briefing("Acme", llm=ScriptedLLM(script=looping), tools=fake_tools(sources), sources=sources,
                     max_model_calls=4)


def test_empty_tool_results_become_missing_notes():
    sources = SourceLog()
    internal, news = fake_tools(sources, internal=lambda q, k: [], news=lambda c: {"items": []})
    assert "Missing information" in internal.invoke({"query": "Acme"})
    assert "missing" in news.invoke({"company_name": "Acme"}).lower()
    assert sources.internal_citations == [] and sources.news_urls == []


def test_news_api_error_is_reported_not_fatal():
    def boom(c):
        raise NewsSearchError("Tavily search failed (500).")
    sources = SourceLog()
    _, news = fake_tools(sources, news=boom)
    out = news.invoke({"company_name": "Acme"})
    assert out.startswith("ERROR") and "not because there is no news" in out
    assert sources.tool_errors == ["search_live_news: Tavily search failed (500)."]


def test_k_is_passed_to_internal_search():
    seen = {}

    def internal(q, k):
        seen["k"] = k
        return [CHUNK]
    internal_tool, _ = fake_tools(SourceLog(), internal=internal, k=8)
    internal_tool.invoke({"query": "Acme"})
    assert seen["k"] == 8


def test_language_in_system_prompt_and_validation():
    assert "Write the whole briefing in Hebrew" in system_prompt("he")
    with pytest.raises(AgentError, match="unsupported language"):
        run_briefing("Acme", language="fr", llm=ScriptedLLM(script=[]), tools=[])
    with pytest.raises(AgentError, match="empty"):
        run_briefing("  ", llm=ScriptedLLM(script=[]), tools=[])


# ---- CLI ----

def test_cli_args_defaults_and_validation():
    a = cli.parse_args(["--company", "Acme"])
    assert (a.company, a.language, a.k) == ("Acme", "en", 5)
    a = cli.parse_args(["--company", "Acme", "--language", "he", "--k", "8"])
    assert (a.language, a.k) == ("he", 8)
    for bad in (["--language", "en"], ["--company", "Acme", "--language", "fr"],
                ["--company", "Acme", "--k", "0"], ["--company", "  "]):
        with pytest.raises(SystemExit) as e:
            cli.parse_args(bad)
        assert e.value.code == 2


def test_cli_missing_key_exits_nonzero(monkeypatch, capsys):
    class S:
        chat_model = "x"

        def required_gemini_key(self):
            return "k"

        def required_tavily_key(self):
            raise ConfigError("Missing environment variable in .env: TAVILY_API_KEY")
    monkeypatch.setattr(cli, "get_settings", lambda: S())
    assert cli.main(["--company", "Acme", "--single"]) == 2
    assert "TAVILY_API_KEY" in capsys.readouterr().err


def test_cli_success_prints_briefing_and_footer(monkeypatch, capsys):
    from app.agents.briefing import BriefingResult
    sources = SourceLog(internal_citations=["a.md § X"], news_urls=["https://n.com/1", "https://n.com/2"])
    result = BriefingResult(company="Acme", language="en", text="# Briefing", model="m", prompt_version="v1",
                            tool_calls=["search_live_news", "search_internal_docs", "search_internal_docs"],
                            sources=sources, duration_s=1.5)

    class S:
        chat_model = "m"

        def required_gemini_key(self):
            return "k"

        def required_tavily_key(self):
            return "k"
    monkeypatch.setattr(cli, "get_settings", lambda: S())
    monkeypatch.setattr(cli, "run_briefing", lambda *a, **kw: result)
    assert cli.main(["--company", "Acme", "--single"]) == 0
    out = capsys.readouterr().out
    assert "# Briefing" in out
    assert "search_internal_docs x2" in out and "1 internal, 2 news" in out


def test_cli_agent_error_exits_1(monkeypatch, capsys):
    class S:
        chat_model = "m"

        def required_gemini_key(self):
            return "k"

        def required_tavily_key(self):
            return "k"

    def fail(*a, **kw):
        raise AgentError("the agent hit the step limit (6 model calls) without finishing")
    monkeypatch.setattr(cli, "get_settings", lambda: S())
    monkeypatch.setattr(cli, "run_briefing", fail)
    assert cli.main(["--company", "Acme", "--single"]) == 1
    assert "step limit" in capsys.readouterr().err
