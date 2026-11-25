"""Run persistence (migration 20261109113829_research_runs.sql).

`SupabaseRunStore` writes with the service key (backend only, D39 §3). `MemoryRunStore` keeps the same data in
memory for tests and `--no-save` runs. The orchestrator wraps every call so a storage failure never breaks a
run (it becomes a warning). Batch inserts for sources, claims and usage (one request each).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.agents.contracts import Briefing, QualityReport, ResearchFindings, ResearchRequest, StageStatus
from app.agents.llm import UsageEvent


class RunStore(Protocol):
    def create_run(self, run_id: str, request: ResearchRequest, meta: dict) -> None: ...
    def save_stage(self, run_id: str, stage: StageStatus) -> None: ...
    def save_briefing(self, run_id: str, briefing: Briefing, markdown: str) -> str: ...
    def save_usage(self, run_id: str, events: list[UsageEvent]) -> None: ...
    def finish_run(self, run_id: str, status: str, error: str | None, totals: dict,
                   findings: ResearchFindings | None, quality: QualityReport | None) -> None: ...


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def run_row(run_id: str, request: ResearchRequest, meta: dict) -> dict:
    return {"id": run_id, "company": request.company, "request": request.model_dump(mode="json"),
            "status": "running", "depth": request.depth, "language": request.language,
            "meeting_type": request.meeting_type, "prompt_versions": meta.get("prompt_versions", {}),
            "depth_config": meta.get("depth_config", {})}


def stage_row(run_id: str, st: StageStatus) -> dict:
    return {"run_id": run_id, "stage": st.stage, "status": st.status, "detail": st.detail,
            "attempts": st.attempts, "started_at": _iso(st.started_at), "finished_at": _iso(st.finished_at)}


def briefing_rows(run_id: str, b: Briefing, markdown: str) -> tuple[dict, list[dict], list[dict]]:
    briefing = {"run_id": run_id, "company": b.meta.company, "language": b.meta.language,
                "meeting_type": b.meta.meeting_type, "content": b.model_dump(mode="json"), "markdown": markdown,
                "is_partial": b.meta.is_partial}
    sources = [{"ref": s.id, "position": n, "kind": s.kind, "title": s.title, "url": s.url, "outlet": s.outlet,
                "published_at": _iso(s.published_at), "tier": s.tier, "source_type": s.source_type,
                "language": s.language, "citation": s.citation, "document_id": s.document_id,
                "document_version": s.version} for n, s in enumerate(b.sources, 1)]
    claims = [{"section": "summary", "position": n, "text": c.text, "info_type": c.info_type,
               "source_refs": c.source_ids, "confidence": c.confidence, "is_conflict": c.is_conflict,
               "conflicting_refs": c.conflicting_source_ids, "importance": None} for n, c in enumerate(b.summary)]
    for s in b.sections:
        pos = 0
        for c in s.claims:
            claims.append({"section": s.key, "position": pos, "text": c.text, "info_type": c.info_type,
                           "source_refs": c.source_ids, "confidence": c.confidence, "is_conflict": c.is_conflict,
                           "conflicting_refs": c.conflicting_source_ids, "importance": None})
            pos += 1
        for i in s.insights:
            claims.append({"section": s.key, "position": pos, "text": f"{i.title}: {i.description}",
                           "info_type": "ai_analysis", "source_refs": i.evidence_source_ids,
                           "confidence": i.confidence, "is_conflict": False, "conflicting_refs": [],
                           "importance": i.importance})
            pos += 1
    return briefing, sources, claims


def finish_row(status: str, error: str | None, totals: dict, findings: ResearchFindings | None,
               quality: QualityReport | None) -> dict:
    return {"status": status, "error": error, "finished_at": datetime.now(timezone.utc).isoformat(),
            "llm_calls": totals.get("llm_calls", 0), "input_tokens": totals.get("input_tokens", 0),
            "output_tokens": totals.get("output_tokens", 0), "tavily_credits": totals.get("tavily_credits", 0),
            "search_languages": findings.search_languages if findings else [],
            "rounds": findings.rounds if findings else 0,
            "quality": quality.model_dump(mode="json") if quality else None}


def usage_rows(run_id: str, events: list[UsageEvent]) -> list[dict]:
    return [{"run_id": run_id, "kind": e.kind, "agent": e.agent, "model": e.model, "input_tokens": e.input_tokens,
             "output_tokens": e.output_tokens, "credits": e.credits} for e in events]


class MemoryRunStore:
    def __init__(self):
        self.runs: dict[str, dict] = {}
        self.stages: dict[tuple[str, str], dict] = {}
        self.briefings: dict[str, dict] = {}
        self.sources: list[dict] = []
        self.claims: list[dict] = []
        self.usage: list[dict] = []
        self.demo_runs = 0

    def create_run(self, run_id, request, meta):
        self.runs[run_id] = run_row(run_id, request, meta)

    def save_stage(self, run_id, stage):
        self.stages[(run_id, stage.stage)] = stage_row(run_id, stage)

    def save_briefing(self, run_id, briefing, markdown):
        row, sources, claims = briefing_rows(run_id, briefing, markdown)
        bid = f"briefing-{len(self.briefings) + 1}"
        self.briefings[bid] = {**row, "id": bid, "is_sample": False}
        self.sources += [{**s, "briefing_id": bid} for s in sources]
        self.claims += [{**c, "briefing_id": bid} for c in claims]
        return bid

    def save_usage(self, run_id, events):
        self.usage += usage_rows(run_id, events)

    def finish_run(self, run_id, status, error, totals, findings, quality):
        self.runs.setdefault(run_id, {"id": run_id}).update(finish_row(status, error, totals, findings, quality))

    def claim_demo_run(self, cap: int) -> bool:
        if self.demo_runs >= cap:
            return False
        self.demo_runs += 1
        return True

    def demo_runs_today(self) -> int:
        return self.demo_runs


class SupabaseRunStore:
    def __init__(self, client=None):
        if client is None:
            from app.db.clients import get_admin_client
            client = get_admin_client()
        self.db = client

    def create_run(self, run_id, request, meta):
        self.db.table("research_runs").insert(run_row(run_id, request, meta)).execute()

    def save_stage(self, run_id, stage):
        self.db.table("run_stages").upsert(stage_row(run_id, stage), on_conflict="run_id,stage").execute()

    def save_briefing(self, run_id, briefing, markdown):
        row, sources, claims = briefing_rows(run_id, briefing, markdown)
        bid = self.db.table("briefings").insert(row).execute().data[0]["id"]
        if sources:
            self.db.table("sources").insert([{**s, "briefing_id": bid} for s in sources]).execute()
        if claims:
            self.db.table("claims").insert([{**c, "briefing_id": bid} for c in claims]).execute()
        return bid

    def save_usage(self, run_id, events):
        rows = usage_rows(run_id, events)
        if rows:
            self.db.table("usage_events").insert(rows).execute()

    def finish_run(self, run_id, status, error, totals, findings, quality):
        self.db.table("research_runs").update(finish_row(status, error, totals, findings, quality)) \
            .eq("id", run_id).execute()

    # ---- reads (Phase 5 "recent briefings", Phase 6 samples) ----
    def recent_briefings(self, limit: int = 20, samples_only: bool = False) -> list[dict]:
        q = self.db.table("briefings").select("id, run_id, company, language, meeting_type, is_partial, "
                                              "is_sample, created_at")
        if samples_only:
            q = q.eq("is_sample", True)
        return q.order("created_at", desc=True).limit(limit).execute().data

    def get_briefing(self, briefing_id: str) -> dict | None:
        rows = self.db.table("briefings").select("*").eq("id", briefing_id).limit(1).execute().data
        return rows[0] if rows else None

    # ---- demo mode daily cap (Phase 6, migration 20261111120000_demo_usage.sql) ----
    def claim_demo_run(self, cap: int) -> bool:
        """Count one live run for today (Pacific date) if today's count is below `cap`. Atomic in SQL."""
        return bool(self.db.rpc("claim_demo_run", {"cap": cap}).execute().data)

    def demo_runs_today(self) -> int:
        return int(self.db.rpc("demo_runs_today", {}).execute().data or 0)
