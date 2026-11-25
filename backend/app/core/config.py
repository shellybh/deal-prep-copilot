"""Settings loaded from the repo-root .env (D5). Fails fast on missing values and never exposes secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")

REQUIRED = ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_ANON_KEY")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    # repr=False keeps secrets out of logs, tracebacks and print(settings).
    supabase_key: str = field(repr=False)
    supabase_anon_key: str = field(repr=False)
    frontend_url: str = "http://localhost:5173"
    log_level: str = "INFO"
    # Gemini (D7, D9). Optional at startup; required_gemini_key() fails fast where it's needed.
    gemini_api_key: str = field(default="", repr=False)
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1536
    # Chunking (D13): "markdown" (headings, then 1000/100) won the Phase 2A eval; "fixed" = baseline 500/50.
    chunking_strategy: str = "markdown"
    chunk_size: int = 500
    chunk_overlap: int = 50
    # Chat models (D7). Free-tier IDs checked 2026-11-06; override in .env if Google retires them.
    chat_model: str = "gemini-3.5-flash"
    chat_model_small: str = "gemini-3.5-flash-lite"
    llm_max_retries: int = 6          # google-genai SDK retries 429/5xx; not for the orchestrator's strong model (D41)
    # Tavily news (D1, Phase 2B)
    tavily_api_key: str = field(default="", repr=False)
    news_max_results: int = 5
    # External research (Phase 3, D37). Cache only for eval/tests: re-runs cost no Tavily credits.
    tavily_cache_dir: str = ""
    research_depth: str = "standard"
    agent_max_model_calls: int = 6    # per agent run: tool rounds + final answer
    # Phase 4 model per role (D7, D41): the Research Agent's tool loop runs on the small model so the strong
    # model's free-tier quota (20 requests/day) covers ~10 runs; analysis + writing stay on the strong one.
    research_model_tier: str = "small"
    # KB management (Phase 2C, D35) + job runner (D14, D18)
    kb_bucket: str = "kb-documents"
    kb_max_upload_mb: int = 20
    kb_max_chunks: int = 500
    worker_enabled: bool = True       # start the job worker with the API (uvicorn)
    worker_poll_seconds: float = 2.0
    ingest_concurrency: int = 1
    job_stale_seconds: int = 300      # running job without heartbeat this long = worker died

    def required_tavily_key(self) -> str:
        if not self.tavily_api_key:
            raise ConfigError("Missing environment variable in .env: TAVILY_API_KEY")
        return self.tavily_api_key

    def required_gemini_key(self) -> str:
        if not self.gemini_api_key:
            raise ConfigError("Missing environment variable in .env: GEMINI_API_KEY")
        return self.gemini_api_key


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _tier_env(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip().lower() or default
    if raw not in ("strong", "small"):
        raise ConfigError(f"{name} must be 'strong' or 'small'")
    return raw


@lru_cache
def get_settings() -> Settings:
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        raise ConfigError(f"Missing environment variables in .env: {', '.join(missing)}")
    return Settings(
        supabase_url=os.environ["SUPABASE_URL"].strip(),
        supabase_key=os.environ["SUPABASE_KEY"].strip(),
        supabase_anon_key=os.environ["SUPABASE_ANON_KEY"].strip(),
        frontend_url=os.getenv("FRONTEND_URL", "http://localhost:5173").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip(),
        embedding_dim=_int_env("EMBEDDING_DIM", 1536),
        chunking_strategy=os.getenv("CHUNKING_STRATEGY", "markdown").strip().lower(),
        chunk_size=_int_env("CHUNK_SIZE", 500),
        chunk_overlap=_int_env("CHUNK_OVERLAP", 50),
        chat_model=os.getenv("CHAT_MODEL", "gemini-3.5-flash").strip(),
        chat_model_small=os.getenv("CHAT_MODEL_SMALL", "gemini-3.5-flash-lite").strip(),
        llm_max_retries=_int_env("LLM_MAX_RETRIES", 6),
        tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
        news_max_results=_int_env("NEWS_MAX_RESULTS", 5),
        tavily_cache_dir=os.getenv("TAVILY_CACHE_DIR", "").strip(),
        research_depth=os.getenv("RESEARCH_DEPTH", "standard").strip().lower(),
        agent_max_model_calls=_int_env("AGENT_MAX_MODEL_CALLS", 6),
        research_model_tier=_tier_env("RESEARCH_MODEL_TIER", "small"),
        kb_max_upload_mb=_int_env("KB_MAX_UPLOAD_MB", 20),
        kb_max_chunks=_int_env("KB_MAX_CHUNKS", 500),
        worker_enabled=os.getenv("WORKER_ENABLED", "true").strip().lower() not in ("0", "false", "no"),
        ingest_concurrency=_int_env("INGEST_CONCURRENCY", 1),
    )


# ---------- demo mode (Phase 6, D39 §2) ----------
@dataclass(frozen=True)
class DemoSettings:
    """Live research runs on the public demo: an access code + a site-wide daily cap.
    Fail closed: demo mode is on unless DEMO_MODE is explicitly off (local development only)."""
    mode: bool
    access_code: str = field(default="", repr=False)
    daily_cap: int = 4      # each run ~2 flash calls; the free tier allows 20 per model per day (D41)


def demo_settings() -> DemoSettings:
    """Read on every call (not cached): cheap, and the Streamlit app may set env vars from st.secrets."""
    mode = os.getenv("DEMO_MODE", "on").strip().lower() not in ("0", "off", "false", "no")
    return DemoSettings(mode=mode, access_code=os.getenv("DEMO_ACCESS_CODE", "").strip(),
                        daily_cap=max(0, _int_env("DEMO_DAILY_CAP", 4)))
