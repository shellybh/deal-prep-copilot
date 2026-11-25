# Deal-Prep Copilot – Decision Log

*Written during development. "The brief" means the original product brief the project started from (not included in this repo).*

Status values (D6–D30 approved by the user on 2026-11-05): **Approved** (decided by the user), **Proposed** (recommendation waiting for approval), **Open** (not yet analyzed or needs input).
Cost figures are rough estimates for a small MVP. Verify current prices on the provider pricing pages before approving anything that costs money.

## Summary

| ID | Topic | Status | Recommendation / decision |
|---|---|---|---|
| D1 | Web search | Approved | Tavily only (news topic + time range). No GDELT in MVP. |
| D2 | Search engine | Approved | Supabase PostgreSQL + pgvector for vector and keyword search. |
| D3 | Document formats | Approved | PDF, DOCX, TXT, MD, CSV. |
| D4 | CRM CSV | Approved | Ingested as a regular KB document. Original kept in Storage. ML prediction = optional later. |
| D5 | Python environment | Approved | `venv` + pinned `requirements.txt`, `.env` via `python-dotenv`. |
| D6 | Frontend framework | Approved, **amended by D39** | React + Vite + TypeScript SPA. *Since D39: Streamlit is the only UI; the React skeleton stays unused.* |
| D7 | LLM provider and models | Approved | **Google Gemini (free tier, AI Studio)**, two model tiers set in config. Code stays provider-agnostic. |
| D8 | Agent framework + text splitting | Approved | LangGraph + `langchain-text-splitters` |
| D9 | Embedding model | Approved | **Gemini `gemini-embedding-001` at 1536 dims** → `vector(1536)` |
| D10 | Keyword search | Approved | Postgres FTS, `simple` config, `ts_rank_cd` (accepted as "BM25-like") |
| D11 | Hybrid ranking | Approved | Reciprocal Rank Fusion (k = 60) in a SQL function |
| D12 | Reranking | Approved | Deferred. Interface only. |
| D13 | Document processing | Approved | `pypdf`, `python-docx`, stdlib for TXT/MD/CSV. Default chunks 500 chars / 50 overlap, Markdown-aware chunking evaluated as alternative. CSV = groups of 10 rows with header. |
| D14 | Background jobs | Approved | DB-backed job table + async worker inside the backend process |
| D15 | Hosting | Approved, **amended by D39** | Local for development. Demo: **Vercel (frontend) + Hugging Face Spaces Docker (backend)**, both free. *Since D39: Streamlit Community Cloud.* |
| D16 | PDF generation | Approved | HTML/CSS templates → PDF with headless Chromium (Playwright) |
| D17 | Research depth parameters | Approved | Table in D17 as proposed |
| D18 | Concurrency limit | Approved | **1 run system-wide**, rest queued (configurable) |
| D19 | Default usage quotas | Approved | **30 runs/user/month**, soft limit, warning at 80% |
| D20 | Organization profile process | Approved | Admin owns it. Manual form + optional AI draft from KB. Review reminder after 90 days. |
| D21 | Source credibility rules | Approved | Rule-based source tiers + LLM evidence assessment + corroboration rule |
| D22 | Schema creation | Approved | **Supabase MCP connected to Claude Code** applies versioned SQL files from `supabase/migrations/` |
| D23 | Backend API framework *(not in , needed for Phase 1)* | Approved | FastAPI |
| D24 | Additional-context field | Approved | One free-text field with one classification (two context fields of the brief merged) |
| D25 | Progress stages | Approved | 7 stages: Company Identification + the 5 research / writing stages + Quality Checks |
| D27 | Admin view of reported claims | Approved | Admin can view the **full briefing** that contains a reported claim |
| D28 | Invites | Approved | Supabase built-in email + admin can copy an invite link as fallback |
| D29 | Rollback | Approved | Prompts versioned in code (rollback via git). Settings versioned in DB (rollback in admin UI). |
| D30 | Git | Approved, **amended by D38, D42** | Developed in a **private** GitHub repo. A public copy is published after a secret scan (D42). |
| D33 | Build order: working agent CLI first | Approved | **Vertical slice first:** Phase 2A (KB core + `search_internal_docs`) → 2B (`search_live_news`, minimal Tavily) → `agent.py` single-agent CLI → 2C (KB management) → full Phases 3–4. |
| D34 | Backend first, then frontend | Approved, **superseded by D38** (order) | **Middle path:** core (2B ✓, 2C, 3, 4) without UI, then the API parts of Phases 5–7, then all screens in one frontend block, then Phase 8. The existing frontend skeleton stays (bug fixes only until the frontend block). |
| D35 | KB upload limits + regular-user visibility | Approved | 20 MB, PDF/DOCX/TXT/MD/CSV checked by content, ~500 chunks max, scanned PDF → Failed (no OCR). Regular users: read-only list + search. |
| D37 | Tavily credit budget + search languages | Approved | Query caps per run (incl. extra rounds), In-depth uses basic search, per-run credit cap, cached responses in eval. Search in **Hebrew + English only**: Israel → He + En; other countries → En + one He query (all depths). Briefing shows the search languages. |
| D36 | Number of agents (MVP scope) | Approved | **Two agents:** Research Agent (Internal + Web + Competitive) and Analysis & Writing Agent (Analyst + Writer). Orchestrator = graph code. Contracts built so they can be split back into six (orchestrator + 5 specialists, as in the brief) later. |
| D38 | Portfolio MVP scope | Approved | **Minimal portfolio demo, not a full product.** Order: 3.5 grounding fix → 4-lite → Streamlit UI → demo mode + deploy → portfolio polish (public repo). Most of Phases 5–8 and the React frontend block move to "Future work". ML stays optional (not built). Amends D6, D15, D30, D34. |
| D39 | Streamlit UI + public demo mode + Streamlit Community Cloud | Approved | Streamlit is the only UI (amends D6). Public visitors see pre-generated sample briefings; live runs need an access code + a site-wide daily cap. Backend calls run server-side with keys in Streamlit Secrets. Hosting: Streamlit Community Cloud (amends D15). Supabase Auth not used by the UI. |
| D40 | Phase 4 open questions: completeness criteria, meeting-type tailoring, generic-statement check | Approved | Completeness = fixed criteria in code, no LLM call; extra rounds search only what was never queried. Tailoring = per-meeting-type config in code injected into one prompt per role. Generic statements = one small-model judge call in the quality checks. |
| D41 | Model per role after the free-tier daily quota finding | Approved | Research Agent on `gemini-3.5-flash-lite` (`RESEARCH_MODEL_TIER=small`), analysis + writing on `gemini-3.5-flash`, judge on flash-lite. ~2 strong calls per run instead of 6. Amends D7's task → tier table. |
| D32 | Phase 1 implementation details | Implemented | Python 3.12 venv at repo root, `requirements.txt` at root, backend in `backend/` (`db_setup.py` there), frontend in `frontend/`. Profile row created by a trigger on `auth.users` (role `user`). Role/`is_active` writable only by the backend. Invite redirect → `/set-password`. |

---

## Approved decisions

### D1 – Web search: Tavily only
- **Date:** 2026-11-05 · **Status:** Approved
- **Decision:** Tavily replaces SearXNG for web search and news (`TAVILY_API_KEY`). Tavily only for the MVP. Its news topic + time range covers the last-48-hours focus. GDELT is not used now. It may be added later behind the same `SearchProvider` interface.
- **Rationale:** Built for AI agents. One provider = less integration work.
- **Alternatives:** SearXNG (self-hosted, in the original brief), GDELT (free news/events, extra integration).

