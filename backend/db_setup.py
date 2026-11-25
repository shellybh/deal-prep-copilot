"""Supabase connection module.

Run from the backend folder:  python db_setup.py
Other scripts (e.g. ingest_data.py) import `get_supabase()` from here.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from supabase import Client  # noqa: E402

from app.core.config import ConfigError, get_settings  # noqa: E402
from app.db.clients import get_admin_client  # noqa: E402


def get_supabase() -> Client:
    """Admin (service key) client. Backend and scripts only."""
    return get_admin_client()


def test_connection() -> bool:
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(f"FAILED: {exc}")
        return False
    try:
        client = get_supabase()
        # Auth admin call: needs a valid secret key and works on an empty schema.
        client.auth.admin.list_users(page=1, per_page=1)
        # Public Auth settings endpoint with the anon key: checks that key too.
        resp = httpx.get(f"{settings.supabase_url}/auth/v1/settings",
                         headers={"apikey": settings.supabase_anon_key}, timeout=15)
        if resp.status_code != 200:
            print(f"FAILED: SUPABASE_ANON_KEY was rejected (HTTP {resp.status_code}).")
            return False
    except Exception as exc:  # noqa: BLE001 - report any failure clearly
        print(f"FAILED: could not connect to Supabase ({type(exc).__name__}). "
              "Check SUPABASE_URL and SUPABASE_KEY in .env.")
        return False
    print(f"SUCCESS: connected to Supabase at {settings.supabase_url}")
    return True


if __name__ == "__main__":
    sys.exit(0 if test_connection() else 1)
