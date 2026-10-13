"""Current-user profile endpoints."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models.user import User
from app.config.settings import get_settings

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    status: str
    is_admin: bool = False

    class Config:
        from_attributes = True


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "status": user.status,
        "is_admin": user.id in get_settings().admin_user_ids,
    }
