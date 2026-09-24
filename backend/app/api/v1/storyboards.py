"""Scene/storyboard inspection and single-scene regeneration."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.scene import Scene
from app.db.models.user import User
from app.db.session import get_db
from app.security.permissions import require_video_owner

router = APIRouter(prefix="/videos", tags=["storyboards"])


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
        }
        for s in result.scalars().all()
    ]


@router.post("/{video_id}/storyboard/scenes/{scene_id}/regenerate")
async def regenerate_scene(
    video_id: uuid.UUID, scene_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Allows regenerating a single scene's visual without re-running the
    entire project (blueprint: "Provide a way to regenerate a scene or
    narration without regenerating the entire project").
    """
    video = await require_video_owner(db, video_id, user.id)
    from app.services import storage_service, visual_service

    scene = await db.get(Scene, scene_id)
    result = await visual_service.generate_scene_image(prompt=scene.visual_prompt, aspect_ratio=video.aspect_ratio)
    storage_key, _c, _s = storage_service.put_object(
        result.image_bytes, content_type=f"image/{result.format}", prefix=f"videos/{video.id}/images"
    )
    from app.db.models.asset import Asset, AssetType

    asset = Asset(owner_id=user.id, type=AssetType.IMAGE, storage_key=storage_key, mime_type=f"image/{result.format}")
    db.add(asset)
    await db.flush()
    scene.visual_asset_id = asset.id
    await db.commit()
    return {"scene_id": str(scene.id), "visual_asset_id": str(asset.id)}
