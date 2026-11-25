"""LLM access for the Phase 4 agents (D7): two model tiers from config, token logging per call, structured output.

Rate limits: the google-genai SDK retries 429 / 5xx with exponential backoff (`LLM_MAX_RETRIES`). Stage-level
retries (orchestrator) sit on top of that for invalid structured output and other transient failures.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger(__name__)
Tier = Literal["strong", "small"]
T = TypeVar("T", bound=BaseModel)


class LLMOutputError(RuntimeError):
    """The model answered, but not in the expected structure."""


# Free tier (found 2026-11-09): gemini-3.5-flash allows 20 requests per day per model. A 429 for a daily
# quota won't clear with retries, so stages fail at once with this message instead of retrying.
DAILY_QUOTA_MSG = "Gemini daily free-tier quota reached for this model (resets within 24 h)"


def is_daily_quota(exc: BaseException) -> bool:
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text and "PerDay" in text


def is_overloaded(text: str) -> bool:
    """Google-side overload ("503 UNAVAILABLE ... high demand"), not a quota or request error."""
    return "503" in text and "UNAVAILABLE" in text


def build_chat_model(tier: Tier = "strong", temperature: float = 0.2,
                     max_retries: int | None = None) -> BaseChatModel:
    """`max_retries` = attempts inside the google-genai SDK (it retries 408/429/5xx silently, and every attempt,
    rejected ones included, counts toward the free-tier daily quota). Default: settings.llm_max_retries.
    1 = a single request, no hidden retries (the orchestrator's strong model, see Deps.strong)."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    s = get_settings()
    model = s.chat_model if tier == "strong" else s.chat_model_small
    return ChatGoogleGenerativeAI(model=model, google_api_key=s.required_gemini_key(), temperature=temperature,
                                  max_retries=max_retries or s.llm_max_retries)


def model_name(llm: BaseChatModel) -> str:
    return getattr(llm, "model", None) or getattr(llm, "model_name", None) or type(llm).__name__


@dataclass
class UsageEvent:
    kind: Literal["llm", "tavily"]
    agent: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    credits: int = 0


@dataclass
class UsageLog:
    """Per-run usage: one event per LLM call, one per research step for Tavily credits."""
    events: list[UsageEvent] = field(default_factory=list)

    def llm(self, agent: str, model: str, message: BaseMessage | None) -> None:
        meta = getattr(message, "usage_metadata", None) or {}
        self.events.append(UsageEvent("llm", agent, model, meta.get("input_tokens", 0), meta.get("output_tokens", 0)))

    def llm_messages(self, agent: str, model: str, messages: list[BaseMessage]) -> None:
        for m in messages:
            if isinstance(m, AIMessage) and m.usage_metadata:
                self.llm(agent, model, m)

    def tavily(self, agent: str, credits: int) -> None:
        if credits:
            self.events.append(UsageEvent("tavily", agent, credits=credits))

    def totals(self) -> dict:
        llm = [e for e in self.events if e.kind == "llm"]
        return {"llm_calls": len(llm), "input_tokens": sum(e.input_tokens for e in llm),
                "output_tokens": sum(e.output_tokens for e in llm),
                "tavily_credits": sum(e.credits for e in self.events if e.kind == "tavily")}

    def by_agent(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.events:
            a = out.setdefault(e.agent, {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "tavily_credits": 0})
            if e.kind == "llm":
                a["llm_calls"] += 1
                a["input_tokens"] += e.input_tokens
                a["output_tokens"] += e.output_tokens
            else:
                a["tavily_credits"] += e.credits
        return out


def structured_call(llm: BaseChatModel, schema: type[T], messages: list[BaseMessage], *, agent: str,
                    usage: UsageLog) -> T:
    """One call with structured output. Logs tokens even when parsing fails."""
    runnable = llm.with_structured_output(schema, include_raw=True)
    out = runnable.invoke(messages)
    raw = out.get("raw") if isinstance(out, dict) else None
    usage.llm(agent, model_name(llm), raw)
    parsed = out.get("parsed") if isinstance(out, dict) else out
    if isinstance(parsed, dict):
        parsed = schema.model_validate(parsed)
    if not isinstance(parsed, schema):
        err = out.get("parsing_error") if isinstance(out, dict) else None
        raise LLMOutputError(f"{agent}: the model did not return a valid {schema.__name__}"
                             + (f" ({str(err)[:200]})" if err else ""))
    return parsed
