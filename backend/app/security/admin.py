"""Operator-only authorization, independent of user-controlled email fields."""
from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.db.models.user import User


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.id not in get_settings().admin_user_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user
