"""Deal-Prep Copilot: Streamlit UI (Phase 5, D39) + public demo mode (Phase 6, D39 §2).

A thin layer over the Phase 4 entry point `run_research(request, on_stage=...)`: form -> stage-by-stage
progress -> briefing (RTL for Hebrew), plus a sidebar list read from Supabase.
Demo mode (on unless DEMO_MODE=off): visitors see sample briefings (`is_sample`); a live run needs the access
code (DEMO_ACCESS_CODE) and a free slot in the site-wide daily cap (DEMO_DAILY_CAP, counted in Supabase).
UI logic lives in `backend/app/ui/view.py`. Run from the repo root: `streamlit run app.py`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# The backend package is also called `app`: put backend/ first so `import app` never resolves to this file.
BACKEND = Path(__file__).resolve().parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import streamlit as st  # noqa: E402


def _secrets_to_env() -> None:
    """Streamlit Cloud: make root-level secrets visible to core/config.py (which reads env vars). Values already
    in the environment win. No secrets file locally -> nothing to do (.env is used)."""
    try:
        items = dict(st.secrets)
    except Exception:
        return
    for key, value in items.items():
        if isinstance(value, (str, int, float, bool)) and not os.environ.get(key):
            os.environ[key] = str(value)


_secrets_to_env()

from app.agents import orchestrator  # noqa: E402
from app.agents.contracts import ResearchRequest  # noqa: E402
from app.agents.orchestrator import Deps  # noqa: E402
from app.agents.store import MemoryRunStore  # noqa: E402
from app.core.config import demo_settings  # noqa: E402
from app.ui import view  # noqa: E402

st.set_page_config(page_title="Deal-Prep Copilot", page_icon="🤝", layout="wide")
demo = demo_settings()


# ---------- store (Supabase if reachable, else in memory) ----------
@st.cache_resource(show_spinner=False)
def get_store():
    """(store, error). The UI keeps working without the DB; briefings just aren't saved or listed."""
    try:
        from app.agents.store import SupabaseRunStore
        return SupabaseRunStore(), None
    except Exception as exc:  # missing keys, network
        error = f"{type(exc).__name__}: {str(exc)[:150]}"
        view.log.warning("Supabase store unavailable: %s", error)   # once per process (cached), no key values
        return None, error


def show_message(msg: view.Message | None) -> None:
    if msg:
        getattr(st, msg.level)(msg.text)


def show_briefing(markdown: str, language: str, company: str, key: str) -> None:
    body, html = view.briefing_markdown(markdown, language)
    st.download_button("Download Markdown", markdown, file_name=view.file_name(company, language),
                       mime="text/markdown", key=f"dl_{key}", on_click="ignore")
    st.markdown(body, unsafe_allow_html=html)


def unlocked() -> bool:
    """Live runs allowed in this session: demo mode off, or the right code was entered once."""
    return not demo.mode or st.session_state.get("unlocked", False)


store, store_error = get_store()

# ---------- form ----------
st.title("Deal-Prep Copilot")
st.caption("Research a company before a sales or partnership meeting: public sources + our internal "
           "knowledge base, every fact cited.")
if demo.mode:
    st.info(view.BANNER_TEXT)

with st.form("briefing_form"):
    c1, c2 = st.columns(2)
    company = c1.text_input("Company *", placeholder="e.g. Snowflake", key="company")
    website = c2.text_input("Website (optional)", placeholder="e.g. snowflake.com", key="website",
                            help="Helps identify the right company when the name is ambiguous.")
    c3, c4, c5 = st.columns(3)
    meeting_type = c3.selectbox("Meeting type", list(view.MEETING_LABELS),
                                format_func=view.MEETING_LABELS.get)
    language = c4.selectbox("Briefing language", list(view.LANGUAGE_LABELS),
                            format_func=view.LANGUAGE_LABELS.get, key="language")
    depth = c5.selectbox("Depth", list(view.DEPTH_LABELS), index=1, format_func=view.DEPTH_LABELS.get)
    goal = st.text_area("Meeting goal", placeholder="e.g. first discovery call about real-time analytics",
                        height=80)
    with st.expander("More options"):
        country = st.text_input("Country (optional)", placeholder="e.g. United States")
        context = st.text_area("What you already know (optional)", height=80,
                               help="Shown in the briefing labeled as user-provided.")
        context_type = st.selectbox("This information is", list(view.CONTEXT_TYPE_LABELS),
                                    format_func=view.CONTEXT_TYPE_LABELS.get)
    code = None
    if not unlocked():
        code = st.text_input("Access code", type="password", key="access_code", help=view.CODE_HELP)
    submitted = st.form_submit_button("Prepare briefing", type="primary", key="submit")


def may_run() -> bool:
    """Access code, then the daily cap (claimed only when everything else is valid). Shows the reason if not."""
    if not unlocked():
        access = view.check_access(code, demo)
        if access == "disabled":
            st.warning(view.LIVE_DISABLED_TEXT)
            return False
        if access == "wrong":
            st.error(view.CODE_WRONG_TEXT)
            return False
        st.session_state["unlocked"] = True
    if not demo.mode:
        return True
    if store is None:                       # fail closed: no counter, no live run
        st.error(view.COUNTER_DOWN_TEXT)
        return False
    try:
        claimed = store.claim_demo_run(demo.daily_cap)
    except Exception as exc:
        view.log.warning("claim_demo_run failed: %s", exc)
        st.error(view.COUNTER_DOWN_TEXT)
        return False
    if not claimed:
        st.warning(view.CAP_TEXT)
    return claimed


