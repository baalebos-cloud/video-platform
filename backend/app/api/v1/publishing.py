"""Publishing account linking + publish-to-platform (blueprint section 13)."""
import uuid
from datetime import datetime
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.publishing import PublishingAccount, PublishedVideo, PublishStatus
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.session import get_db
from app.security.permissions import require_video_owner
from app.services.publishing_service import get_publishing_provider
from app.services.publishing_oauth import authorize, complete_authorization
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
        raise HTTPException(status.HTTP_409_CONFLICT, "Render and review the latest video before publishing")

    account = await db.get(PublishingAccount, payload.publishing_account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publishing account not found")
    if account.platform != platform:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Publishing account platform mismatch")
    if video.status != VideoStatus.READY or video.needs_rerender:
        raise HTTPException(status.HTTP_409_CONFLICT, "Render and review the latest video before publishing")
    if (video.voice_preferences or {}).get("mode") == "recorded":
        from app.db.models.asset import Asset, AssetType
        from app.db.models.scene import Scene
        scene_rows = await db.execute(select(Scene).where(Scene.video_id == video.id))
        all_scenes = list(scene_rows.scalars().all())
        asset_ids = [scene.audio_asset_id for scene in all_scenes if scene.audio_asset_id]
        audio_rows = await db.execute(
            select(Asset).where(Asset.id.in_(asset_ids), Asset.owner_id == user.id, Asset.type == AssetType.AUDIO)
        )
        audio_assets = {asset.id: asset for asset in audio_rows.scalars().all()}
        if not all_scenes or any(
            scene.audio_asset_id not in audio_assets or
            (audio_assets[scene.audio_asset_id].provider_metadata or {}).get("provider") != "personal_recording"
            for scene in all_scenes
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Record all scene narration before publishing this personal-voice video",
            )
    if platform != "mock" and not account.token_ciphertext:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reconnect this account to authorize publishing")
    if platform == "mock" and get_settings().app_env == "production":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Mock publishing is unavailable in production")
    try:
        get_publishing_provider(platform)
    except ValueError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Publishing integration is not configured") from exc

    from app.db.models.asset import Asset

    asset = await db.get(Asset, video.output_asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Rendered video asset is missing")
    queue_id = await enqueue(
        "publish_task",
        {
            "video_id": str(video.id),
            "platform": platform,
            "publishing_account_id": str(payload.publishing_account_id),
            "asset_storage_key": asset.storage_key,
            "metadata": {"title": payload.title, "description": payload.description, "hashtags": payload.hashtags},
        },
    )
    if not queue_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Publishing queue unavailable")
    return {"status": "publish_queued", "video_id": str(video.id), "platform": platform}


@router.get("/accounts")
async def connected_accounts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PublishingAccount).where(
        PublishingAccount.user_id == user.id,
        PublishingAccount.platform.in_(("youtube", "tiktok")),
        PublishingAccount.token_ciphertext.is_not(None),
    ).order_by(PublishingAccount.platform))
    return {"items": [{"id": str(a.id), "platform": a.platform,
                        "external_id": a.external_id} for a in result.scalars().all()]}


@router.post("/connections/{platform}/start")
async def start_platform_oauth(platform: str, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    return {"authorization_url": await authorize(db, platform, user.id)}


@router.get("/oauth/{platform}/callback", include_in_schema=False)
async def complete_platform_oauth(platform: str, state: str, code: str,
                                  db: AsyncSession = Depends(get_db)):
    await complete_authorization(db, platform, state, code)
    # Never redirect to untrusted OAuth query parameters.
    return RedirectResponse(
        url=f"{get_settings().app_url.rstrip('/')}/dashboard/publishing?connected={quote(platform)}",
        status_code=303,
    )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_publishing_account(account_id: uuid.UUID, user: User = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    account = await db.scalar(select(PublishingAccount).where(
        PublishingAccount.id == account_id, PublishingAccount.user_id == user.id,
    ).with_for_update())
    if not account:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publishing account not found")
    account.token_ciphertext = None
    await db.commit()


@router.get("/history")
async def publishing_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(PublishedVideo).join(
        PublishingAccount, PublishedVideo.publishing_account_id == PublishingAccount.id,
    ).where(PublishingAccount.user_id == user.id).order_by(
        PublishedVideo.created_at.desc()
    ).limit(40))
    return {"items": [
        {"id": str(p.id), "platform": p.platform, "video_id": str(p.video_id),
         "status": p.status.value, "external_post_id": p.external_post_id,
         "created_at": p.created_at}
        for p in rows.scalars().all()
    ]}
