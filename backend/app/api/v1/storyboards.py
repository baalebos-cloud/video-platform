"""Scene/storyboard inspection and single-scene regeneration."""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.scene import Scene
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.session import get_db
from app.security.permissions import require_video_owner
from app.security.rate_limit import RateLimiter

router = APIRouter(prefix="/videos", tags=["storyboards"])


class ScenePromptUpdate(BaseModel):
    visual_prompt: str = Field(min_length=3, max_length=3000)


def ensure_editable(video) -> None:
    if video.status != VideoStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Scenes can be edited after video generation finishes")


async def get_owned_scene(db: AsyncSession, video_id: uuid.UUID, scene_id: uuid.UUID) -> Scene:
    scene = await db.get(Scene, scene_id)
    if scene is None or scene.video_id != video_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene not found for this video")
    return scene


@router.get("/{video_id}/storyboard")
async def get_storyboard(video_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await require_video_owner(db, video_id, user.id)
    result = await db.execute(select(Scene).where(Scene.video_id == video_id).order_by(Scene.sequence))
    return [
        {
            "id": str(s.id),
            "sequence": s.sequence,
            "narration": s.narration,
            "visual_prompt": s.visual_prompt,
            "duration_seconds": s.duration_seconds,
            "visual_asset_id": str(s.visual_asset_id) if s.visual_asset_id else None,
            "on_screen_text": s.on_screen_text,
        }
        for s in result.scalars().all()
    ]


@router.patch("/{video_id}/storyboard/scenes/{scene_id}")
async def update_scene_prompt(
    video_id: uuid.UUID,
    scene_id: uuid.UUID,
    payload: ScenePromptUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    video = await require_video_owner(db, video_id, user.id)
    await db.execute(select(Video.id).where(Video.id == video.id).with_for_update())
    ensure_editable(video)
    scene = await get_owned_scene(db, video.id, scene_id)
    prompt = payload.visual_prompt.strip()
    if len(prompt) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Visual prompt is too short")
    scene.visual_prompt = prompt
    await db.commit()
    return {"scene_id": str(scene.id), "visual_prompt": scene.visual_prompt}


@router.post("/{video_id}/storyboard/scenes/{scene_id}/regenerate")
async def regenerate_scene(
    video_id: uuid.UUID, scene_id: uuid.UUID, user: User = Depends(get_current_user),
    _: None = Depends(RateLimiter(limit=3, window_seconds=60, scope="regenerate_visual")),
    db: AsyncSession = Depends(get_db),
):
    """
    Allows regenerating a single scene's visual without re-running the
    entire project (blueprint: "Provide a way to regenerate a scene or
    narration without regenerating the entire project").
    """
    video = await require_video_owner(db, video_id, user.id)
    from app.services import storage_service, visual_service

    ensure_editable(video)
    scene = await get_owned_scene(db, video.id, scene_id)
    result = await visual_service.generate_scene_image(prompt=scene.visual_prompt, aspect_ratio=video.aspect_ratio)
    storage_key, _c, _s = await asyncio.to_thread(
        storage_service.put_object,
        result.image_bytes,
        content_type=f"image/{result.format}",
        prefix=f"videos/{video.id}/images",
    )
    from app.db.models.asset import Asset, AssetType

    # Recheck after the external provider call: another request may have
    # queued re-rendering while an image was being generated.
    await db.execute(select(Video.id).where(Video.id == video.id).with_for_update())
    ensure_editable(video)
    scene = await get_owned_scene(db, video.id, scene_id)
    asset = Asset(owner_id=user.id, type=AssetType.IMAGE, storage_key=storage_key, mime_type=f"image/{result.format}")
    db.add(asset)
    await db.flush()
    scene.visual_asset_id = asset.id
    video.needs_rerender = True
    await db.commit()
    return {"scene_id": str(scene.id), "visual_asset_id": str(asset.id)}
