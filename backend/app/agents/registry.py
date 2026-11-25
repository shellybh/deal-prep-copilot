"""Source registry for one run: every source a tool returned, under a short ID the models cite (I1, W1).

Short IDs keep prompts small and make citation checks exact: a claim may only cite an ID in this registry
(R6). Web sources are deduplicated by normalized URL across tool calls and research rounds.
"""
from __future__ import annotations

from app.agents.contracts import FindingsSectionName, ResearchFindings, SourceRecord
from app.research.sources import Source

SNIPPET_CHARS = 500
CHUNK_CHARS = 1500
PAGE_CHARS = 3000
COMPETITOR_PURPOSES = {"competitors"}


class SourceRegistry:
    def __init__(self, company: str):
        self.findings = ResearchFindings(company=company)
        self._by_url: dict[str, str] = {}
        self._by_chunk: dict[str, str] = {}
        self._n = {"internal": 0, "external": 0}
        self.queried_purposes: set[str] = set()
        self.internal_queries: list[str] = []
        self.budget_exhausted = False

    @property
    def sources(self) -> dict[str, SourceRecord]:
        return self.findings.sources

    def get(self, sid: str) -> SourceRecord | None:
        return self.findings.sources.get(sid)

    def _new_id(self, kind: str) -> str:
        self._n[kind] += 1
        return ("I" if kind == "internal" else "W") + str(self._n[kind])

    def _attach(self, rec: SourceRecord) -> None:
        self.findings.sources[rec.id] = rec
        section = self.findings.section(rec.section)
        if rec.id not in section.source_ids:
            section.source_ids.append(rec.id)

    def add_internal(self, chunk: dict) -> SourceRecord:
        key = f"{chunk.get('document_id')}|{chunk.get('citation')}"
        if key in self._by_chunk:
            return self.sources[self._by_chunk[key]]
        rec = SourceRecord(id=self._new_id("internal"), kind="internal", section="internal",
                           title=chunk.get("file_name") or chunk["citation"], citation=chunk["citation"],
                           file_name=chunk.get("file_name"), document_id=chunk.get("document_id"),
                           version=chunk.get("version"), text=(chunk.get("content") or "")[:CHUNK_CHARS])
        self._by_chunk[key] = rec.id
        self._attach(rec)
        return rec

    def add_web(self, s: Source, section: FindingsSectionName | None = None) -> SourceRecord:
        if section is None:
            section = "competitive" if set(s.query_purposes) & COMPETITOR_PURPOSES else "web"
        existing = self._by_url.get(s.normalized_url)
        if existing:
            rec = self.sources[existing]
            rec.purposes = sorted(set(rec.purposes) | set(s.query_purposes))
            for u in s.also_reported_by:
                if u not in rec.also_reported_by:
                    rec.also_reported_by.append(u)
            if s.content and len(s.content) > len(rec.text):
                rec.text = s.content[:PAGE_CHARS]
            return rec
        rec = SourceRecord(
            id=self._new_id("external"), kind="external", section=section, title=s.title, url=s.url,
            normalized_url=s.normalized_url, outlet=s.outlet, published_at=s.published_at, tier=s.tier,
            source_type=s.source_type, window=s.window, language=s.language,
            also_reported_by=list(s.also_reported_by), purposes=list(s.query_purposes),
            text=(s.content or s.snippet or "")[:PAGE_CHARS if s.content else SNIPPET_CHARS])
        self._by_url[s.normalized_url] = rec.id
        self._attach(rec)
        return rec

    def set_page_text(self, sid: str, text: str) -> None:
        rec = self.get(sid)
        if rec and text:
            rec.text = text[:PAGE_CHARS]

    def with_purpose(self, purpose: str) -> list[SourceRecord]:
        return [r for r in self.sources.values() if purpose in r.purposes]

    def for_prompt(self, ids: list[str] | None = None) -> list[dict]:
        """Compact view of the sources for the analysis / writing prompts."""
        recs = [self.sources[i] for i in ids if i in self.sources] if ids is not None else list(self.sources.values())
        out = []
        for r in recs:
            d = {"id": r.id, "section": r.section, "title": r.title, "text": r.text}
            if r.kind == "internal":
                d["citation"] = r.citation
            else:
                d.update(outlet=r.outlet, tier=r.tier, type=r.source_type,
                         date=r.published_at.date().isoformat() if r.published_at else "date unknown")
                if r.window:
                    d["window"] = r.window
            out.append(d)
        return out
