"""Structured (JSON) logging with secret redaction."""
from __future__ import annotations

import json
import logging
import os
import re

_SECRET_ENV = ("SUPABASE_KEY", "SUPABASE_ANON_KEY", "GEMINI_API_KEY", "TAVILY_API_KEY", "OPENAI_API_KEY")
_PATTERNS = [
    (re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"), "[REDACTED]"),  # JWTs
    (re.compile(r"sb_(?:secret|publishable)_[\w-]+"), "[REDACTED]"),  # Supabase new-style keys
    (re.compile(r"(?i)(bearer\s+)\S+"), r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    for name in _SECRET_ENV:
        value = os.getenv(name, "").strip()
        if len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class JsonRedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonRedactingFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
