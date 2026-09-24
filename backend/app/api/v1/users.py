"""Current-user profile endpoints."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    status: str

    class Config:
        from_attributes = True


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> User:
    return user
