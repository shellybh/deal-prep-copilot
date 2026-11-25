"""Quality checks (D21, D40 §3). Runs after writing; fixes what it can, reports the rest.

Deterministic checks:
- every section present (contract) and empty ones marked missing with a reason
- facts without a valid source -> relabeled `unverified`
- analysis / recommendations without a source -> dropped (grounding rule, Phase 3.5)
- info type vs source kind: an "external fact" that only cites internal docs is an internal fact, and back
- low-confidence and conflicting claims counted (shown in the briefing)
- duplicate cited sources (same normalized URL) merged, undated sources in Recent developments noted
- Hebrew words written partly in Arabic letters ("المחוונים") -> Hebrew; Arabic-only words listed in the notes

Two small-model calls (the judge, union of flags) remove generic statements that passed the prompt rules. If the judge fails,
the briefing is kept and the report says the check did not run.
"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.contracts import ANALYSIS_TYPES, FACT_TYPES, Briefing, GenericVerdict, QualityReport
from app.agents.llm import UsageLog, structured_call
from app.agents.registry import SourceRegistry
from app.agents.role_prompts import quality as PQ

log = logging.getLogger(__name__)
JUDGE_RUNS = 2  # judge calls per briefing (small model, D41); union of the flagged IDs
JUDGED_SECTIONS = ("business_opportunities", "risks_challenges", "meeting_strategy", "recommended_questions",
                   "next_steps", "internal_intelligence")


def deterministic_checks(b: Briefing, reg: SourceRegistry, report: QualityReport) -> None:
    def fix(claims):
        kept = []
        for c in claims:
            kinds = {reg.get(i).kind for i in c.source_ids if reg.get(i)}
            if c.info_type in FACT_TYPES:
                if not c.source_ids:
                    c.info_type = "unverified"
                    c.confidence = "low"
                    report.facts_without_source += 1
                elif c.info_type == "external_fact" and kinds == {"internal"}:
                    c.info_type = "internal_document"
                    report.info_type_relabeled += 1
                elif c.info_type == "internal_document" and kinds == {"external"}:
                    c.info_type = "external_fact"
                    report.info_type_relabeled += 1
            elif c.info_type in ANALYSIS_TYPES and not c.source_ids:
                report.uncited_analysis_dropped += 1
                continue
            kept.append(c)
        return kept

    b.summary = fix(b.summary)
    for s in b.sections:
        s.claims = fix(s.claims)
        before = len(s.insights)
        s.insights = [i for i in s.insights if i.evidence_source_ids]
        report.uncited_analysis_dropped += before - len(s.insights)
    for c in b.all_claims():
        report.conflicts += c.is_conflict
        report.low_confidence += c.confidence == "low"
    for s in b.sections:
        report.low_confidence += sum(i.confidence == "low" for i in s.insights)

    # duplicate cited sources: point every claim at one ID per normalized URL
    first: dict[str, str] = {}
    alias: dict[str, str] = {}
    for rec in reg.sources.values():
        if rec.normalized_url:
            if rec.normalized_url in first:
                alias[rec.id] = first[rec.normalized_url]
            else:
                first[rec.normalized_url] = rec.id
    if alias:
        for c in b.all_claims():
            new = list(dict.fromkeys(alias.get(i, i) for i in c.source_ids))
            report.duplicate_sources_merged += len(c.source_ids) - len(new)
            c.source_ids = new

    undated = {i for c in b.section("recent_developments").claims for i in c.source_ids
               if reg.get(i) and reg.get(i).kind == "external" and reg.get(i).published_at is None}
    if undated:
        report.notes.append(f"{len(undated)} undated source(s) cited in Recent developments (labeled date unknown).")
    fix_foreign_script(b, report)


# The model sometimes starts a Hebrew word with Arabic letters: "المחוונים" for "המחוונים", "المיוחד" for
# "המיוחד" (elbit 2026-11-16, monday.com 2026-11-24): the Arabic article "ال" for "ה", then Arabic letters for
# Hebrew ones, although the prompts forbid Arabic letters. A word that mixes the two scripts is always such an
# error: its Arabic letters are mapped to Hebrew. Words written only in Arabic are left and listed in the notes.
_ARABIC = "؀-ۿ"
_HEBREW = "א-ת"
_MIXED_WORD = re.compile(rf"[{_ARABIC}{_HEBREW}]*(?:[{_ARABIC}][{_ARABIC}{_HEBREW}]*[{_HEBREW}]|"
                         rf"[{_HEBREW}][{_ARABIC}{_HEBREW}]*[{_ARABIC}])[{_ARABIC}{_HEBREW}]*")
_ARABIC_WORD = re.compile(rf"\S*[{_ARABIC}]+\S*")
_AR_TO_HE = str.maketrans("ابتثجحخدذرزسشصضطظعغفقكلمنهوية" "أإآءى",
                          "אבתתגחחדדרזסשצצטטעגפקכלמנהויה" "אאאאי")


def _fix_mixed(m: re.Match) -> str:
    word = m.group(0)
    if word.startswith("ال"):          # Arabic article -> Hebrew "ה"
        word = "ה" + word[2:]
    return word.translate(_AR_TO_HE)


def fix_foreign_script(b: Briefing, report: QualityReport) -> None:
    """Arabic letters inside a Hebrew word -> Hebrew; Arabic-only words are left and listed in the notes."""
    fixed = 0
    left: list[str] = []

    def clean(text: str | None) -> str | None:
        nonlocal fixed
        if not text:
            return text
        text, n = _MIXED_WORD.subn(_fix_mixed, text)
        fixed += n
        left.extend(_ARABIC_WORD.findall(text))
        return text

    for c in b.all_claims():
        c.text = clean(c.text)
    for s in b.sections:
        s.missing_reason = clean(s.missing_reason)
        for i in s.insights:
            for attr in ("title", "description", "why_it_matters", "how_to_address", "importance_rationale"):
                setattr(i, attr, clean(getattr(i, attr)))
    if fixed:
        report.notes.append(f"Fixed {fixed} Hebrew word(s) written partly in Arabic letters.")
    if left:
        report.notes.append(f"Words with Arabic letters left in the text: {', '.join(dict.fromkeys(left))}.")


# Insight sub-lines judged on their own (title given for context). A generic sub-line is blanked, the insight stays.
INSIGHT_LINES = {"why": ("why_it_matters", "why it matters"), "how": ("how_to_address", "how to address"),
                 "rating": ("importance_rationale", "rating")}


def judge_generic(b: Briefing, company: str, llm: BaseChatModel, usage: UsageLog, report: QualityReport) -> None:
    items, where, lines = [], {}, {}
    for n, c in enumerate(b.summary):
        # user-provided items too: a summary line that only restates the meeting goal is generic
        if c.info_type in ANALYSIS_TYPES or c.info_type == "user_provided":
            items.append({"id": f"s{n}", "text": c.text})
            where[f"s{n}"] = ("summary", c)
    for s in b.sections:
        if s.key not in JUDGED_SECTIONS:
            continue
        for n, c in enumerate(s.claims):
            items.append({"id": f"{s.key}.c{n}", "text": c.text})
            where[f"{s.key}.c{n}"] = (s.key, c)
        for n, i in enumerate(s.insights):
            items.append({"id": f"{s.key}.i{n}", "text": f"{i.title}: {i.description}"})
            where[f"{s.key}.i{n}"] = (s.key, i)
            for suffix, (attr, label) in INSIGHT_LINES.items():
                if getattr(i, attr).strip():
                    line_id = f"{s.key}.i{n}.{suffix}"
                    items.append({"id": line_id, "text": f"[{i.title}] {label}: {getattr(i, attr)}"})
                    lines[line_id] = (s.key, i, attr, label)
    if not items:
        report.generic_check_ran = True
        return
    messages = [SystemMessage(PQ.SYSTEM.format(company=company)),
                HumanMessage(PQ.USER.format(items=json.dumps(items, ensure_ascii=False)))]
    verdict = structured_call(llm, GenericVerdict, messages, agent="quality", usage=usage)
    report.generic_check_ran = True
    # One judge run is noisy (eval: the same text scored 4 / 2 / 4): run it JUDGE_RUNS times on the small model
    # and drop what any run flags. A failed extra run keeps the verdicts already collected.
    for _ in range(JUDGE_RUNS - 1):
        try:
            extra = structured_call(llm, GenericVerdict, messages, agent="quality", usage=usage)
        except Exception as exc:
            log.warning("extra generic-judge run failed: %s", exc)
            break
        verdict.generic_ids = list(dict.fromkeys([*verdict.generic_ids, *extra.generic_ids]))
        verdict.reasons = {**extra.reasons, **verdict.reasons}
    drop = {i for i in verdict.generic_ids if i in where}
    for item_id in drop:
        key, obj = where[item_id]
        text = obj.text if hasattr(obj, "text") else obj.title
        reason = verdict.reasons.get(item_id, "")
        report.generic_dropped.append(f"{key}: {text}" + (f" ({reason})" if reason else ""))
    dropped_objs = {id(where[i][1]) for i in drop}
    for line_id in (i for i in verdict.generic_ids if i in lines):
        key, insight, attr, label = lines[line_id]
        if id(insight) in dropped_objs:
            continue
        reason = verdict.reasons.get(line_id, "")
        report.generic_dropped.append(f"{key}: {insight.title} ({label}): {getattr(insight, attr)}"
                                      + (f" ({reason})" if reason else ""))
        setattr(insight, attr, "")
    b.summary = [c for c in b.summary if id(c) not in dropped_objs]
    for s in b.sections:
        s.claims = [c for c in s.claims if id(c) not in dropped_objs]
        s.insights = [i for i in s.insights if id(i) not in dropped_objs]


def finalize_sections(b: Briefing, report: QualityReport) -> None:
    for s in b.sections:
        if s.is_empty and s.status == "complete":
            s.status = "missing_info"
            s.missing_reason = "only unsupported or generic statements were found"
        if s.status == "missing_info":
            report.sections_missing.append(s.key)


def run_quality_checks(b: Briefing, reg: SourceRegistry, company: str, judge_llm: BaseChatModel | None,
                       usage: UsageLog, report: QualityReport | None = None) -> QualityReport:
    report = report or b.quality
    deterministic_checks(b, reg, report)
    if judge_llm is not None:
        try:
            judge_generic(b, company, judge_llm, usage, report)
        except Exception as exc:  # the briefing is still valid without this check
            log.warning("generic-statement judge failed: %s", exc)
            report.notes.append(f"Generic-statement check did not run ({type(exc).__name__}).")
    finalize_sections(b, report)
    b.quality = report
    return report