### D2 – Search engine: Supabase PostgreSQL + pgvector
- **Date:** 2026-11-05 · **Status:** Approved
- **Decision:** Vector search (pgvector) and keyword search (Postgres) both run in Supabase.
- **Rationale:** One database. No sync between systems on upload, replace and delete. RLS applies to search too.
- **Alternatives:** OpenSearch (in the original brief), a dedicated vector DB.

### D3 – Document formats
- **Date:** 2026-11-05 · **Status:** Approved
- **Decision:** PDF, DOCX, TXT, MD and CSV.
- **Rationale:** Sample KB is Markdown, CRM file is CSV.

### D4 – CRM CSV as a regular KB document
- **Date:** 2026-11-05 · **Status:** Approved
- **Decision:** `crm_historical_win_loss_data_2025_2026.csv` is ingested as a regular internal document. No CRM integration. The original file is kept in full in Storage. ML deal prediction is an optional extension after the MVP, only with approval ( item 1). Not planned in phases 1–8.
- **Rationale:** Keeps scope small without blocking the extension later.

### D5 – Python environment
- **Date:** 2026-11-05 · **Status:** Approved
- **Decision:** `venv` + `requirements.txt` with pinned versions. Secrets in `.env` (git-ignored) loaded with `python-dotenv`. `.env.example` placeholders only. `SUPABASE_KEY` = secret service_role key, backend only. `SUPABASE_ANON_KEY` = public key for the frontend and user-scoped calls.
- **Rationale:** Simplest option.
- **Alternatives:** Poetry, uv, conda.

---

## Decisions D6–D23 (approved 2026-11-05; options kept for reference)

### D6 – Frontend framework
- **Status:** Approved (2026-11-05)
- **Needs:** Full navigation, invite-only login, RTL Hebrew + English, structured briefing editor, progress polling, admin screens.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. React + Vite + TypeScript SPA** (recommended) | Full control of UI, RTL and editing. `supabase-js` handles login. Builds to static files, so free hosting. Clean split: all logic stays in the Python API. Strong portfolio value. | Second language (TypeScript) and a Node toolchain. More code than Streamlit. | Free (static hosting) |
| B. Next.js (React) | Same UI power. SSR, routing built in. First-class Vercel hosting. | Server components + SSR auth add complexity we don't need, since the backend is Python. Two servers. | Free tier on Vercel |
| C. Streamlit | Python only. Very fast to build. Common for AI demos. | Weak fit for multi-page app with roles, invite login, RTL editing and custom layouts. Session reruns make polling and editing awkward. Looks less like an enterprise product. | Free (Community Cloud) or same host as backend |

**Recommendation:** A. Streamlit is the fallback if time becomes the main constraint.

### D7 – LLM provider and models per task type
- **Status:** Approved (2026-11-05)
- **Context:** `.env.example` has `OPENAI_API_KEY` active and `ANTHROPIC_API_KEY` commented out. Only OpenAI is available now.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. OpenAI only, two tiers in config** (recommended) | Key already exists. One SDK, one billing account. Same provider as embeddings (D9). Structured outputs work well with Pydantic. | Single vendor. | Lowest setup. Roughly a few cents to ~$0.50 per run depending on depth and model (estimate, measured in Phase 4). |
| B. Anthropic (Claude) for analysis and writing, OpenAI for the rest | Strong long-form writing and analysis, good Hebrew. | Needs a new paid key (approval needed). Two SDKs and two billing accounts. | Extra account + per-token cost |
| C. Mixed per task, chosen after evaluation | Best quality/cost per task. | Needs both keys and an eval loop before choosing. More config. | Highest setup effort |

**Proposed task → tier mapping (Option A):**

| Task | Tier | Why |
|---|---|---|
| Orchestration (plan, completeness check) | Strong | Few calls, decisions matter |
| Research summarization (web results, RAG excerpts, company identification) | Small/cheap | Many calls, extraction-style work |
| Strategic analysis | Strong | Reasoning quality |
| Briefing writing (He/En) | Strong | Final quality, Hebrew fluency |
| Quality checks | Small/cheap | Rule-like checks |

Exact model IDs are set in config (not hard-coded) and picked in Phase 4 from OpenAI's current model list (e.g. a current "mini" model for the small tier and the current flagship for the strong tier). The LLM client is provider-agnostic, so Anthropic can be added later without touching agents.

**Recommendation (original):** A.

**Approved decision:** Google Gemini via Google AI Studio free tier (no credit card). The user prefers free services. Small tier = a current Gemini Flash-Lite/Flash model, strong tier = the strongest model available on the free tier. Exact model IDs live in config and are checked against Google's model list in Phase 4.
- Free-tier caveats: rate limits (hence D18 = 1). Google may use free-tier data to improve its products, so **only sample/synthetic data**, never real organization data.
- New env variable `GEMINI_API_KEY` (placeholder added to `.env.example`; the user adds the real key to `.env`).
- `OPENAI_API_KEY` stays in `.env.example`. The LLM client is provider-agnostic (LangChain chat models), so switching to OpenAI or Claude later is a config change.

### D8 – Agent framework / orchestration (+ text splitting)
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. LangGraph + `langchain-text-splitters`** (recommended) | Explicit graph: parallel branches (internal/web/competitive), bounded loop for extra research, shared typed state. Matches "controlled autonomy". Same family as `langchain-text-splitters`. Provider-agnostic chat models. Good portfolio keyword. | Learning curve. Extra dependencies. API changes between versions (pin versions, D5). | Free (open source). No LangSmith needed. |
| B. OpenAI Agents SDK | Simple agents + handoffs + tools. Light. | Tied to OpenAI. Less explicit control of graph, parallel stages and stage status. Splitting would need a second library. | Free |
| C. Custom orchestrator (asyncio + Pydantic + provider SDK) + small custom splitter | No framework lock-in. Full control. Fewest dependencies. | We write retries, parallelism, state and loop limits ourselves. | Free |

**Text splitting:** `langchain-text-splitters` (`MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter`) under Option A. A custom splitter is ~50 lines but needs its own tests. With A, splitting and agents stay in one library family.
**Recommendation:** A.

### D9 – Embedding model (Hebrew + English)
- **Status:** Approved (2026-11-05). **Must be approved before any vector table is created.** The choice fixes the column dimension. Changing it later = migration + re-embedding all documents.

| Option | Dims | Pros | Cons | Cost (approx.) |
|---|---|---|---|---|
| **A. OpenAI `text-embedding-3-large` with `dimensions=1536`** (recommended) | 1536 | Better multilingual (Hebrew) quality than 3-small. 1536 fits pgvector HNSW (limit 2,000 for `vector`). Same key as the LLM. | Paid API (small). | ~$0.13 / 1M tokens. The sample KB is far below 1M tokens → cents. |
| B. OpenAI `text-embedding-3-small` | 1536 | Cheapest. Most common in tutorials. | Weaker on Hebrew and cross-language queries. | ~$0.02 / 1M tokens |
| C. Open-source multilingual (e.g. `bge-m3`, `multilingual-e5-large`) | 1024 | Free per call. Strong multilingual. Data stays local. | Large download + PyTorch, slow on CPU, harder to host on a small server. | $0 API, but heavier hosting |

