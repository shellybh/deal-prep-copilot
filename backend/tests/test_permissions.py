import pytest
from fastapi import HTTPException

from app.core.security import CurrentUser, ensure_admin


def test_admin_passes():
    ensure_admin(CurrentUser(id="1", email="a@x.com", role="admin"))


@pytest.mark.parametrize(
    "user",
    [
        CurrentUser(id="2", email="u@x.com", role="user"),
        CurrentUser(id="3", email="d@x.com", role="admin", is_active=False),
    ],
)
def test_non_admin_or_inactive_blocked(user):
    with pytest.raises(HTTPException) as exc:
        ensure_admin(user)
    assert exc.value.status_code == 403
