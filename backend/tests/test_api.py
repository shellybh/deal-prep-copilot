from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import users as users_module
from app.core import security
from app.core.logging import redact
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def as_user(role: str):
    app.dependency_overrides[security.get_current_user] = lambda: security.CurrentUser(
        id=f"{role}-id", email=f"{role}@x.com", role=role
    )


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_unauthenticated_rejected():
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/admin/invites", json={"email": "n@x.com"}).status_code == 401


def test_invalid_token_rejected(monkeypatch):
    fake = MagicMock()
    fake.auth.get_user.side_effect = Exception("bad jwt")
    monkeypatch.setattr(security, "get_admin_client", lambda: fake)
    r = client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_regular_user_cannot_invite(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(users_module, "get_admin_client", lambda: fake)
    as_user("user")
    r = client.post("/api/admin/invites", json={"email": "n@x.com"})
    assert r.status_code == 403
    fake.auth.admin.invite_user_by_email.assert_not_called()


def test_admin_can_invite(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(users_module, "get_admin_client", lambda: fake)
    as_user("admin")
    r = client.post("/api/admin/invites", json={"email": "n@x.com"})
    assert r.status_code == 201
    fake.auth.admin.invite_user_by_email.assert_called_once()


def test_invite_validates_email():
    as_user("admin")
    assert client.post("/api/admin/invites", json={"email": "nope"}).status_code == 422


def test_me_returns_role():
    as_user("user")
    assert client.get("/api/me").json()["role"] == "user"


def test_redaction():
    out = redact("Authorization: Bearer abc.def.ghi and sb_secret_XYZ123 and eyJa.eyJb.sig")
    assert "abc.def.ghi" not in out and "sb_secret_XYZ123" not in out and "eyJa" not in out
