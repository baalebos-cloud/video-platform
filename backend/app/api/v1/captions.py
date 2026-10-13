"""Owner-only caption editor: editable text per scene and safe FFmpeg style presets."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.scene import Scene
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.session import get_db
from app.security.permissions import require_video_owner

router = APIRouter(prefix="/videos", tags=["captions"])

CaptionStyle = Literal["classic", "bold", "social", "minimal"]


class CaptionEdit(BaseModel):
    scene_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=1000)
    style: CaptionStyle | None = None

    @model_validator(mode="after")
    def validate_edit(self):
        if self.style is None and (self.scene_id is None or self.text is None):
            raise ValueError("Provide caption style or a scene_id and text")
        if (self.scene_id is None) != (self.text is None):
            raise ValueError("scene_id and text must be provided together")
        return self


def caption_rows(scenes: list[Scene]) -> list[dict]:
    offset = 0.0
    rows = []
    for scene in sorted(scenes, key=lambda item: item.sequence):
        duration = max(float(scene.duration_seconds or 0), 0)
        rows.append({
            "scene_id": str(scene.id), "sequence": scene.sequence,
            "text": scene.caption_text if scene.caption_text is not None else scene.narration,
            "original_text": scene.narration,
            "start_seconds": round(offset, 2),
            "end_seconds": round(offset + duration, 2),
        })
        offset += duration
    return rows


@router.get("/{video_id}/captions")
async def get_captions(
    video_id: uuid.UUID, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    video = await require_video_owner(db, video_id, user.id)
    result = await db.execute(select(Scene).where(Scene.video_id == video.id).order_by(Scene.sequence))
    return {
        "video_id": str(video.id),
        "style": video.caption_style or "classic",
        "needs_rerender": video.needs_rerender,
        "scenes": caption_rows(list(result.scalars().all())),
        "timing_note": "Cue timings are estimated from scene audio duration, not word-aligned.",
    }


@router.patch("/{video_id}/captions")
async def edit_captions(
    video_id: uuid.UUID, payload: CaptionEdit,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    video = await require_video_owner(db, video_id, user.id)
    await db.refresh(video, with_for_update=True)
    if video.status != VideoStatus.READY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Captions are editable only after generation finishes")
    changed = False
    if payload.scene_id is not None:
        scene = await db.get(Scene, payload.scene_id)
        if scene is None or scene.video_id != video.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene not found for this video")
        # Empty text intentionally disables captions in that scene.
        text = (payload.text or "").strip()
        if scene.caption_text != text:
            scene.caption_text = text
            changed = True
    if payload.style is not None and video.caption_style != payload.style:
        video.caption_style = payload.style
        changed = True
    if changed:
        video.needs_rerender = True
        await db.commit()
    return {"video_id": str(video.id), "style": video.caption_style,
            "needs_rerender": video.needs_rerender, "changed": changed}