Note: A and B both use 1536, so switching between them later needs re-embedding but no column migration.
**Recommendation (original):** A → `embedding vector(1536)`, cosine distance, HNSW index.

**Approved decision:** Gemini `gemini-embedding-001` (free tier, same `GEMINI_API_KEY`) with `output_dimensionality = 1536` → `embedding vector(1536)`, cosine distance, HNSW index.
- Reduced-dimension vectors are L2-normalized before storage.
- Task type `RETRIEVAL_DOCUMENT` for chunks, `RETRIEVAL_QUERY` for queries.
- Ingestion embeds in batches with throttling for free-tier rate limits.
- Model name + dimension stored per chunk. Switching to OpenAI 1536-dim later = re-embed only, no column migration.

### D10 – Keyword search in Postgres
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. Built-in FTS: generated `tsvector` with `simple` config, GIN index, `websearch_to_tsquery`, `ts_rank_cd`** (recommended) | Built in, supported on Supabase, documented hybrid-search pattern. `simple` works for Hebrew and English (no stemming = exact names, products and IDs match well). | Not true BM25 (no IDF / length saturation). No Hebrew stemming or prefix handling (ה/ו/ב/ל/מ/ש). | Free |
| B. `english` config for English + `simple` for Hebrew (two tsvectors, chosen by detected language) | English stemming improves recall. | More complex. Language detection per chunk/query. Little gain for names/IDs, which is FTS's main job here. | Free |
| C. BM25 extension (e.g. ParadeDB `pg_search`) | Real BM25 ranking. | **Verified 2026-11-05: `pg_search` is not in the project's extension list.** Would need a self-hosted Postgres → contradicts D2. | Self-hosting cost |
| *Note (found 2026-11-05)* | The project offers **PGroonga** (full-text search for all languages, including Hebrew) and `pg_trgm` (fuzzy name matching). Not adopted. Can be evaluated in Phase 2 if Hebrew keyword recall with `simple` is weak. | Extra extension to learn | Free |

Hebrew semantic recall relies on vector search.  says "BM25-style ranking". Option A is BM25-like only in spirit. See contradiction C1.
**Recommendation:** A.

### D11 – Hybrid ranking
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.

| Option | Pros | Cons |
|---|---|---|
| **A. Reciprocal Rank Fusion (RRF), k = 60, optional per-list weights** (recommended) | Uses ranks only, so no need to normalize `ts_rank_cd` vs cosine scores. Robust. Supabase's documented pattern. Easy in one SQL function. | Ignores score gaps. |
| B. Weighted score (α·cosine + (1−α)·normalized ts_rank) | Intuitive. Tunable. | Scores are on different scales. Needs normalization and tuning per query type. Fragile. |
| C. Vector-first, FTS only as fallback | Simplest. | Loses exact-match strength for names/IDs. Not really hybrid. |

**Recommendation:** A. Candidate pool = 3 × match_count from each list. Cost: free.

### D12 – Reranking
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. Defer. Keep a `Reranker` interface (no-op).** Decide after retrieval evaluation in Phase 2/8 (recommended) | The brief says it is not required. Less latency and cost. | Possibly lower precision on ambiguous queries. | Free |
| B. LLM reranking with the small model | No new vendor. | Extra latency and tokens per query. | Small per-query cost |
| C. Hosted reranker (e.g. Cohere) or local cross-encoder | Best precision. | New paid service (approval) or heavy local model. | Paid or heavy |

**Recommendation:** A.

### D13 – Document processing libraries and CSV chunking
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.

| Format | Recommended | Alternatives |
|---|---|---|
| PDF | `pypdf` (pure Python, BSD license, page numbers for citations) | `pdfplumber` (better tables, slower). `PyMuPDF` (fastest, but AGPL license). OCR for scanned PDFs is out of scope: no text → status Failed with a clear reason. |
| DOCX | `python-docx` (paragraphs + headings + tables) | `docx2txt` (simpler, loses structure) |
| TXT | stdlib, UTF-8 with fallback encoding detection | — |
| MD | stdlib read + `MarkdownHeaderTextSplitter` (heading path stored as location) | — |
| CSV | stdlib `csv` | `pandas` (heavier. Only needed for the optional ML extension.) |

**Chunking (proposed):**
- Text (updated 2026-11-06): default = `RecursiveCharacterTextSplitter`, ~500 characters, 50 overlap, configurable. Alternative evaluated in Phase 2: split by headings (MD/DOCX) first, then by size (~800–1,000 characters), so tables and sections stay whole. Keep the method with better hit@k / MRR. Chunks go to the `corporate_documents` table. Metadata: `file_name`, `chunk_index`, `section` (nearest heading, page, or CSV row range).
- **CSV:** groups of rows (default 10 rows, or fewer if the token budget is exceeded). Each chunk repeats the header and renders each row as `Column: value` lines, so it reads well for both embeddings and FTS. Location = file name + row range (e.g. rows 11–20), as  requires. The whole original file stays in Storage (D4).

**Recommendation:** As above. Cost: free.

**Phase 2A result (2026-11-06):** both strategies scored 1.0 on the hybrid eval (18 queries). **Default = `markdown`** (headings, then 1000/100): table rows stay with their header row 98% vs 85%, 131 vs 170 chunks. `fixed` 500/50 (baseline) stays available (`--chunking fixed` / `CHUNKING_STRATEGY`). Implementation details found in the eval:
- The embedded text is `title + section + chunk` (stored `content` stays raw), so cut-off chunks keep their context.
- The keyword part of `hybrid_search` OR-s the query terms (AND with the `simple` config rarely matches a question), and English/Hebrew stop words are removed in Python first. Without that, hybrid hit@1 dropped to 0.889 in English.

### D14 – Background job execution for research runs
- **Status:** Approved (2026-11-05). Recommended option A.
- **Needs:** Runs continue when the user disconnects. Queue + concurrency limit, stop, persisted stage status.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. DB-backed queue: `research_runs` table + async worker loop started with the backend. Claims jobs with `FOR UPDATE SKIP LOCKED` up to the concurrency limit. Heartbeat + stale-run recovery.** (recommended) | No new infrastructure. Queue, concurrency and stop work from Phase 4 (so Phase 8 only adds UX). State survives page reloads. Worker can move to a separate process later without code changes. | If the backend restarts mid-run, that run is marked failed/partial (acceptable; resuming is out of scope). Needs an always-on host. | Free |
| B. FastAPI `BackgroundTasks` / plain `asyncio.create_task` | Simplest code. | No queue, no concurrency limit, lost on restart. Phase 8 would need a rewrite. | Free |
| C. Celery / RQ / Arq + Redis | Industry standard. Retries, monitoring. | Extra service (Redis) to run and host. Overkill for MVP. | Redis hosting (free tier or paid) |

Same mechanism handles document ingestion jobs.
**Recommendation:** A.

### D15 – Hosting
- **Status:** Approved (2026-11-05). See approved decision below.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. Local only during development. Before the demo: frontend on a free static host (Vercel / Netlify / Cloudflare Pages) + backend as one always-on container on Render or Railway. Supabase Cloud free tier.** (recommended) | Cheap and simple. Backend stays up so background runs aren't killed. | Small monthly fee for the always-on backend. | ~$5–7/month for backend (needs approval). Frontend + Supabase free. |
| B. Same, but backend on a free tier that sleeps (e.g. Render free) | $0 | Sleeping instance kills running research jobs and gives slow cold starts. Bad for a live demo. | $0 |
| C. Local only (demo from laptop) | $0. Zero deployment work. | Not reachable by others. Weaker for portfolio. | $0 |

