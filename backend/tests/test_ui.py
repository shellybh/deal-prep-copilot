"""Phase 5 Streamlit UI: helpers in app/ui/view.py (no Streamlit) + app.py through Streamlit's AppTest with the
agents mocked (fake LLMs from test_orchestrator, no network, no Supabase)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agents import orchestrator
from app.agents.briefing import CompanyNotIdentified
from app.agents.contracts import STAGES, ResearchRequest, StageStatus
from app.agents.identify import Identification
from app.agents.llm import DAILY_QUOTA_MSG
from app.agents.orchestrator import run_research
from app.ui import view
from tests.test_orchestrator import REQ, make_deps

APP = str(Path(__file__).resolve().parents[2] / "app.py")


# ---------------------------------------------------------------- helpers

def test_stage_line_and_labels():
    line = view.stage_line(StageStatus(stage="internal_research", status="completed", detail="2 queries"))
    assert line == "✅ **Internal knowledge base**: 2 queries"
    assert view.stage_line(StageStatus(stage="quality_checks")) == "⏳ **Quality checks**"
    assert set(view.STAGE_LABELS) == set(STAGES)                      # every stage has a label


def test_rtl_only_for_hebrew_and_markdown_kept():
    md = "# T\n\nline one\nline two\n\n- item\n"
    he, html = view.briefing_markdown(md, "he")
    assert html and he.startswith('<div dir="rtl"') and he.rstrip().endswith("</div>")
    assert "\n\n# T" in he                                           # blank line: Markdown inside still renders
    en, html_en = view.briefing_markdown(md, "en")
    assert not html_en and "dir=" not in en


def test_for_streamlit_hard_breaks_plain_lines_only():
    md = "info line\nGoal: x\n\n## Sources\n\n[1] a\n[2] b\n- bullet\n- bullet 2"
    out = view.for_streamlit(md).splitlines()
    assert out[0] == "info line  " and out[1] == "Goal: x"          # last line before a blank: no break
    assert out[5] == "[1] a  " and out[6] == "[2] b  "
    assert out[7] == "- bullet"                                      # list items untouched


def test_error_messages():
    nid = CompanyNotIdentified(Identification("Zorbex", None, False))
    assert view.error_message(nid) == view.Message("warning", view.NOT_IDENTIFIED_TEXT)
    with pytest.raises(ValidationError) as e:
        ResearchRequest(company="")
    msg = view.error_message(e.value)
    assert msg.level == "error" and "company" in msg.text
    quota = RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    assert view.error_message(quota).text == view.QUOTA_TEXT
    other = view.error_message(KeyError("secret internals"))
    assert other.text == view.UNEXPECTED_TEXT and "secret" not in other.text


def _result(status, stages=(), error=None):
    return SimpleNamespace(status=status, error=error, stages=[StageStatus(stage=s, status=st, detail=d)
                                                               for s, st, d in stages])


def test_result_messages():
    assert view.result_message(_result("completed")) is None
    failed = view.result_message(_result("failed", error="writer failed"))
    assert failed.level == "error" and "writer failed" in failed.text
    quota = view.result_message(_result("failed", [("strategic_analysis", "failed", DAILY_QUOTA_MSG)]))
    assert quota.text == view.QUOTA_TEXT
    partial = view.result_message(_result("partial", [("strategic_analysis", "failed", "boom"),
                                                      ("internal_research", "completed", None)]))
    assert partial.level == "warning" and "Strategic analysis" in partial.text and "Internal" not in partial.text


def test_run_footer_from_a_real_mocked_run():
    r = run_research(REQ, make_deps())
    text = view.run_footer(r)
    assert "LLM calls" in text and "internal" in text and "cited" in text and "sections missing" in text


def test_briefing_label_and_file_name():
    row = {"company": "monday.com", "language": "he", "meeting_type": "sales", "is_partial": True,
           "created_at": "2026-11-10T08:30:00+00:00"}
    assert view.briefing_label(row) == "monday.com · HE · Sales opportunity · 2026-11-10 · partial"
    assert view.briefing_label({**row, "created_at": "garbage", "is_partial": False}).endswith("· garbage")
    assert view.file_name("monday.com", "he") == "monday_com_he_briefing.md"


# ---------------------------------------------------------------- app.py (AppTest)

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


class FakeStore:
    def __init__(self, rows=None, fail=False, used=0, counter_fails=False):
        self.rows, self.fail, self.saved = rows or [], fail, {}
        self.used, self.counter_fails, self.claims = used, counter_fails, []

    def recent_briefings(self, limit=20, samples_only=False, run_ids=None):
        if self.fail:
            raise ConnectionError("db down")
        rows = [r for r in self.rows if r.get("is_sample")] if samples_only else self.rows
        return [r for r in rows if r.get("run_id") in run_ids] if run_ids is not None else rows

    def save_briefing(self, run_id, briefing, markdown, *a):   # list the new run like Supabase would
        self.rows.insert(0, {"id": f"b-{run_id}", "run_id": run_id, "company": briefing.meta.company,
                             "language": "en", "meeting_type": "sales", "is_partial": False,
                             "is_sample": False, "created_at": "2026-11-26T09:00:00+00:00",
                             "markdown": markdown})

    def claim_demo_run(self, cap):
        self.claims.append(cap)
        if self.counter_fails:
            raise ConnectionError("db down")
        if self.used >= cap:
            return False
        self.used += 1
        return True

    def demo_runs_today(self):
        return self.used

    def get_briefing(self, briefing_id):
        return next((r for r in self.rows if r["id"] == briefing_id), None)

    # RunStore writes (ignored)
    def create_run(self, *a): pass
    def save_stage(self, *a): pass
    def save_usage(self, *a): pass
    def finish_run(self, *a): pass


@pytest.fixture
def app(monkeypatch):
    """AppTest factory: `app(store=..., run=...)`. `run` replaces run_research(request, deps, on_stage)."""
    import streamlit as st
    from app.agents import store as store_mod

    def make(store=None, run=None, store_error=False, demo=None):
        """`demo`: env for demo mode, e.g. {"DEMO_MODE": "on", "DEMO_ACCESS_CODE": "s3cret"}. Default: off."""
        st.cache_resource.clear()
        env = {"DEMO_MODE": "off", "DEMO_ACCESS_CODE": "", "DEMO_DAILY_CAP": "4", **(demo or {})}
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        if store_error:
            def boom():
                raise RuntimeError("SUPABASE_URL missing")
            monkeypatch.setattr(store_mod, "SupabaseRunStore", boom)
        else:
            monkeypatch.setattr(store_mod, "SupabaseRunStore", lambda: store or FakeStore())
        if run is not None:
            monkeypatch.setattr(orchestrator, "run_research", run)
        return AppTest.from_file(APP, default_timeout=30)
    return make


def mocked_run(request, deps, on_stage=None):
    return run_research(request, make_deps(store=deps.store), on_stage=on_stage)


def submit(at, company="Acme", website="acme.com", language="en"):
    at.text_input(key="company").input(company)
    at.text_input(key="website").input(website)
    at.selectbox(key="language").set_value(language)
    at.button(key="submit").click()
    return at.run()


def all_markdown(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_app_completed_run_shows_progress_and_briefing(app):
    at = app(run=mocked_run).run()
    assert not at.exception and at.title[0].value == "Deal-Prep Copilot"
    at = submit(at)
    assert not at.exception
    text = all_markdown(at)
    assert "# Deal-Prep Briefing: Acme" in text and "## One-page summary" in text
    assert "✅ **Quality checks**" in text                                  # stage progress
    assert "dir=\"rtl\"" not in text
    assert any("LLM calls" in c.value for c in at.caption)


def test_progress_box_stays_open_while_running(app, monkeypatch):
    # Streamlit 1.67: update(label=...) without `expanded` re-sends the box with the field cleared and the browser
    # collapses it, so the stage list was hidden during live runs (2026-11-27). Every update must say expanded.
    from streamlit.elements.lib.mutable_status_container import StatusContainer
    calls, real = [], StatusContainer.update

    def spy(self, **kw):
        calls.append(kw)
        return real(self, **kw)
    monkeypatch.setattr(StatusContainer, "update", spy)
    at = submit(app(run=mocked_run).run())
    assert not at.exception
    running = [c for c in calls if c.get("state") is None]                   # stage-label updates during the run
    assert running and all(c.get("expanded") is True for c in running)


def test_app_hebrew_briefing_is_rtl(app):
    at = submit(app(run=mocked_run).run(), language="he")
    assert not at.exception
    assert any(m.value.startswith('<div dir="rtl"') and "תדריך הכנה לפגישה" in m.value for m in at.markdown)


def test_app_not_identified_shows_warning_and_no_briefing(app):
    def run(request, deps, on_stage=None):
        raise CompanyNotIdentified(Identification(request.company, None, False))
    at = submit(app(run=run).run(), company="Zorbex Dynamics", website="")
    assert not at.exception
    assert [w.value for w in at.warning] == [view.NOT_IDENTIFIED_TEXT]
    assert "Deal-Prep Briefing" not in all_markdown(at)


def test_app_unexpected_error_does_not_crash(app):
    def run(request, deps, on_stage=None):
        raise KeyError("internal detail")
    at = submit(app(run=run).run())
    assert not at.exception
    assert [e.value for e in at.error] == [view.UNEXPECTED_TEXT]


def test_app_failed_run_on_quota(app):
    def run(request, deps, on_stage=None):
        r = run_research(request, make_deps(store=deps.store))
        r.status, r.markdown, r.briefing = "failed", None, None
        r.stages[4].status, r.stages[4].detail = "failed", DAILY_QUOTA_MSG
        return r
    at = submit(app(run=run).run())
    assert not at.exception and [e.value for e in at.error] == [view.QUOTA_TEXT]


def test_app_empty_company_is_rejected_without_a_run(app):
    def run(*a, **k):
        raise AssertionError("must not run")
    at = submit(app(run=run).run(), company="  ")
    assert not at.exception and [e.value for e in at.error] == ["Please enter a company name."]


def test_app_db_down_still_renders_form(app):
    at = app(store=FakeStore(fail=True)).run()
    assert not at.exception
    assert any("Couldn't load recent briefings" in c.value for c in at.sidebar.caption)
    assert at.button(key="submit") is not None

    at = app(store_error=True).run()
    assert not at.exception
    assert any("unavailable" in c.value for c in at.sidebar.caption)


def test_app_opens_saved_briefing_from_sidebar(app):
    row = {"id": "b1", "run_id": "r1", "company": "Wix", "language": "he", "meeting_type": "partnership",
           "is_partial": False, "is_sample": False, "created_at": "2026-11-10T09:00:00+00:00",
           "markdown": "# תדריך הכנה לפגישה: Wix\n\n- שורה [1]\n"}
    at = app(store=FakeStore(rows=[row])).run()
    at.sidebar.button(key="saved_b1").click()
    at = at.run()
    assert not at.exception
    assert any(m.value.startswith('<div dir="rtl"') and "Wix" in m.value for m in at.markdown)


# ---------------------------------------------------------------- Phase 6: demo mode (D39 §2)

from app.core.config import DemoSettings, demo_settings  # noqa: E402

CODE = "s3cret-code"
DEMO_ON = {"DEMO_MODE": "on", "DEMO_ACCESS_CODE": CODE, "DEMO_DAILY_CAP": "2"}
SAMPLE = {"id": "s1", "run_id": "r1", "company": "Snowflake", "language": "en", "meeting_type": "sales",
          "is_partial": False, "is_sample": True, "created_at": "2026-11-12T09:00:00+00:00",
          "markdown": "# Deal-Prep Briefing: Snowflake\n\n- sample line [1]\n"}
PRIVATE = {**SAMPLE, "id": "p1", "company": "Private Co", "is_sample": False,
           "markdown": "# Deal-Prep Briefing: Private Co\n"}


def test_demo_settings_fail_closed(monkeypatch):
    for k in ("DEMO_MODE", "DEMO_ACCESS_CODE", "DEMO_DAILY_CAP"):
        monkeypatch.delenv(k, raising=False)
    cfg = demo_settings()
    assert cfg.mode and cfg.access_code == "" and cfg.daily_cap == 4          # on unless explicitly off
    assert CODE not in repr(DemoSettings(True, CODE))                         # secret kept out of repr
    for off in ("off", "false", "0", "NO"):
        monkeypatch.setenv("DEMO_MODE", off)
        assert not demo_settings().mode
    monkeypatch.setenv("DEMO_DAILY_CAP", "-3")
    assert demo_settings().daily_cap == 0


def test_check_access():
    on = DemoSettings(True, CODE)
    assert view.check_access(CODE, on) == "ok"
    assert view.check_access(f"  {CODE} ", on) == "ok"
    assert view.check_access("wrong", on) == "wrong"
    assert view.check_access("", on) == "wrong" and view.check_access(None, on) == "wrong"
    assert view.check_access(CODE, DemoSettings(True, "")) == "disabled"     # no code configured: closed
    assert view.check_access(None, DemoSettings(False, "")) == "open"


def test_demo_texts():
    assert view.usage_line(5, 4) == "Live runs today: 4 / 4 (resets at 10:00 Israel time)"
    assert view.sample_caption(SAMPLE) == "Sample briefing · generated 2026-11-12 · not updated live"
    assert "NexaStream" in view.BANNER_TEXT


def test_memory_store_cap():
    from app.agents.store import MemoryRunStore
    s = MemoryRunStore()
    assert [s.claim_demo_run(2) for _ in range(3)] == [True, True, False] and s.demo_runs_today() == 2
    assert MemoryRunStore().claim_demo_run(0) is False


def never_run(*a, **k):
    raise AssertionError("run_research must not be called")


def test_demo_public_view_samples_only_and_newest_sample_shown(app):
    at = app(store=FakeStore(rows=[SAMPLE, PRIVATE]), run=never_run, demo=DEMO_ON).run()
    assert not at.exception
    assert at.sidebar.header[0].value == "Sample briefings"
    keys = [b.key for b in at.sidebar.button]
    assert "saved_s1" in keys and "saved_p1" not in keys                     # private briefings hidden
    assert any(view.BANNER_TEXT == i.value for i in at.info)
    assert any("sample line" in m.value for m in at.markdown)                 # first visit: a sample at once
    assert any(c.value == view.sample_caption(SAMPLE) for c in at.caption)
    assert at.text_input(key="access_code") is not None


def test_first_sample_prefers_newest_english(app):
    he = {**SAMPLE, "id": "h1", "company": "monday.com", "language": "he", "created_at": "2026-11-27T09:00:00+00:00",
          "markdown": "# תדריך: monday.com\n\n- שורת דוגמה\n"}
    assert view.first_sample([he, SAMPLE])["id"] == "s1"
    assert view.first_sample([he])["id"] == "h1"                              # no English sample: the newest
    at = app(store=FakeStore(rows=[he, SAMPLE]), run=never_run, demo=DEMO_ON).run()
    assert not at.exception
    assert any("sample line" in m.value for m in at.markdown)                 # the English one opens first
    assert not any("שורת דוגמה" in m.value for m in at.markdown)


def test_demo_no_or_wrong_code_runs_nothing(app):
    store = FakeStore(rows=[SAMPLE])
    at = submit(app(store=store, run=never_run, demo=DEMO_ON).run())
    assert not at.exception and [e.value for e in at.error] == [view.CODE_WRONG_TEXT]
    at.text_input(key="access_code").input("nope")
    at = submit(at)
    assert not at.exception and view.CODE_WRONG_TEXT in [e.value for e in at.error]
    assert store.claims == []                                                 # nothing counted


def test_demo_correct_code_runs_once_and_unlocks(app):
    store = FakeStore(rows=[SAMPLE, PRIVATE])
    calls = []

    def run(request, deps, on_stage=None):
        calls.append(request.company)
        return mocked_run(request, deps, on_stage)
    at = app(store=store, run=run, demo=DEMO_ON).run()
    at.text_input(key="access_code").input(CODE)
    at = submit(at)
    assert not at.exception and calls == ["Acme"] and store.claims == [2]
    assert "# Deal-Prep Briefing: Acme" in all_markdown(at)
    assert [h.value for h in at.sidebar.header] == ["Your briefings", "Sample briefings"]
    keys = [b.key for b in at.sidebar.button]
    assert keys[0].startswith("saved_b-") and "saved_s1" in keys             # own run first, then samples
    assert "saved_p1" not in keys                                             # other people's runs stay hidden
    assert any(c.value.startswith("Live runs today: 1 / 2") for c in at.sidebar.caption)
    at = at.run()                                                             # next interaction:
    assert not at.exception and not [t for t in at.text_input if t.key == "access_code"]   # no re-typing
    assert "# Deal-Prep Briefing: Acme" in all_markdown(at) and calls == ["Acme"]          # kept, no new run


def test_demo_cap_reached_blocks_the_run(app):
    store = FakeStore(rows=[SAMPLE, PRIVATE], used=2)
    at = app(store=store, run=never_run, demo=DEMO_ON).run()
    at.text_input(key="access_code").input(CODE)
    at = submit(at)
    assert not at.exception and [w.value for w in at.warning] == [view.CAP_TEXT]
    assert [h.value for h in at.sidebar.header] == ["Sample briefings"]      # code holder, no runs yet
    assert "saved_p1" not in [b.key for b in at.sidebar.button]


def test_glossary_in_sidebar(app):
    assert all(t in view.glossary_markdown() for t in ("**ARR**", "**TCO**", "**MAP**", "CRO"))
    at = app(store=FakeStore(rows=[SAMPLE]), demo=DEMO_ON).run()
    assert not at.exception
    assert at.sidebar.expander[-1].label == "Glossary"
    assert any("**ARR**" in m.value for m in at.sidebar.markdown)


def test_demo_invalid_form_is_not_counted(app):
    store = FakeStore(rows=[SAMPLE])
    at = app(store=store, run=never_run, demo=DEMO_ON).run()
    at.text_input(key="access_code").input(CODE)
    at = submit(at, company="  ")
    assert not at.exception and store.claims == []


def test_demo_fail_closed_without_code_or_counter(app):
    at = submit(app(store=FakeStore(rows=[SAMPLE]), run=never_run,
                    demo={"DEMO_MODE": "on", "DEMO_ACCESS_CODE": ""}).run())
    assert not at.exception and [w.value for w in at.warning] == [view.LIVE_DISABLED_TEXT]

    store = FakeStore(rows=[SAMPLE], counter_fails=True)
    at = app(store=store, run=never_run, demo=DEMO_ON).run()
    at.text_input(key="access_code").input(CODE)
    at = submit(at)
    assert not at.exception and [e.value for e in at.error] == [view.COUNTER_DOWN_TEXT]

    at = app(store_error=True, run=never_run, demo=DEMO_ON).run()            # DB down: form renders, no run
    assert not at.exception
    at.text_input(key="access_code").input(CODE)
    at = submit(at)
    assert not at.exception and [e.value for e in at.error] == [view.COUNTER_DOWN_TEXT]


def test_demo_mode_off_needs_no_code(app):
    store = FakeStore()
    at = submit(app(store=store, run=mocked_run, demo={"DEMO_MODE": "off"}).run())
    assert not at.exception and "# Deal-Prep Briefing: Acme" in all_markdown(at) and store.claims == []
    assert not at.info                                                         # no demo banner locally
    assert at.sidebar.header[0].value == "Recent briefings"                  # local dev: everything


# ---------------------------------------------------------------- mark_sample.py

class FakeTable:
    def __init__(self, rows):
        self.rows, self.op, self.filters = rows, None, {}

    def update(self, values):
        self.op = ("update", values)
        return self

    def select(self, cols):
        self.op = ("select", cols)
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def order(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def execute(self):
        hit = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        if self.op[0] == "update":
            for r in hit:
                r.update(self.op[1])
        return SimpleNamespace(data=hit)


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == "briefings"
        return FakeTable(self.rows)


def test_mark_sample_cli(capsys):
    import mark_sample
    db = FakeDB([dict(PRIVATE)])
    assert mark_sample.main(["p1"], db=db) == 0 and db.rows[0]["is_sample"] is True
    assert capsys.readouterr().out.startswith("marked: SAMPLE p1")
    assert mark_sample.main(["p1", "--off"], db=db) == 0 and db.rows[0]["is_sample"] is False
    assert mark_sample.main(["missing"], db=db) == 1
    assert mark_sample.main(["--list"], db=db) == 0 and "Private Co" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        mark_sample.main([], db=db)
