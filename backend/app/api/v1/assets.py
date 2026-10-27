"""Asset upload signing + retrieval (large binaries live in object storage, not Postgres)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models.asset import Asset, AssetType
from app.db.models.scene import Scene
from app.db.models.video import Video, VideoStatus
from app.db.models.user import User
from app.db.session import get_db
from app.services.storage_service import get_signed_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetResponse(BaseModel):
    id: uuid.UUID
    type: str
    mime_type: str
    signed_url: str


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: uuid.UUID, download: bool = False,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    asset = await db.get(Asset, asset_id)
    if asset is None or asset.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    if download:
        if asset.type != AssetType.FINAL_VIDEO:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only completed videos can be downloaded as MP4")
        result = await db.execute(select(Video).where(Video.output_asset_id == asset.id))
        video = result.scalar_one_or_none()
        if video is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Video export is unavailable")
        if (video.voice_preferences or {}).get("mode") == "recorded":
            # The initial recorded-mode render is deliberately silent. Do not
            # provide a download link until all private narrations are saved
            # AND the final MP4 has been re-rendered with those recordings.
            if video.status != VideoStatus.READY or video.needs_rerender:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Re-render all your saved voiceovers before downloading the MP4",
                )
            result = await db.execute(select(Scene).where(Scene.video_id == video.id))
            scenes = list(result.scalars().all())
            audio_ids = [s.audio_asset_id for s in scenes if s.audio_asset_id]
            stored = await db.execute(select(Asset).where(
                Asset.id.in_(audio_ids), Asset.owner_id == user.id, Asset.type == AssetType.AUDIO,
            ))
            audio_by_id = {item.id: item for item in stored.scalars().all()}
            if not scenes or any(
                not audio_by_id.get(scene.audio_asset_id)
                or (audio_by_id[scene.audio_asset_id].provider_metadata or {}).get("provider")
                    != "personal_recording"
                for scene in scenes
            ):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Complete every personal narration scene before exporting",
                )
    filename = f"baalebos-{asset.id}.mp4" if download else None
    return AssetResponse(
        id=asset.id, type=asset.type.value, mime_type=asset.mime_type,
        signed_url=get_signed_url(asset.storage_key, download_filename=filename)
    )
