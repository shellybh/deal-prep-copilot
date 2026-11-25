"""Current user + minimal admin invite. Full user management is future work."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.config import get_settings
from app.core.security import CurrentUser, get_current_user, require_admin
from app.db.clients import get_admin_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["users"])


class MeResponse(BaseModel):
    id: str
    email: str | None
    role: str


class InviteRequest(BaseModel):
    email: EmailStr


class InviteResponse(BaseModel):
    email: str
    invited: bool


@router.get("/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(id=user.id, email=user.email, role=user.role)


@router.post("/admin/invites", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
def invite_user(body: InviteRequest, admin: CurrentUser = Depends(require_admin)) -> InviteResponse:
    redirect = f"{get_settings().frontend_url}/set-password"
    try:
        get_admin_client().auth.admin.invite_user_by_email(str(body.email), {"redirect_to": redirect})
    except Exception as exc:
        log.warning("Invite failed for an email by admin %s: %s", admin.id, type(exc).__name__)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invite failed: {exc}") from exc
    log.info("Admin %s invited a user", admin.id)
    return InviteResponse(email=str(body.email), invited=True)
