"""Create or promote the first admin (bootstrap, run once).

Public signup is disabled and only admins can invite, so the first admin can't come
through the app. This script uses the service key:
  - email not registered yet -> send a Supabase invite (user sets a password at /set-password)
  - email already registered  -> just promote

Then it sets role = 'admin' and is_active = true on the profile.

Run from the backend folder:  python create_admin.py admin@example.com [--send-link]
--send-link: for an already registered user, email a password-reset link to /set-password
(use it when the invite link expired or was already used).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from email_validator import EmailNotValidError, validate_email  # noqa: E402

from app.core.config import ConfigError, get_settings  # noqa: E402
from app.db.clients import get_admin_client  # noqa: E402
from supabase import Client, ClientOptions, create_client  # noqa: E402


def _link_client() -> Client:
    """Client for emailed links. supabase-py defaults to PKCE, which returns `?code=` that only this
    Python process could exchange; the frontend uses the implicit flow (tokens in the URL hash)."""
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_anon_key, options=ClientOptions(
        flow_type="implicit", auto_refresh_token=False, persist_session=False))


def create_admin(email: str, send_link: bool = False) -> str:
    """Return 'invited', 'promoted' or 'promoted+link'. Raises on failure."""
    email = validate_email(email, check_deliverability=False).normalized
    client = get_admin_client()

    rows = client.table("profiles").select("id").eq("email", email).execute().data
    if rows:
        user_id, outcome = rows[0]["id"], "promoted"
    else:
        redirect = f"{get_settings().frontend_url}/set-password"
        resp = client.auth.admin.invite_user_by_email(email, {"redirect_to": redirect})
        user_id, outcome = resp.user.id, "invited"

    # The profile row is created by the on_auth_user_created trigger.
    updated = (client.table("profiles")
               .update({"role": "admin", "is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()})
               .eq("id", user_id).execute().data)
    if not updated:
        raise RuntimeError("profile row not found after invite (is the profiles migration applied?)")
    if outcome == "promoted" and send_link:
        redirect = f"{get_settings().frontend_url}/set-password"
        _link_client().auth.reset_password_for_email(email, {"redirect_to": redirect})
        outcome = "promoted+link"
    return outcome


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--send-link"]
    if len(args) != 1:
        print("Usage: python create_admin.py <email> [--send-link]")
        return 2
    try:
        outcome = create_admin(args[0], send_link="--send-link" in argv)
    except (ConfigError, EmailNotValidError) as exc:
        print(f"FAILED: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - report clearly, never print secrets
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return 1
    if outcome == "invited":
        print("SUCCESS: invite email sent and the user is set as admin. "
              "Open the link in the email to set a password.")
    elif outcome == "promoted+link":
        print("SUCCESS: user is admin and a password-reset link was emailed. Open it once to set a password.")
    else:
        print("SUCCESS: existing user promoted to admin.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
