"""Publish-date parsing. Never guesses: anything unparseable or in the future is `None`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FUTURE_TOLERANCE = timedelta(days=1)   # clock skew / time zones; further ahead = not trustworthy


def parse_date(raw) -> datetime | None:
    """Tavily gives RFC 2822 ('Tue, 03 Nov 2026 15:00:00 GMT'); accept ISO 8601 too. Never guess."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def trusted_date(raw, now: datetime) -> datetime | None:
    """Parsed date, or None when missing, unparseable or in the future."""
    dt = parse_date(raw)
    if dt is None or dt > now + FUTURE_TOLERANCE:
        return None
    return dt
