"""URL normalization and duplicate detection.

- `normalize_url`: same page → same string (scheme/host case, `www.`, default ports, fragments, tracking
  parameters, trailing slash, AMP variants).
- `same_story`: near-duplicate titles (the same story across outlets or languages' wire copies), by
  token-set Jaccard similarity. Titles under 4 words never match (generic page titles, false corroboration).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ocid", "ref", "ref_src", "cmpid",
                   "igshid", "spm", "amp", "outputtype"}
TRACKING_PREFIXES = ("utm_",)
_DEFAULT_PORTS = {"http": 80, "https": 443}
_WORD = re.compile(r"[\w\u0590-\u05ff]+", re.UNICODE)
_SUFFIX_SEP = re.compile(r"\s+[-|–—:]\s+")
NEAR_DUP_THRESHOLD = 0.8
MIN_TOKENS_FOR_FUZZY = 4


def _host(netloc: str) -> str:
    host = netloc.rsplit("@", 1)[-1].lower()
    return host.removeprefix("www.")


def domain_of(url_or_domain: str | None) -> str | None:
    """Host without `www.` for a URL or a bare domain ('monday.com', 'https://www.monday.com/x')."""
    if not url_or_domain or not url_or_domain.strip():
        return None
    raw = url_or_domain.strip()
    if "://" not in raw:
        raw = "https://" + raw
    host = urlsplit(raw).hostname
    return host.lower().removeprefix("www.") if host else None


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme == "http":
        scheme = "https"                       # same page; avoids http/https duplicates
    host = _host(parts.netloc)
    if parts.port and parts.port != _DEFAULT_PORTS.get(parts.scheme.lower()):
        host = f"{host.split(':')[0]}:{parts.port}"
    else:
        host = host.split(":")[0]
    if host.startswith("amp."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    path = re.sub(r"/amp/?$", "/", path)
    if path != "/":
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)]
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


def title_tokens(title: str) -> set[str]:
    """Lower-case word tokens, outlet suffix removed ('Acme raises $5M - Reuters' → acme raises 5m)."""
    t = (title or "").strip()
    parts = _SUFFIX_SEP.split(t)
    if len(parts) > 1 and len(parts[-1].split()) <= 4:
        t = " ".join(parts[:-1])
    return {w for w in _WORD.findall(t.lower()) if len(w) > 1}


def same_story(title_a: str, title_b: str, threshold: float = NEAR_DUP_THRESHOLD) -> bool:
    a, b = title_tokens(title_a), title_tokens(title_b)
    if not a or not b:
        return False
    if min(len(a), len(b)) < MIN_TOKENS_FOR_FUZZY:
        return False   # 'monday.com', 'About us': generic page titles, not a story (would fake corroboration)
    return len(a & b) / len(a | b) >= threshold