Supabase free tier notes: projects pause after ~1 week of inactivity. The built-in email sender is heavily rate-limited (a few emails per hour), which affects invites (see risk R4).
**Recommendation (original):** A, with deployment done near the end (Phase 8). Develop with C until then.

**Approved decision:** Free hosting. Develop locally until Phase 8. Then frontend on **Vercel** (free) and backend as a **Docker Space on Hugging Face Spaces** (free CPU tier, secrets stored as Space secrets). A free Space sleeps after ~48 h without traffic, so open it before a demo. Deploying from GitHub uses the private repo (D30).

### D16 – PDF generation (Hebrew RTL + English)
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. Jinja2 HTML/CSS templates → PDF with headless Chromium (Playwright)** (recommended) | Browser-grade RTL and bidi text, Hebrew fonts, mixed He/En. Same HTML look as the in-app briefing. Installs easily on Windows (`pip` + `playwright install chromium`). | ~150 MB browser download. Heavier container image. | Free |
| B. WeasyPrint (HTML/CSS → PDF) | Pure HTML/CSS. Good RTL via Pango. Lighter than Chromium. | On Windows needs the GTK/Pango runtime installed separately (painful setup). | Free |
| C. ReportLab | Pure Python, precise layout. | RTL needs manual bidi + shaping (`python-bidi`), fragile with mixed He/En. More layout code. | Free |

Fonts: bundle an open-license font with Hebrew + Latin (e.g. Noto Sans Hebrew / Heebo, OFL). Two export modes: summary only / full.
**Recommendation:** A. Run a 1-hour Hebrew PDF spike early (Phase 1 or 2) to remove the risk.
**Spike result (2026-11-06):** A confirmed. Hebrew RTL + mixed English/numbers render correctly with Playwright 1.64 + bundled Heebo (OFL). Two bidi rules for the Phase 6 template: wrap data values in `<bdi>`, and `unicode-bidi: isolate` on citation markers. (The spike is kept in the development repo; PDF export was later cut by D38.)

### D17 – Research depth parameters
- **Status:** Approved (2026-11-05). Table as proposed.

| Parameter | Quick | Standard (default) | In-depth |
|---|---|---|---|
| Max extra research iterations (Orchestrator) | 0 | 1 | 2 |
| Web queries (all agents, per iteration) | ~6 | ~12 | ~20 |
| Tavily `search_depth` | basic | basic | advanced |
| News time range | 30 days | 90 days | 12 months |
| "Last 48 hours" news query | yes | yes | yes |
| Max sources kept in the briefing | 10 | 20 | 35 |
| Full page extraction (Tavily extract) for top results | 0 | 3 | 8 |
| RAG top-k per query | 6 | 10 | 15 |
| Competitors profiled | 2 | 3–4 | 5 |
| Soft time limit for the run | 3 min | 6 min | 12 min |
| Approx. Tavily credits per run | ~6–8 | ~15–20 | ~50–60 |

All values live in `system_settings_versions` and are admin-editable within ranges. Local language + English queries are counted inside the query budget.
**Amended by D37 (2026-11-08):** query numbers are a cap per run including extra rounds; In-depth uses `basic`; per-run credit cap; search languages Hebrew + English only.
Cost note: Tavily's free plan (around 1,000 credits/month, verify) supports roughly 50 Standard runs per month, including development and evaluation.
**Recommendation:** Approve this table as the starting point. Tune it after the first evaluation runs.

### D18 – Initial concurrency limit
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.
- **Options:** A. 2 system-wide, 1 per user (recommended). B. 1 system-wide (simplest, long waits). C. 5 system-wide (needs more memory and higher rate limits).
- **Pros of A:** Fits one small backend instance and API rate limits. Shows the queue working in a demo. Per-user limit prevents one user blocking others.
- **Cost:** No direct cost. Higher limits may need a bigger instance.
- **Approved decision:** **1 run system-wide** (so also 1 per user), because of the Gemini free-tier rate limits. The queue still works and can be demonstrated. Configurable in settings.

### D19 – Default usage quotas
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.
- **Options:**
  - A. **30 runs per user per month, soft limit (warning at 80% and 100%, run still allowed). Admin can set a hard limit or approve extra runs per user.** (recommended)
  - B. No default quota, only tracking.
  - C. Hard default limit (e.g. 20/month).
- **Rationale:**  says the default is not a hard block. 30 Standard runs ≈ 450–600 Tavily credits, so the free Tavily plan supports about one active user plus testing. In-depth runs could count as 3 runs (optional, adds complexity, not recommended for MVP).
- **Approved decision:** **30 runs per user per month**, soft limit, warnings at 80% and 100%. Admin can set a hard limit or approve extra runs. Note: the Tavily free plan supports ~55 Standard runs per month for the whole system, so one heavy user could use most of it. The Phase 8 usage view shows remaining credits.

### D20 – Organization profile update process and ownership
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.
- **Options:**
  - A. Admin edits a manual form only. Shows `last_reviewed_at`. Dashboard reminder to admins after 90 days.
  - B. **A + an optional "Draft from knowledge base" button: the LLM proposes field values from selected KB documents, the admin reviews and saves.** (recommended,  says the profile can be filled "with help from KB documents")
  - C. Automatic re-generation from the KB on every upload.
- **Pros of B:** Matches the brief, keeps a human in control, no surprise changes. **Cons:** One more LLM feature (small).
- **Cost:** A few cents per draft.
- **Ownership:** Admin role only. All users can read. Agents read it at run start and record which version was used.
- **Recommendation:** B. If time is short, ship A first and add the draft button later in Phase 7.

### D21 – Source credibility rules
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.
- **Options:**
  - A. **Hybrid: rule-based source tiers + LLM evidence assessment + corroboration rule** (recommended)
  - B. LLM-only judgment for each source. (Simple, but inconsistent and hard to test.)
  - C. Third-party credibility ratings API. (Paid, poor coverage for Hebrew/local sources.)
- **Proposed rules for A:**
  1. **Source tier** (deterministic, config list of domains + patterns):
     - Tier 1 – Official: the company's own domain / investor relations, regulators and government (`.gov`, `.gov.il`, SEC, ISA/MAYA, TASE), stock exchanges.
     - Tier 2 – Established news and financial media (curated allowlist, Hebrew + international).
     - Tier 3 – Professional / industry sources, analyst firms, trade publications.
     - Tier 4 – Other / unknown: blogs, forums, social media, aggregators.
     - User-preferred URLs get search priority but keep their real tier.
  2. **Evidence quality** (LLM, structured output per claim): fact vs opinion, direct vs indirect, has supporting data, publication date.
  3. **Corroboration:** count distinct independent domains supporting the claim.
  4. **Recency:** news older than the depth's time range is marked as dated. Financials must state their period.
  5. **Claim confidence:**
     - High = a Tier 1 source, or ≥ 2 independent Tier 2–3 sources.
     - Medium = 1 Tier 2–3 source.
     - Low / unverified = only Tier 4 sources, or opinion only. Important claims with Low confidence are labeled "unverified" or dropped.
  6. **Conflicts:** sources that disagree → `is_conflict = true`, both shown, not resolved.
- **Cost:** Included in LLM calls. **Recommendation:** A.

