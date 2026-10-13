"""Publishing account linking + publish-to-platform (blueprint section 13)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.publishing import PublishingAccount
from app.db.models.user import User
from app.db.models.video import Video
from app.db.session import get_db
from app.security.permissions import require_video_owner
from app.services.publishing_service import get_publishing_provider
from app.config.settings import get_settings
from app.workers.queue import enqueue

router = APIRouter(prefix="/publishing", tags=["publishing"])


class PublishRequest(BaseModel):
    video_id: uuid.UUID
    publishing_account_id: uuid.UUID
    title: str
    description: str = ""
    hashtags: list[str] = []


@router.post("/{platform}")
async def publish_video(
    platform: str, payload: PublishRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    video = await require_video_owner(db, payload.video_id, user.id)
    if video.output_asset_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Video has not finished rendering yet")

    account = await db.get(PublishingAccount, payload.publishing_account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publishing account not found")
    if account.platform != platform:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Publishing account platform mismatch")
    if platform == "mock" and get_settings().app_env == "production":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Mock publishing is unavailable in production")
    try:
        get_publishing_provider(platform)
    except ValueError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Publishing integration is not configured") from exc

    from app.db.models.asset import Asset

    asset = await db.get(Asset, video.output_asset_id)
    await enqueue(
        "publish_task",
        {
            "video_id": str(video.id),
            "platform": platform,
            "publishing_account_id": str(payload.publishing_account_id),
            "asset_storage_key": asset.storage_key,
            "metadata": {"title": payload.title, "description": payload.description, "hashtags": payload.hashtags},
        },
    )
    return {"status": "publish_queued", "video_id": str(video.id), "platform": platform}
