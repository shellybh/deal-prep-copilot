"""Single tool-calling briefing agent (Phase 2B): LangChain `create_agent` (runs on LangGraph) + Gemini (D7, D8).
`langgraph.prebuilt.create_react_agent` is deprecated in LangGraph 1.x in favor of `create_agent`.

Thin layer over project services: the tools call app.tools, the prompt lives in prompts.py.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.errors import GraphRecursionError

from app.agents import identify
from app.agents.identify import Identification, InvalidWebsite, parse_website
from app.agents.prompts import NUDGE_PROMPT, PROMPT_VERSION, system_prompt, user_prompt
from app.core.config import get_settings
from app.research.news import NewsSearchError

INTERNAL_TOOL = "search_internal_docs"
NEWS_TOOL = "search_live_news"
REQUIRED_TOOLS = (INTERNAL_TOOL, NEWS_TOOL)
RECURSION_BACKSTOP = 60  # LangGraph step limit; the model-call limit normally stops the loop first
LANGUAGES = ("en", "he")


class AgentError(RuntimeError):
    pass


class CompanyNotIdentified(AgentError):
    """No relevant web source and no internal mention: no briefing is written (Phase 3.5)."""

    def __init__(self, identification: Identification):
        self.identification = identification
        hint = ("check the website" if identification.domain
                else "run again with the company's website (--website)")
        super().__init__(f"company not identified: no relevant results for '{identification.company}'"
                         + (f" ({identification.domain})" if identification.domain else "") + f"; {hint}")


@dataclass
class SourceLog:
    """What the tools returned during one run: used for the CLI footer and later for persistence."""
    internal_citations: list[str] = field(default_factory=list)
    news_urls: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)

    def add_internal(self, citation: str) -> None:
        if citation not in self.internal_citations:
            self.internal_citations.append(citation)

    def add_news(self, url: str) -> None:
        if url not in self.news_urls:
            self.news_urls.append(url)


@dataclass
class BriefingResult:
    company: str
    language: str
    text: str
    model: str
    prompt_version: str
    tool_calls: list[str]
    sources: SourceLog
    duration_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    nudged: bool = False   # True if the agent skipped a required tool and had to be reminded
    website_domain: str | None = None
    identification: Identification | None = None


def make_tools(sources: SourceLog, k: int,
               internal_fn: Callable[..., list[dict]] | None = None,
               news_fn: Callable[..., dict] | None = None) -> list[BaseTool]:
    """Wrap app.tools functions as LangChain tools. Empty results become explicit 'missing' notes."""
    if internal_fn is None or news_fn is None:
        from app import tools as app_tools  # lazy: avoids DB/Tavily clients when tests inject fakes
        internal_fn = internal_fn or app_tools.search_internal_docs
        news_fn = news_fn or app_tools.search_live_news

    def search_internal_docs(query: str) -> str:
        """Search our internal knowledge base (battlecards, case studies, pricing, playbooks, product
        specs, CRM win/loss history). Input: a short English search query."""
        chunks = internal_fn(query, k=k)
        if not chunks:
            return (f"NO RESULTS in the internal knowledge base for '{query}'. "
                    "Report this under Missing information. Do not invent internal facts.")
        for c in chunks:
            sources.add_internal(c["citation"])
        return json.dumps([{"citation": c["citation"], "content": c["content"]} for c in chunks],
                          ensure_ascii=False)

    def search_live_news(company_name: str) -> str:
        """Get recent news about a company: last 48 hours first, widened to 30 days if there is none.
        Input: the company name."""
        try:
            result = news_fn(company_name)
        except NewsSearchError as exc:
            sources.tool_errors.append(f"{NEWS_TOOL}: {exc}")
            return (f"ERROR: the news search failed ({exc}). Report news as missing information "
                    "because the search failed, not because there is no news.")
        items = result.get("items") or []
        if not items:
            return (f"NO RESULTS: no news found for '{company_name}' in the last 30 days. Report recent news "
                    "as missing. This does not prove that nothing happened.")
        for item in items:
            sources.add_news(item["url"])
        return json.dumps(result, ensure_ascii=False)

    return [StructuredTool.from_function(search_internal_docs, name=INTERNAL_TOOL),
            StructuredTool.from_function(search_live_news, name=NEWS_TOOL)]


def build_llm(model: str | None = None) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI
    s = get_settings()
    return ChatGoogleGenerativeAI(model=model or s.chat_model, google_api_key=s.required_gemini_key(),
                                  temperature=0.2, max_retries=s.llm_max_retries)


def _tool_calls(messages: list[BaseMessage]) -> list[str]:
    return [tc["name"] for m in messages if isinstance(m, AIMessage) for tc in (m.tool_calls or [])]


def _final_text(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not m.tool_calls:
            return (m.text if isinstance(m.text, str) else m.text()).strip()
    return ""


def run_briefing(company: str, language: str = "en", k: int = 5, website: str | None = None,
                 llm: BaseChatModel | None = None, tools: list[BaseTool] | None = None,
                 sources: SourceLog | None = None, max_model_calls: int | None = None,
                 identify_fn: Callable[[str, str | None], Identification] | None = None) -> BriefingResult:
    """`website` is optional (URL or bare domain). The company is identified first; if it can't be,
    `CompanyNotIdentified` is raised and no LLM call is made."""
    company = company.strip()
    if not company:
        raise AgentError("company name is empty")
    if language not in LANGUAGES:
        raise AgentError(f"unsupported language '{language}' (use one of: {', '.join(LANGUAGES)})")
    try:
        domain = parse_website(website)
    except InvalidWebsite as exc:
        raise AgentError(str(exc)) from exc
    started = time.perf_counter()
    identification = (identify_fn or identify.identify_company)(company, domain)
    if identification.identified is False:
        raise CompanyNotIdentified(identification)

    s = get_settings()
    sources = sources if sources is not None else SourceLog()
    llm = llm or build_llm()
    tools = tools or make_tools(sources, k=k)
    limit = max_model_calls or s.agent_max_model_calls
    agent = create_agent(llm, tools, system_prompt=system_prompt(language),
                         middleware=[ModelCallLimitMiddleware(run_limit=limit, exit_behavior="error")])
    config = {"recursion_limit": RECURSION_BACKSTOP}

    messages: list[BaseMessage] = [HumanMessage(user_prompt(company, domain))]
    nudged = False
    try:
        messages = agent.invoke({"messages": messages}, config=config)["messages"]
        missing = [t for t in REQUIRED_TOOLS if t not in _tool_calls(messages)]
        if missing:  # the prompt says MUST; enforce it once, still bounded
            nudged = True
            nudge = HumanMessage(NUDGE_PROMPT.format(missing=" and ".join(missing), company=company))
            messages = agent.invoke({"messages": messages + [nudge]}, config=config)["messages"]
    except (ModelCallLimitExceededError, GraphRecursionError) as exc:
        raise AgentError(f"the agent hit the step limit ({limit} model calls) without finishing") from exc

    text = _final_text(messages)
    if not text:
        raise AgentError("the model returned an empty briefing")
    usage = [m.usage_metadata for m in messages if isinstance(m, AIMessage) and m.usage_metadata]
    return BriefingResult(
        company=company, language=language, text=text,
        model=getattr(llm, "model", None) or getattr(llm, "model_name", None) or type(llm).__name__,
        prompt_version=PROMPT_VERSION, tool_calls=_tool_calls(messages), sources=sources,
        duration_s=time.perf_counter() - started,
        input_tokens=sum(u.get("input_tokens", 0) for u in usage),
        output_tokens=sum(u.get("output_tokens", 0) for u in usage),
        nudged=nudged, website_domain=domain, identification=identification)