### D22 – How database tables are created
- **Status:** Approved (2026-11-05). See approved decision below.
- **Context:** The `supabase` Python client works over REST and cannot run DDL. `.env` has no direct DB connection string.

| Option | Pros | Cons | Cost |
|---|---|---|---|
| **A. Versioned SQL files in `supabase/migrations/` (`YYYYMMDDHHMMSS_name.sql`), applied manually in the Supabase SQL Editor, tracked in a checklist in `README.md`** (recommended) | Zero new tools or secrets. Easy to review. File naming is Supabase-CLI compatible, so we can switch to B later. | Manual step. Risk of forgetting a file (mitigated by the checklist + a `schema_version` check in `db_setup.py`). | Free |
| B. Supabase CLI migrations (`supabase link` + `supabase db push`) | Repeatable, standard, tracks applied migrations. | Install CLI (Scoop/npm on Windows), needs the DB password, more setup. | Free |
| C. Direct Postgres connection (`psycopg` + migration runner) | Fully automated from Python. | Needs a new secret (`SUPABASE_DB_URL`) in `.env`. Changing `.env.example` needs approval. Another dependency. | Free |

**Recommendation (original):** A now. Move to B if migrations become frequent.

**Approved decision:** **D. Supabase MCP server connected to Claude Code.** The user connects it once (login to their Supabase account, free, no new secret in `.env`). Claude Code then applies each migration file through the MCP. Rules:
- Every schema change is first written as a versioned file in `supabase/migrations/` (`YYYYMMDDHHMMSS_name.sql`), then applied. No DDL that isn't in a file.
- Scope the MCP connection to the dev project only. Never connect it to a project with real data.
- The app itself reads and writes data through the `supabase` Python client (automatic). The MCP is only a development tool.
- Fallback if the MCP is unavailable: paste the same file into the SQL Editor (option A).

**Update 2026-11-08 (no change of decision, B added as a working route):** the Supabase CLI is linked to the dev project. The MCP's `apply_migration` stores its own timestamp and SQL Editor runs aren't recorded, so the remote history had drifted from the file names; it was fixed with `supabase migration repair`. From now on `supabase db push` (B) is the preferred way to apply a migration file, since it records the file's own version. The MCP stays for inspection (schema, SQL checks, advisors, logs) and as a fallback. The "every change is a file first" and "dev project only" rules are unchanged.

### D23 – Backend API framework *(added: not listed in , but Phase 1 needs it)*
- **Status:** Approved (2026-11-05). Recommended option chosen unless stated below.

| Option | Pros | Cons |
|---|---|---|
| **A. FastAPI + Pydantic + Uvicorn** (recommended) | Async (fits parallel agents and the worker loop). Pydantic models shared with agent contracts. Automatic OpenAPI docs. | — |
| B. Flask | Familiar, simple. | Sync by default. Validation and docs need extra libraries. |
| C. Django + DRF | Batteries included. | Heavy. Its ORM and auth overlap with Supabase. |

**Recommendation:** A. Cost: free.

---

## Decisions after Phase 1

### D33 – Build order: working agent before KB management
- **Date:** 2026-11-06 · **Status:** Approved
- **Context:** A single tool-calling agent CLI (`agent.py --company`) with `search_internal_docs` and `search_live_news` can run right after the KB is loaded. Our plan reached the first briefing only at the end of Phase 4.
- **Decision:**
  1. Order: **2A** KB core (migration, Gemini embeddings, `ingest_data.py` for MD + CSV, `hybrid_search`, `search_internal_docs`, short retrieval eval) → **2B** `search_live_news` (minimal Tavily) → **`agent.py`** → **2C** KB management (upload/replace/delete UI, PDF/DOCX, job runner) → full Phase 3 → Phase 4.
  2. `agent.py` uses LangGraph + Gemini (D7, D8), not OpenAI. It's a thin CLI over project services (`backend/agent.py`), so nothing is thrown away. Phase 4 splits it into the six agents, and the CLI stays as a dev/demo tool. *(Superseded 2026-11-08 by D36: two agents in the MVP; the 2B agent stays as eval baseline.)*
  3. Kept from the brief: **hybrid** search (D10, D11) behind the same tool; **top-k configurable, default 5** (3 × 500 chars is too little context, e.g. the pricing table); news window **48 h first, widen to 30 days if empty** and label it as older; **sources required** in the briefing and missing info marked as missing; `--language he|en` (default `en`).
  4. Phase 2 open questions (max upload size; whether regular users see the KB list/search) are deferred to 2C.
- **Rationale:** Working end-to-end product early, later work builds on tested code. Nothing from the brief is dropped, only reordered.
- **Alternatives:** Keep the original order (first briefing only after Phase 4); write `agent.py` as a standalone throwaway script.

### D34 – Backend first, then frontend (middle path)
- **Date:** 2026-11-06 · **Status:** Approved
- **Context:** Building the whole backend first and the frontend in the next stage keeps each step testable without UI. Our plan mixed backend and UI inside Phases 2C and 5–7, and Phase 1 already built a frontend skeleton (login, set-password, layout, minimal invite screen).
- **Options:**
  - A. Strict backend first: every backend item of all phases, then all UI. + Stable API before screens, one technology at a time. − No visual demo until very late, integration issues (auth, CORS, RTL) found late.
  - B. Our original order (feature slices: each phase = backend + UI). + Something visible after each phase, integration issues found early. − Constant context switching, screens built on an API that still changes, phases 5–7 hard to close.
  - C. **Middle path (chosen).** Core without UI → API parts of Phases 5–7 → all screens in one block → Phase 8.
- **Decision:**
  1. Order: **2C-API → 3 → 4 → 5-API → 6-API → 7-API → frontend block (KB screen, 5-UI, 6-UI, 7-UI) → 8**.
  2. Each of Phases 2C, 5, 6, 7 runs in two parts: **API part** (services, endpoints, server-side validation, RLS, API tests) in the backend block, **UI part** (screens, client validation, UI tests) in the frontend block.
  3. Phase 8 stays last and keeps both its backend and UI items (quality checks, feedback, quotas, costs, queue, stop, deployment, final check against the success criteria).
  4. The Phase 1 frontend skeleton stays as is. Until the frontend block, only bug fixes there.
  5. The agent CLI (`backend/agent.py`) is the demo tool until the frontend block.
- **Rationale:** The real risk is agent quality, which the CLI and tests cover without UI. Screens are built once, on a stable API, which saves rework. The full app is usable at the end of the frontend block, before Phase 8, so a demo exists even if time runs short.
- **Alternatives:** A and B above.

### D35 – KB upload limits and regular-user visibility (Phase 2 open questions)
- **Date:** 2026-11-07 · **Status:** Approved
- **Decision:**
  1. **Upload limits:** max **20 MB** per file (Supabase free tier allows 50 MB per file and 1 GB total). Allowed formats: PDF, DOCX, TXT, MD, CSV (D3), checked by extension **and** file content (magic bytes / UTF-8 decode), not only the extension. Max **~500 chunks** per document: larger → `failed` with a clear message (protects the Gemini embedding free-tier quota).
  2. **No OCR in the MVP:** a scanned PDF (no extractable text) → `failed` with a clear message ("no extractable text, probably a scanned document; upload a digital version or a text file"). OCR is an **optional later extension** (Future work), consistent with D13.
  3. **Regular users: read-only access.** They see the list of current, indexed documents (name, type, update date) and can use the KB test search box. Upload, replace, delete, failed documents and failure messages are **admin only**. Matches  ("use the knowledge base") and the existing 2A RLS read policy.
