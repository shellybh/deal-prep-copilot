"""Agent tools (D33; Phase 3 tools for the Research Agent, D36).
Plain functions returning citation-ready dicts. app/agents/briefing.py wraps them as LangChain tools.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.db.clients import get_admin_client
from app.rag.embeddings import GeminiEmbedder
from app.rag.retrieval import retrieve
from app.research.news import TavilyProvider, search_news
from app.research.provider import default_cache
from app.research.service import ExternalResearchService

DEFAULT_K = 5
COMPANY_INFO_PURPOSES = {"profile", "financial", "people", "press", "israel", "preferred"}
COMPETITOR_PURPOSES = {"competitors"}


@lru_cache
def news_provider() -> TavilyProvider:
    """Shared provider so its usage counter covers the whole process (also used by Phase 3 tools)."""
    return TavilyProvider(cache=default_cache())


@lru_cache
def research_service() -> ExternalResearchService:
    return ExternalResearchService(news_provider())


@lru_cache
def _embedder() -> GeminiEmbedder:
    return GeminiEmbedder()


def search_internal_docs(query: str, k: int = DEFAULT_K) -> list[dict]:
    """Search our internal knowledge base (battlecards, case studies, pricing, playbooks, product
    specs, CRM win/loss history). Returns the top-k chunks with a citation for each.
    Empty list = nothing relevant found."""
    chunks = retrieve(get_admin_client(), _embedder(), query, k=k)
    return [{
        "citation": c.citation,
        "file_name": c.file_name,
        "section": c.section,
        "document_id": c.document_id,
        "version": c.version,
        "score": round(c.score, 4),
        "content": c.content,
    } for c in chunks]


def search_live_news(company_name: str, max_results: int | None = None) -> dict:
    """Recent news about a company from Tavily: last 48 hours first, widened to 30 days if empty.
    Each item has title, url, outlet, published_at (ISO or None, never invented), snippet and window
    (last_48h | last_30_days | date_unknown)."""
    limit = max_results or get_settings().news_max_results
    return search_news(company_name, news_provider(), max_results=limit).to_dict()


def search_company_info(company_name: str, country: str | None = None, website: str | None = None,
                        depth: str | None = None) -> dict:
    """Public web information about a company: overview, products, financials (with period), leadership,
    press releases, Israeli activity. Hebrew + English per D37. Each source has url, outlet, published_at
    (or None), source_type and credibility tier (1 = official ... 4 = other)."""
    return research_service().research_company(
        company_name, country=country, website=website, depth=depth or get_settings().research_depth,
        purposes=COMPANY_INFO_PURPOSES, extract=False).to_dict()


def search_competitors(company_name: str, country: str | None = None, depth: str | None = None) -> dict:
    """Web sources about a company's competitors, alternatives and market position. Every claimed
    advantage must come from a returned source."""
    return research_service().research_company(
        company_name, country=country, depth=depth or get_settings().research_depth,
        purposes=COMPETITOR_PURPOSES, extract=False).to_dict()


def fetch_page(url: str) -> dict:
    """Main text of one web page (truncated). Use for the few most important sources only."""
    return research_service().fetch_pages([url])
