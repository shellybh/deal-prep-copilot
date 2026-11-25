"""Country → search languages (D37: Hebrew + English only in the MVP).

- Israel → Hebrew + English (full query set in both).
- Any other country → English, plus one Hebrew query to catch Israeli activity (all depths).
- `LOCAL_LANGUAGE` only tells the briefing which local language was *not* searched. Adding a supported
  language later = add it to SUPPORTED_LANGUAGES and give the country a row in FULL_LANGUAGES.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("en", "he")

# ISO 3166-1 alpha-2 → English name (query wording + Tavily `country`, which takes lowercase names).
COUNTRY_NAMES = {
    "IL": "Israel", "US": "United States", "GB": "United Kingdom", "CA": "Canada", "AU": "Australia",
    "IE": "Ireland", "NZ": "New Zealand", "IN": "India", "SG": "Singapore", "DE": "Germany", "AT": "Austria",
    "CH": "Switzerland", "FR": "France", "BE": "Belgium", "NL": "Netherlands", "ES": "Spain", "IT": "Italy",
    "PT": "Portugal", "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "FI": "Finland", "PL": "Poland",
    "JP": "Japan", "CN": "China", "KR": "South Korea", "BR": "Brazil", "MX": "Mexico", "AE": "United Arab Emirates",
}

# Local language of the country (only to report what wasn't searched).
LOCAL_LANGUAGE = {
    "IL": "he", "US": "en", "GB": "en", "CA": "en", "AU": "en", "IE": "en", "NZ": "en", "IN": "en", "SG": "en",
    "DE": "de", "AT": "de", "CH": "de", "FR": "fr", "BE": "fr", "NL": "nl", "ES": "es", "IT": "it", "PT": "pt",
    "SE": "sv", "NO": "no", "DK": "da", "FI": "fi", "PL": "pl", "JP": "ja", "CN": "zh", "KR": "ko", "BR": "pt",
    "MX": "es", "AE": "ar",
}

# Countries searched with the full query set in more than English.
FULL_LANGUAGES = {"IL": ("he", "en")}

_ALIASES = {
    "israel": "IL", "ישראל": "IL", "usa": "US", "united states": "US", "united states of america": "US",
    "america": "US", "ארצות הברית": "US", 'ארה"ב': "US", "ארהב": "US", "uk": "GB", "united kingdom": "GB",
    "great britain": "GB", "england": "GB", "britain": "GB", "בריטניה": "GB", "אנגליה": "GB", "canada": "CA",
    "קנדה": "CA", "australia": "AU", "אוסטרליה": "AU", "ireland": "IE", "אירלנד": "IE", "india": "IN",
    "הודו": "IN", "singapore": "SG", "סינגפור": "SG", "germany": "DE", "גרמניה": "DE", "austria": "AT",
    "אוסטריה": "AT", "switzerland": "CH", "שווייץ": "CH", "שוויץ": "CH", "france": "FR", "צרפת": "FR",
    "belgium": "BE", "בלגיה": "BE", "netherlands": "NL", "holland": "NL", "הולנד": "NL", "spain": "ES",
    "ספרד": "ES", "italy": "IT", "איטליה": "IT", "portugal": "PT", "פורטוגל": "PT", "sweden": "SE",
    "שוודיה": "SE", "norway": "NO", "נורווגיה": "NO", "denmark": "DK", "דנמרק": "DK", "finland": "FI",
    "פינלנד": "FI", "poland": "PL", "פולין": "PL", "japan": "JP", "יפן": "JP", "china": "CN", "סין": "CN",
    "south korea": "KR", "korea": "KR", "קוריאה": "KR", "brazil": "BR", "ברזיל": "BR", "mexico": "MX",
    "מקסיקו": "MX", "uae": "AE", "united arab emirates": "AE", "איחוד האמירויות": "AE", "new zealand": "NZ",
    "ניו זילנד": "NZ",
}


def normalize_country(raw: str | None) -> str | None:
    """ISO alpha-2 code for a country name / code in English or Hebrew, or None if unknown."""
    if not raw or not raw.strip():
        return None
    key = " ".join(raw.strip().lower().split())
    if len(key) == 2 and key.upper() in COUNTRY_NAMES:
        return key.upper()
    code = _ALIASES.get(key)
    if code is None:
        log.info("Unknown country %r: searching in English (+ one Hebrew query)", raw)
    return code


@dataclass(frozen=True)
class LanguagePlan:
    country_code: str | None
    full_languages: tuple[str, ...]    # languages with the full query set
    extra_hebrew_query: bool           # foreign company: one Hebrew query (D37)
    local_language: str | None         # None = country unknown
    local_language_searched: bool

    @property
    def search_languages(self) -> list[str]:
        langs = list(self.full_languages)
        if self.extra_hebrew_query and "he" not in langs:
            langs.append("he")
        return langs

    @property
    def tavily_country(self) -> str | None:
        name = COUNTRY_NAMES.get(self.country_code or "")
        return name.lower() if name else None


def language_plan(country: str | None) -> LanguagePlan:
    code = normalize_country(country)
    full = FULL_LANGUAGES.get(code or "", ("en",))
    local = LOCAL_LANGUAGE.get(code or "")
    extra_he = "he" not in full
    searched = local is not None and (local in full or (local == "he" and extra_he))
    return LanguagePlan(country_code=code, full_languages=full, extra_hebrew_query=extra_he,
                        local_language=local, local_language_searched=searched)