- **Rationale:** Limits fit the free tiers. Read-only visibility lets users see what the agents rely on without risking the KB.
- **Alternatives:** Larger limits (closer to the 50 MB Storage cap); KB visible to admins only (regular users use it only through agents); OCR now (Tesseract locally, weak Hebrew; or Gemini vision, conflicts with D7 "sample data only").

### D36 – Two agents instead of six (MVP scope), splittable later
- **Date:** 2026-11-08 · **Status:** Approved. `ARCHITECTURE.md` (§2 diagram, §3, §4.2, §5) updated 2026-11-08.
- **Context:** Phase 2B built one tool-calling agent (`agent.py`). The brief defines six (Orchestrator + 5 specialists). For an MVP that mainly shows capabilities, six agents mean a large Phase 4 and ~10–20 model calls per briefing on the Gemini free tier.
- **Decision:**
  1. **Research Agent** (tool-calling, extends the 2B agent) covers the Internal, Web and Competitive Intelligence roles. Tools: `search_internal_docs`, `search_live_news`, plus the Phase 3 tools (company search, competitor search, page extract).
  2. **Analysis & Writing Agent** covers the Strategic Analyst and Briefing Writer roles: one LLM step with structured output (Pydantic), no tools. Separate fields keep facts, analysis and recommendations apart. If one call gets too long, split it into summary + appendix calls inside the same agent.
  3. **Orchestrator = LangGraph graph code, not an LLM supervisor.** Fixed flow: research → completeness check → bounded extra research round(s) per depth (D17) → analysis & writing → quality checks. The completeness check may use a small LLM call to name what's missing, but the code decides the number of rounds and when to stop.
  4. **Progress stages stay the 7 of D25.** Stages are process steps, not agents: the Research Agent reports Internal Research / External Research / Competitor Analysis from the tools it runs; the second agent reports Strategic Analysis / Briefing Writing.
  5. **Kept open for splitting later (into 3 research agents and/or separate Analyst + Writer, i.e. back to the brief's six):**
     - The Research Agent returns a typed `ResearchFindings` contract with separate sections `internal`, `web`, `competitive` (each with its sources and gaps). A future Internal / Web / Competitive agent returns one section each, and the graph merges them, so the completeness check and the writing step don't change.
     - The second agent has two internal functions, `analyze(findings) -> Analysis` and `write(findings, analysis) -> Briefing`, with their own contracts and prompt files. They are called in sequence today. Splitting = making each one a graph node.
     - One prompt file per role (`research/`, `analysis/`, `writer/`), versioned (D29), so a split doesn't rewrite prompts.
     - Graph nodes are registered by name in one place; adding parallel research nodes = new nodes + edges, no change to the run state machine or stage reporting.
  6. The 2B single agent (`agent.py`) stays as a **baseline** for the agent eval (single agent vs. two agents on the same companies) and as a demo fallback.
- **Rationale:** Fewer model calls (~5–8 per briefing), much smaller Phase 4, builds directly on tested 2B code. Still shows a multi-agent design (two agents + graph orchestration + bounded loop + structured output). Separating research from writing fixes the 2B issue of stretching generic KB content into "our positioning".
- **Alternatives:** Six agents as in the brief (most depth, largest scope and cost); one agent doing everything (cheapest, but mixes research and writing, weak structured output, re-runs everything when info is missing).

### D37 – Tavily credit budget and search languages (Phase 3 open questions)
- **Date:** 2026-11-08 · **Status:** Approved
- **Context:** Tavily account checked 2026-11-08 via `GET /usage`: plan **Researcher (free), 1,000 credits/month**, 10 used. Rates assumed: basic search 1 credit, advanced 2, extract 1 credit per 5 URLs (basic); verify on Tavily's pricing page. The agent eval (5–8 companies × single agent vs. two agents) could use half the monthly budget.  asks for the local language + English for every company.
- **Decision:**
  1. **Credit budget (amends D17):**
     - D17's web-query numbers are a **cap per run, including extra research rounds** (not per round).
     - **In-depth uses `search_depth = basic`** in the MVP (more searches instead of expensive ones). `advanced` stays a config option.
     - **Per-run Tavily credit cap** in the settings (defaults: Quick 8, Standard 20, In-depth 40). When reached, the run stops searching, continues with what it has, and the briefing marks the gaps. Credits per run are recorded.
     - **Cache Tavily responses during eval and tests** (keyed by request body), so re-running the same company costs no credits. Off in normal runs.
  2. **Search languages: Hebrew and English only in the MVP (amends ):**
     - **Israeli company:** Hebrew + English queries.
     - **Any other country:** English queries (international sources), **plus one Hebrew query** (e.g. `"<company> ישראל"`) at every depth (Quick too) to catch Israeli activity (R&D center, customers, partners).
     - The country field stays: used for company identification, in query wording, and for official-source tiering (e.g. `.gov.il`, MAYA only for Israel).
     - **Transparency:** the briefing stores and shows `search_languages`. When the company's local language wasn't searched, the briefing says so ("searched in English and Hebrew only; local-language sources not checked"), consistent with .
     - The country → language table stays in config. Adding a language later = one row, no agent changes.
  3. All search-language queries count inside the per-run query cap.
- **Rationale:** Fits the free plan with room for development and eval. Two languages we can actually judge in eval, matching the KB, embeddings and briefing languages. The extra Hebrew query is cheap and useful for an Israeli seller.
- **Alternatives:** Keep D17 as per-round budgets with `advanced` for In-depth (≈ 17–22 In-depth runs/month); local language + English per  (better coverage of non-English companies, more queries, results we can't evaluate); English only for foreign companies (one credit cheaper, misses Israeli activity).

### D38 – Portfolio MVP scope
- **Date:** 2026-11-09 · **Status:** Approved
- **Context:** The goal is a **portfolio project** that shows the AI/backend skills (agents, RAG, sourced research, grounding, eval). The user's existing portfolio piece is a Flutter mobile app (quote generator), so this project should highlight the AI/backend side, not UI. The remaining plan (Phases 5–8 + React frontend block: editing, versions, PDF, follow-up, org/user management, templates, versioned admin settings, quotas, cost views) is product scope that portfolio visitors won't see.
- **Decision:**
  1. **New order:** **3.5** grounding fix → **4-lite** → **5 Streamlit UI** (D39) → **6 demo mode + deploy** (D39) → **7 portfolio polish**.
  2. **3.5 – grounding fix:** prompt v3 with a rule against generic market statements (every claim must be about the specific company and backed by a source, otherwise it goes under missing information); an **optional** company website (`--website`, passed to research as `company_domain`), not a required one; when the company can't be identified, stop with "company not identified, please provide the website" instead of writing a briefing; an eval case with a fictional company.
  3. **4-lite keeps:** Pydantic contracts, the two agents in the LangGraph graph (D36), bounded extra research round (D17), citations + claim confidence + conflicts (D21), basic quality checks, simple persistence of runs / stages / briefings / sources / claims, simple usage logging (tokens, Tavily credits), retries with "failed stage → continue, mark incomplete", the 2B-vs-graph eval.
  4. **4-lite drops:** `stopping` / `stopped` states and user cancel ( except per-stage persistence), the research-run queue with a concurrency limit (the 2C `jobs` queue stays as is for ingestion), `system_settings_versions` and admin rollback (depth config stays in code, `app/research/depth.py`), `briefing_versions`, organization profile input.
  5. **Moved to "Future work"** (listed in the README, not built): editing + versions + comparison, PDF export, follow-up research, organization and personal profiles, user management screen, templates, admin settings UI, feedback and claim reports, quotas, cost views, queue/stop UX, the React frontend block and the KB management screen.
  6. **Kept unchanged:** everything already built (Phases 1–3, incl. the React skeleton, Supabase Auth/RLS and the KB management API). They're described in the README as built foundations; the React skeleton is marked "not used by the demo".
  7. **ML win probability: not built.** 30 synthetic rows give no credible signal, and new companies have no `Previous_Interactions_Count`. Stays optional ( item 1, D4).
  8. **D30 amended:** the repo becomes **public** in step 7, only after a secret scan of the **full git history**.
- **Rationale:** Smallest scope that still shows the distinctive parts: a two-agent graph, hybrid RAG, Hebrew + English research with tiered sources, grounding rules and a measured eval, plus a live link a visitor can open. Saves the whole frontend block and most of Phases 5–8.
- **Alternatives:** Keep the full plan (D34; most features, weeks more work nobody sees in a portfolio); also build the ML win-probability model and require the company URL (weak model, more friction); stop after Phase 4 with CLI only (no visible demo).

### D39 – Streamlit UI, public demo mode, Streamlit Community Cloud
- **Date:** 2026-11-09 · **Status:** Approved
- **Context:** D38 needs one UI and one public link. Every live run spends Gemini free-tier calls and Tavily credits (1,000/month), so a public link with unlimited live runs would exhaust the quotas quickly (bots included).
- **Decision:**
  1. **UI: Streamlit, the only UI** (amends D6; Streamlit was D6's fallback). `app.py` is a thin layer over the backend services: form (company, optional website, meeting type, language, depth), progress by stage (`st.status`, not just a spinner), briefing view with citations and info-type labels, RTL for Hebrew, "recent briefings" list. Errors are shown in the UI, the app doesn't crash on a failed API call. The entry point is the Phase 4 function (`run_research`).
  2. **Demo mode (option B of the 2026-11-09 discussion):**
     - Anyone with the link sees **3–4 pre-generated sample briefings** (Israeli + foreign company, He + En), read from the database. No login, no quota use.
     - A **live run needs an access code** (stored in Streamlit Secrets, shared on request / in interviews).
     - A **site-wide daily cap** on live runs (e.g. 5/day, counted in Supabase), so the quotas are safe even if the code leaks.
  3. **Auth:** the UI doesn't use Supabase Auth. Backend calls run server-side with the service key, which stays in Secrets and never reaches the browser. The Phase 1 auth/roles/RLS code stays in the repo. KB uploads stay via the existing API / `ingest_data.py`.
  4. **Hosting: Streamlit Community Cloud** (amends D15; Vercel + HF Spaces not used). Python 3.12 in Advanced settings. Secrets: `GEMINI_API_KEY`, `TAVILY_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_ANON_KEY`, the access code; to be verified on the first deploy that root-level secrets reach `core/config.py` as env vars. Slim requirements file for the deploy if the full one is too heavy. Free apps sleep when idle (acceptable). Deploy docs in `deployment_guide.md`.
- **Rationale:** Visitors see a full, high-quality result instantly with no sign-up. The live run, the most convincing part, is still available on request. Quotas are protected twice (code + daily cap). Python only, one deploy, minimal work.
- **Amendment (2026-11-11, Phase 6 plan, approved by the user):** daily cap default **4** (not 5): each run ≈ 2 flash calls and on 2026-11-11 only ~10 flash calls succeeded before the daily 429. The cap day is the **Pacific date** (resets with the Gemini quota, 10:00 Israel time); a run counts when it starts, failed runs included. **Fail closed:** demo mode is on unless `DEMO_MODE=off`; with no `DEMO_ACCESS_CODE` or no reachable counter, live runs are disabled. Public visitors see only sample briefings (the full recent list needs the code). Samples generated after the Phase 4-lite prompt fixes; the old Snowflake v1 briefing is not a sample.
- **Alternatives:** Fully open live runs (no friction, quotas gone in a day); Supabase Auth login (shows auth skills, but visitors won't sign up, so it ends as a shared demo password); Streamlit Cloud viewer allow-list (blocks portfolio visitors entirely); React + Vite (more frontend breadth, several days more and two deploys).

### D40 – Phase 4 open questions: completeness, meeting-type tailoring, generic-statement check
- **Date:** 2026-11-09 · **Status:** Approved (the user picked the recommended option for each; for §1 they asked for my recommendation)
- **Context:** Open before building Phase 4: the completeness criteria (the round limit is already D17: 0 / 1 / 2), how much meeting-type tailoring goes into prompts vs code. Phase 3.5 left one item open: a generic risk ("intense competition…") survived prompt v3.
- **Decision:**
  1. **Completeness = code only, no LLM call.** Criteria: internal KB searched; ≥ 1 profile source (or an official page); news queried; ≥ 1 financial source; ≥ 1 people source; competitive sources ≥ 2 / 3 / 5 by depth (D17 "competitors profiled"). An extra round runs only the searches that can change the answer: purposes never queried (agent skipped a tool, query cap) and the internal search if it never ran. A purpose that was queried and found nothing stays a gap (same query → same result). No web rounds after a fatal Tavily error or the credit cap. Gaps go to the writer's Missing information.
  2. **Meeting-type tailoring = config in code** (`app/agents/tailoring.py`): per type the seller's role, emphasis list, opportunity lens, risk lens, question focus. Injected into the one analysis prompt and the one writer prompt. Adding a meeting type = one entry.
  3. **Generic statements = small-model judge** (`gemini-3.5-flash-lite`, one call per briefing) on the summary's analysis items and sections 7–12; flagged items are removed and listed in the quality report; a section left empty becomes `missing_info`. If the judge fails, the briefing is kept and the report says the check didn't run.
- **Rationale:** (1) predictable, testable, saves one strong-model call per round on the free tier; (2) one prompt per role, the difference between types is visible and testable in one file; (3) a cited generic sentence passes any rule a regex can check, and Hebrew phrase lists are brittle.
- **Alternatives:** (1) code + a small LLM call that names gaps and proposes queries (more flexible, one more call per round); (2) one prompt file per meeting type (more control, duplicated text); (3) a deterministic phrase list (free, but the 3.5 example cited a source and would pass).

### D41 – Model per role after the free-tier daily quota finding (amends D7)
- **Date:** 2026-11-09 · **Status:** Approved (user chose option 1 after an explanation)
- **Context:** The first agent eval failed: the Gemini free tier allows **20 requests per day per model** for `gemini-3.5-flash` (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). A full run used 6 strong-model calls (4 Research Agent, analysis, writing) + 1 small (judge) → 2–3 runs a day; the eval needs ~30 strong calls and D39 plans up to 5 live demo runs a day. The quota is counted per model.
- **Decision:**
  1. The Research Agent's tool loop runs on the small model (`gemini-3.5-flash-lite`), set by `RESEARCH_MODEL_TIER` (`small` default, `strong` to go back without a code change). Analysis and writing stay on the strong model; the judge stays on the small one. → **2 strong calls per run (~10 runs/day)**, ~7 small calls.
  2. Research prompt v2: at least two internal searches, the second one built on the web results (competitors found, industry, need), because v1 on flash-lite searched the KB only once.
  3. A daily-quota 429 is not retried (the stage fails at once with a clear message).
  4. The agent eval runs over two days (2B baseline ~3 strong calls per company on day 1, the graph on day 2).
- **Checked before deciding (research stage only, cached Tavily):** flash-lite called all four required tools for Snowflake and monday.com, added the Hebrew alias `מאנדיי` by itself, found 25 / 24 web, 4 / 8 competitive and (v2) 15 / 14 internal sources, accurate cited notes, ~13 s instead of minutes. Flash-lite's own daily limit is not known yet (it served 40+ calls on 2026-11-09); measure it before Phase 6 sets the demo cap.
- **Rationale:** The research loop is tool selection + short notes, with most safeguards in code (fixed company/website, relevance filter, completeness check and extra round). The output users read (analysis, Hebrew writing) stays on the strong model. Stays free (user preference).
- **Amendment (2026-11-11, measured in AI Studio's rate-limit page, approved by the user):** free-tier limits are flash (served as `gemini-3.6-flash` behind the `gemini-3.5-flash` alias) **20 RPD / 5 RPM**, flash-lite **500 RPD / 15 RPM**, embeddings 1K RPD / 100 RPM. Flash showed **29 / 20** requests in a day, so **rejected requests count** too. The google-genai SDK retried 408/429/5xx up to 6 times silently, which explains why only ~10 calls succeeded on 2026-11-11. **Change:** the orchestrator's strong model makes one request per call (`max_retries=1`); retries only in `Run.attempt()` (logged, 20 s wait to leave the per-minute window, none after a daily-quota 429). Flash-lite and embeddings keep the SDK retries (their daily limits are far away).
- **Amendment (2026-11-24, fallback writer, approved by the user):** on 2026-11-24, 4 of 6 live runs got `503 UNAVAILABLE` ("high demand") from flash, mostly in the writing step, losing the research + analysis already paid for (and, in the demo, a cap slot). **Change:** when every writing attempt on the strong model fails with a 503 overload (not a quota 429 or another error), the writer tries **once on the small model** (flash-lite, own daily limit). The briefing says so (`meta.fallback_writer`, a ⚠ line under the header, the stage detail). Same prompts and quality checks. Analysis has no fallback (its failure already leads to a partial briefing). Fallback-written briefings are not used as samples. `Deps.writer_fallback` turns it off.
- **Alternatives:** keep everything on flash and run the eval over 3–4 days (demo limited to 1–2 live runs a day); paid Gemini tier 1 (high limits, a few cents per run, needs billing).

### D42 – Finishing plan: samples, prompt freeze, public repo
- **Date:** 2026-11-25 · **Status:** Approved
- **Context:** Phases 5–6 are built and reviewed; what is left is the samples, going public, deploy and the README. The flash free tier (20 RPD, frequent 503s on 2026-11-24) makes every extra tuning run expensive.
- **Decision:**
  1. **Three samples:** Snowflake (en, partnership), monday.com (he, sales), QuantaLake (en, competitor win-back). One of them run in demo mode with a temporary code, so the daily cap is checked live too. A fallback-written briefing (D41 amendment) is not a sample.
  2. **Prompt freeze after the samples:** research/v2, analysis/v5, writer/v5, quality/v4 stay as they are unless a sample is clearly wrong. Known limits go to the README.
  3. **Public repo:** a public copy with a fresh, condensed history (code, migrations, evals, demo data, these docs). Working notes, the original brief and the phase-by-phase planning prompts stay in the private development repo. The README says what the project started from.
  4. **README for visitors** with a section on how the demo copes with free-tier limits (access code + daily cap, fallback writer, keepalive) and a CI badge.
- **Rationale:** Three samples cover He + En, Israeli + foreign, sales + partnership + win-back. Freezing the prompts stops spending the scarce flash quota on diminishing returns. A fresh public copy shows only what runs.
- **Alternatives:** a fourth sample (Wix, partnership in Hebrew); more prompt tuning; making the development repo public after rewriting its history.

## When each decision is needed

| Before | Decisions |
|---|---|
| Phase 1 | D6, D22, D23 (+ D15 for local setup) |
| Phase 2 | **D9** (fixes `vector(1536)`), D8 (splitters), D10, D11, D12, D13, D14 |
| Phase 3 | D17 (query budgets), D21 (tiers), D37 |
| Phase 4 | D7, D8, D17, D18, D21, D36 |
| Phase 6 | D16 (spike earlier) |
| Phase 7 | D20 |
| Phase 8 | D19, D15 (deployment) |
| After Phase 3 | D38, D39 (portfolio scope, UI, demo mode, hosting) |
| Phase 4-lite | D40 (completeness, tailoring, generic check), D41 (model per role) |
| Phases 6–7 finish | D42 (samples, prompt freeze, public repo) |

---

## Risks

| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Scope is large for the timeline: 6 agents, RAG, web research, UI, roles, history, PDF, costs | High | Build the "must have for the demo" path first. Phases 7–8 extras can be cut. **Resolved 2026-11-09 by D36 + D38** (two agents, portfolio scope). |
| R15 | Public demo link burns the free Gemini / Tavily quotas | High | D39: sample briefings for visitors, access code for live runs, site-wide daily cap. |
| R2 | Hebrew quality: no Hebrew FTS stemming, RTL in UI and PDF, Hebrew writing quality of the LLM | Medium | Vector search covers Hebrew semantics. Early PDF spike. Hebrew eval cases. |
| R3 | Tavily free credits run out during development and evaluation | Medium | Mock Tavily in unit tests. Quick depth for dev. Credit logging. Cache search results in dev. |
| R14 | Free-tier dependence: Gemini rate limits and data-use terms, Tavily 1,000 credits/month, Hugging Face Space sleeping | Medium | Concurrency 1 (D18), throttled batching, sample data only, credit logging, wake the Space before demos. Provider-agnostic code allows moving to paid tiers. |
| R4 | Supabase free tier: invite email rate limit, project pauses after inactivity, storage/DB limits | Medium | Accept the invite email limit for the MVP (D28). Keep the project active (keepalive workflow). Small sample data. |
| R5 | Background runs lost when the backend sleeps or restarts | Medium | Always-on host (D15-A). Heartbeat + stale-run recovery marks runs partial/failed. |
| R6 | Hallucinated facts or citations pointing to sources that weren't retrieved | High | Claims may only reference source IDs present in the run. Validation rejects unknown IDs. Quality checks. |
| R7 | **Prompt injection from web pages and documents** (fetched text telling the agent what to do) | Medium | Treat fetched content as data in prompts. Agents have no write tools. Output schema validation. |
| R8 | Misuse of the service_role key bypasses RLS | High | Admin client used only in services after explicit permission checks. Code review + RLS tests. |
| R9 | Wrong company identified (common names, Hebrew/English transliteration) | Medium | Confirmation step. Show domain + country of candidates. |
| R10 | Embedding lock-in (D9) | Medium | Approve before Phase 2. Store model name + dimension per chunk. |
| R11 | Library API changes (LangGraph, Supabase client) | Low | Pinned versions (D5). |
| R12 | Personal data about key people | Medium | Public professional information only. Prompt rule + eval check. |
| R13 | LLM rate limits when agents run in parallel and several runs run at once | Low | Concurrency limit (D18). Retries with backoff. |
