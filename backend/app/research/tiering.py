"""Rule-based source type + credibility tier (D21 step 1). Config: `source_tiers.json`.

Order of rules: the company's own domain (official, tier 1) → government / regulators / exchanges
(tier 1) → listed domains → unknown (other, tier 4). Evidence-quality assessment is Phase 4 (LLM).
Preferred sources are never upgraded here: this module doesn't know about preferences.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("source_tiers.json")
SOURCE_TYPES = ("official", "news", "government_regulatory", "financial", "professional_industry", "other")
# Preferred categories → config groups used for targeted (include_domains) queries.
CATEGORY_GROUPS = {
    "news": ("news",),
    "official": ("official_wires",),
    "government_regulatory": ("government_regulatory",),
    "financial": ("financial",),
    "professional_industry": ("professional_industry",),
}


@dataclass(frozen=True)
class Classification:
    source_type: str
    tier: int


@lru_cache
def load_config(path: str | None = None) -> dict:
    data = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def classify_source(host: str | None, company_domain: str | None = None, config: dict | None = None) -> Classification:
    cfg = config or load_config()
    host = (host or "").lower().removeprefix("www.")
    if not host:
        return Classification("other", 4)
    if company_domain and _matches(host, company_domain.lower().removeprefix("www.")):
        return Classification("official", 1)
    gov = cfg.get("government_regulatory", {})
    if any(host.endswith(s) for s in gov.get("suffixes", [])) or any(_matches(host, d) for d in gov.get("domains", [])):
        return Classification("government_regulatory", int(gov.get("tier", 1)))
    # Most specific match wins (e.g. finance.yahoo.com listed, yahoo.com not = unknown).
    best: tuple[int, Classification] | None = None
    for group, spec in cfg.items():
        if group == "government_regulatory" or "tier" not in spec:
            continue
        for d in spec.get("domains", []):
            if _matches(host, d) and (best is None or len(d) > best[0]):
                best = (len(d), Classification(spec.get("source_type", group), int(spec["tier"])))
    return best[1] if best else Classification("other", 4)


def hebrew_media_domains(config: dict | None = None) -> list[str]:
    """Israeli Hebrew outlets for targeted Hebrew queries (D37). Not a tier group."""
    return list((config or load_config()).get("hebrew_media", {}).get("domains", []))


def category_domains(category: str, company_domain: str | None = None, config: dict | None = None) -> list[str]:
    """Domains for a preferred category. Unknown category → []. Search priority only."""
    cfg = config or load_config()
    groups = CATEGORY_GROUPS.get((category or "").strip().lower())
    if not groups:
        return []
    out: list[str] = []
    if category == "official" and company_domain:
        out.append(company_domain)
    for g in groups:
        out += cfg.get(g, {}).get("domains", [])
    return list(dict.fromkeys(out))
