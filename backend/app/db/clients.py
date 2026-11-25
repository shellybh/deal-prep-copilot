"""Supabase clients.

- Admin client: SUPABASE_KEY (secret / service_role). Bypasses RLS. Backend only, and every
  call must come after a server-side permission check.
- User client: SUPABASE_ANON_KEY + the user's JWT, so RLS applies.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app.core.config import get_settings


@lru_cache
def get_admin_client() -> Client:
    s = get_settings()
    return create_client(
        s.supabase_url,
        s.supabase_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )


def get_user_client(access_token: str) -> Client:
    s = get_settings()
    client = create_client(
        s.supabase_url,
        s.supabase_anon_key,
        options=ClientOptions(
            auto_refresh_token=False,
            persist_session=False,
            headers={"Authorization": f"Bearer {access_token}"},
        ),
    )
    client.postgrest.auth(access_token)
    return client
