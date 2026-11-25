from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import create_admin


def _client(existing_rows, updated_rows):
    client = MagicMock()
    table = client.table.return_value
    table.select.return_value.eq.return_value.execute.return_value.data = existing_rows
    table.update.return_value.eq.return_value.execute.return_value.data = updated_rows
    client.auth.admin.invite_user_by_email.return_value = SimpleNamespace(user=SimpleNamespace(id="new-id"))
    return client


def test_invites_new_email_and_sets_admin(monkeypatch):
    client = _client(existing_rows=[], updated_rows=[{"id": "new-id"}])
    monkeypatch.setattr(create_admin, "get_admin_client", lambda: client)

    assert create_admin.create_admin("Boss@Example.com") == "invited"

    email, opts = client.auth.admin.invite_user_by_email.call_args.args
    assert email == "Boss@example.com"  # domain normalized
    assert opts["redirect_to"].endswith("/set-password")
    payload = client.table.return_value.update.call_args.args[0]
    assert payload["role"] == "admin" and payload["is_active"] is True
    client.table.return_value.update.return_value.eq.assert_called_with("id", "new-id")


def test_promotes_existing_user_without_invite(monkeypatch):
    client = _client(existing_rows=[{"id": "old-id"}], updated_rows=[{"id": "old-id"}])
    monkeypatch.setattr(create_admin, "get_admin_client", lambda: client)

    assert create_admin.create_admin("user@example.com") == "promoted"
    client.auth.admin.invite_user_by_email.assert_not_called()
    client.table.return_value.update.return_value.eq.assert_called_with("id", "old-id")


def test_fails_when_profile_missing(monkeypatch):
    client = _client(existing_rows=[], updated_rows=[])
    monkeypatch.setattr(create_admin, "get_admin_client", lambda: client)
    with pytest.raises(RuntimeError, match="profile row not found"):
        create_admin.create_admin("x@example.com")


def test_main_rejects_bad_input(monkeypatch, capsys):
    monkeypatch.setattr(create_admin, "get_admin_client", lambda: pytest.fail("must not call Supabase"))
    assert create_admin.main(["create_admin.py"]) == 2
    assert create_admin.main(["create_admin.py", "not-an-email"]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_send_link_for_existing_user(monkeypatch):
    client = _client(existing_rows=[{"id": "old-id"}], updated_rows=[{"id": "old-id"}])
    link_client = MagicMock()
    monkeypatch.setattr(create_admin, "get_admin_client", lambda: client)
    monkeypatch.setattr(create_admin, "_link_client", lambda: link_client)

    assert create_admin.create_admin("user@example.com", send_link=True) == "promoted+link"
    email, opts = link_client.auth.reset_password_for_email.call_args.args
    assert email == "user@example.com" and opts["redirect_to"].endswith("/set-password")


def test_link_client_uses_implicit_flow():
    # PKCE links can't be completed by the frontend (regression: 2026-11-06 reset link gave no session).
    assert create_admin._link_client().auth._flow_type == "implicit"
