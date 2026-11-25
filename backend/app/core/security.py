"""Server-side authentication and permission checks."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db.clients import get_admin_client

log = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)

ROLES = ("user", "admin")


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None
    role: str
    is_active: bool = True
    # The caller's JWT, for a user-scoped client (RLS). Never logged.
    access_token: str = field(default="", repr=False)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def ensure_admin(user: CurrentUser) -> None:
    """Pure permission helper, unit-tested. Raises 403 unless the user is an active admin."""
    if not (user.is_active and user.is_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")


def _load_user(token: str) -> CurrentUser:
    admin = get_admin_client()
    try:
        auth_user = admin.auth.get_user(token).user
    except Exception:  # invalid / expired token
        auth_user = None
    if auth_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    rows = (
        admin.table("profiles").select("role,is_active").eq("id", auth_user.id).limit(1).execute().data
    )
    if not rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No profile for this user")
    return CurrentUser(id=auth_user.id, email=auth_user.email, role=rows[0]["role"], is_active=rows[0]["is_active"])


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> CurrentUser:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = _load_user(creds.credentials)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is deactivated")
    return replace(user, access_token=creds.credentials)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    ensure_admin(user)
    return user
