"""Live checks against the dev Supabase project (TESTING.md §2.2).

Creates two throwaway confirmed users (no email is sent), signs in with the anon key so RLS
applies, and deletes the users afterwards.
Run: python -m pytest -m integration
"""
from __future__ import annotations

import secrets
import uuid

import pytest
from fastapi.testclient import TestClient
from supabase import Client, ClientOptions, create_client

from app.core.config import get_settings
from app.db.clients import get_admin_client, get_user_client
from app.main import app

pytestmark = pytest.mark.integration


def _anon_client() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_anon_key,
                         options=ClientOptions(auto_refresh_token=False, persist_session=False))


@pytest.fixture(scope="module")
def users():
    admin = get_admin_client()
    created = {}
    try:
        for name in ("regular", "admin"):
            email = f"rls-test-{name}-{uuid.uuid4().hex[:8]}@example.com"
            password = secrets.token_urlsafe(16)
            user = admin.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}).user
            created[name] = {"id": user.id, "email": email, "password": password}
        admin.table("profiles").update({"role": "admin"}).eq("id", created["admin"]["id"]).execute()
        for u in created.values():
            session = _anon_client().auth.sign_in_with_password(
                {"email": u["email"], "password": u["password"]}).session
            u["token"] = session.access_token
            u["db"] = get_user_client(session.access_token)
        yield created
    finally:
        for u in created.values():
            admin.auth.admin.delete_user(u["id"])  # profile row goes with it (on delete cascade)


def test_self_signup_is_blocked():
    with pytest.raises(Exception, match="(?i)signup|signups not allowed|disabled"):
        _anon_client().auth.sign_up(
            {"email": f"signup-{uuid.uuid4().hex[:8]}@example.com", "password": secrets.token_urlsafe(16)})


def test_trigger_created_profiles_with_default_role(users):
    row = (get_admin_client().table("profiles").select("role,is_active,email")
           .eq("id", users["regular"]["id"]).single().execute().data)
    assert row == {"role": "user", "is_active": True, "email": users["regular"]["email"]}


def test_regular_user_sees_only_own_profile(users):
    rows = users["regular"]["db"].table("profiles").select("id").execute().data
    assert [r["id"] for r in rows] == [users["regular"]["id"]]


def test_admin_sees_all_profiles(users):
    ids = {r["id"] for r in users["admin"]["db"].table("profiles").select("id").execute().data}
    assert {users["regular"]["id"], users["admin"]["id"]} <= ids


def test_user_can_edit_own_name_but_not_others(users):
    db = users["regular"]["db"]
    own = db.table("profiles").update({"full_name": "Regular Tester"}).eq("id", users["regular"]["id"]).execute()
    assert own.data and own.data[0]["full_name"] == "Regular Tester"
    other = db.table("profiles").update({"full_name": "hacked"}).eq("id", users["admin"]["id"]).execute()
    assert other.data == []


def test_user_cannot_change_role_or_delete(users):
    db = users["regular"]["db"]
    with pytest.raises(Exception, match="(?i)permission denied"):
        db.table("profiles").update({"role": "admin"}).eq("id", users["regular"]["id"]).execute()
    with pytest.raises(Exception, match="(?i)permission denied"):
        db.table("profiles").delete().eq("id", users["regular"]["id"]).execute()
    row = (get_admin_client().table("profiles").select("role")
           .eq("id", users["regular"]["id"]).single().execute().data)
    assert row["role"] == "user"


def test_anon_cannot_read_profiles():
    with pytest.raises(Exception, match="(?i)permission denied"):
        _anon_client().table("profiles").select("id").execute()


def test_api_roles_with_real_tokens(users):
    api = TestClient(app)
    me = api.get("/api/me", headers={"Authorization": f"Bearer {users['regular']['token']}"})
    assert me.status_code == 200 and me.json()["role"] == "user"
    me_admin = api.get("/api/me", headers={"Authorization": f"Bearer {users['admin']['token']}"})
    assert me_admin.json()["role"] == "admin"
    # Regular user can't invite. No email is sent because the request is rejected first.
    resp = api.post("/api/admin/invites", json={"email": "nobody@example.com"},
                    headers={"Authorization": f"Bearer {users['regular']['token']}"})
    assert resp.status_code == 403
