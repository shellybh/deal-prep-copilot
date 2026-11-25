"""Keyword part of hybrid search (D10). The 'simple' FTS config has no stop words, and hybrid_search
OR-s the query terms, so words like "what / is / the" or "מה / של / את" match almost every chunk and
push question-style text to the top. Drop them before the FTS query; the vector search still gets the
full question. Found by the retrieval eval (2026-11-06)."""
from __future__ import annotations

import re

STOP_WORDS_EN = set("""
a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers him his how i if in into is it its itself just me more most my no nor not now
of off on once only or other our ours out over own same she should so some such than that the their
theirs them then there these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours we us vs
""".split())

STOP_WORDS_HE = set("""
של את על עם אל מה מי איך למה מתי איפה כמה האם זה זו זאת אלה אלו הוא היא הם הן אני אנחנו אתה את אתם
גם או אבל כי אם לא כן יש אין היה היתה היו להיות כל עוד רק כבר מאוד יותר פחות בין לפי אחרי לפני תוך
שלנו שלהם שלו שלה לנו להם לו לה בו בה הזה הזאת האלה
""".split())

_TOKEN = re.compile(r"[\w$%+./-]+", re.UNICODE)


def keyword_query(text: str) -> str:
    """Terms worth matching literally: names, products, numbers, domain words."""
    tokens = [t.strip(".-/") for t in _TOKEN.findall(text)]
    kept = [t for t in tokens if t and t.lower() not in STOP_WORDS_EN and t not in STOP_WORDS_HE]
    return " ".join(kept)