# ---------- run ----------
if submitted:
    st.session_state.pop("result", None)
    st.session_state["view"] = {"kind": "new"}
    request = None
    if not company.strip():
        st.error("Please enter a company name.")
    else:
        try:
            request = ResearchRequest(
                company=company, website=website.strip() or None, meeting_type=meeting_type,
                meeting_goal=goal, language=language, depth=depth, country=country,
                user_context=context or None, user_context_type=context_type if context.strip() else None)
        except Exception as exc:  # validation: shown, nothing counted
            show_message(view.error_message(exc))
    if request is None or not may_run():
        st.session_state.pop("view")
    else:
        stages: dict = {}
        with st.status(f"Researching {request.company}…", expanded=True) as status:
            box = st.empty()

            def on_stage(s) -> None:
                stages[s.stage] = s
                box.markdown(view.stage_lines(stages.values()))
                if s.status == "in_progress":
                    status.update(label=f"{view.stage_label(s.stage)}…")

            try:
                result = orchestrator.run_research(request, Deps(store=store or MemoryRunStore()),
                                                   on_stage=on_stage)
            except Exception as exc:  # not identified, anything unexpected: never crash the page
                status.update(label="Stopped", state="error", expanded=True)
                show_message(view.error_message(exc))
            else:
                st.session_state["result"] = result
                st.session_state.setdefault("my_runs", []).append(result.run_id)   # this session's own runs
                done = result.status == "completed"
                status.update(label=f"{'Done' if done else result.status.capitalize()} in {result.duration_s:.0f} s",
                              state="complete" if result.status != "failed" else "error", expanded=not done)

# ---------- sidebar ----------
# Demo mode: everyone sees the samples; a code holder also sees the briefings of their own runs in this session,
# never other visitors' runs. Local dev (demo mode off): all recent briefings.
# Drawn after the run, so a run that just finished is already listed, with the new count.
def briefing_buttons(header: str, fetch, empty: str | None) -> list[dict] | None:
    st.header(header)
    try:
        found = fetch()
    except Exception as exc:
        st.caption("Couldn't load recent briefings.")
        view.log.warning("recent_briefings failed: %s", exc)
        return None
    if not found and empty:
        st.caption(empty)
    for row in found:
        if st.button(view.briefing_label(row), key=f"saved_{row['id']}", width="stretch"):
            st.session_state["view"] = {"kind": "saved", "id": row["id"]}
            st.session_state.pop("result", None)
    return found


rows: list[dict] | None = None
with st.sidebar:
    if store is None:
        st.header("Sample briefings" if demo.mode else "Recent briefings")
        st.caption("Briefing history is unavailable (database not reachable). New briefings won't be saved.")
    elif not demo.mode:
        rows = briefing_buttons("Recent briefings", lambda: store.recent_briefings(limit=20), "No briefings yet.")
    else:
        my_runs = st.session_state.get("my_runs", [])
        if my_runs:
            briefing_buttons("Your briefings", lambda: store.recent_briefings(limit=20, run_ids=my_runs), None)
        rows = briefing_buttons("Sample briefings", lambda: store.recent_briefings(limit=20, samples_only=True),
                                "No sample briefings yet.")
        if unlocked():
            try:
                st.caption(view.usage_line(store.demo_runs_today(), demo.daily_cap))
            except Exception as exc:
                view.log.warning("demo_runs_today failed: %s", exc)
    st.space("large")                         # set apart from the briefing list: it's a reference card, not a briefing
    with st.container(key="glossary"):
        with st.expander("Glossary", icon=":material/menu_book:"):
            st.markdown(view.glossary_markdown())

# The only custom CSS: a light card for the glossary on the navy sidebar (scoped to the container's key class).
st.html(f"<style>{view.GLOSSARY_CSS}</style>")

# ---------- view ----------
current = st.session_state.get("view")
if current is None and not submitted and rows and demo.mode and not unlocked():
    current = {"kind": "saved", "id": view.first_sample(rows)["id"]}   # first visit: newest English sample
current = current or {}
if current.get("kind") == "new" and "result" in st.session_state:
    r = st.session_state["result"]
    show_message(view.result_message(r))
    if r.markdown:
        st.caption(view.run_footer(r) + ("" if store else " · not saved (no database)"))
        show_briefing(r.markdown, r.request.language, r.request.company, r.run_id)
elif current.get("kind") == "saved" and store is not None:
    try:
        row = store.get_briefing(current["id"])
    except Exception as exc:
        row = None
        view.log.warning("get_briefing failed: %s", exc)
    if row is None:
        st.error("Couldn't load this briefing.")
    else:
        st.caption(view.sample_caption(row) if row.get("is_sample") else f"Saved briefing · {view.briefing_label(row)}")
        if row.get("is_partial"):
            st.warning("Partial briefing: some research stages failed when it was created.")
        show_briefing(row["markdown"], row["language"], row["company"], row["id"])
