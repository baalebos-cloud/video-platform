"""Asset upload signing + retrieval (large binaries live in object storage, not Postgres)."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models.asset import Asset, AssetType
from app.db.models.user import User
from app.db.session import get_db
from app.services.storage_service import get_signed_url
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetResponse(BaseModel):
    id: uuid.UUID
    type: str
    mime_type: str
    signed_url: str


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException, status

    asset = await db.get(Asset, asset_id)
    if asset is None or asset.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return AssetResponse(
        id=asset.id, type=asset.type.value, mime_type=asset.mime_type, signed_url=get_signed_url(asset.storage_key)
    )
