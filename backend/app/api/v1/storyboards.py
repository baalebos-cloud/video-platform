"""Scene/storyboard inspection and single-scene regeneration."""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from typing import Literal
import math
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.scene import Scene
from app.db.models.asset import Asset, AssetType
from app.services.personal_voice_service import MAX_UPLOAD_BYTES, PersonalVoiceError, normalize_recording
from app.services import storage_service
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.session import get_db
from app.security.permissions import require_video_owner
from app.security.rate_limit import RateLimiter
from app.config.settings import get_settings
from app.services import credit_service

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
    scenes = list(result.scalars().all())
    audio_ids = [scene.audio_asset_id for scene in scenes if scene.audio_asset_id is not None]
    audio_by_id = {}
    if audio_ids:
        audio_rows = await db.execute(
            select(Asset).where(Asset.id.in_(audio_ids), Asset.owner_id == user.id)
        )
        audio_by_id = {a.id: a for a in audio_rows.scalars().all()}
    return [
        {
            "id": str(s.id),
            "sequence": s.sequence,
            "narration": s.narration,
            "visual_prompt": s.visual_prompt,
            "duration_seconds": s.duration_seconds,
            "max_duration_seconds": original_scene_duration(s),
            "transition_in": scene_transition(s),
            "visual_asset_id": str(s.visual_asset_id) if s.visual_asset_id else None,
            "audio_asset_id": str(s.audio_asset_id) if s.audio_asset_id else None,
            "audio_state": (
                "pending" if (audio_by_id.get(s.audio_asset_id) and
                    (audio_by_id[s.audio_asset_id].provider_metadata or {}).get("recording_pending"))
                else "recorded" if (audio_by_id.get(s.audio_asset_id) and
                    (audio_by_id[s.audio_asset_id].provider_metadata or {}).get("provider") == "personal_recording")
                else "generated"
            ),
            "on_screen_text": s.on_screen_text,
        }
        for s in scenes
    ]


@router.post("/{video_id}/storyboard/scenes/{scene_id}/narration")
async def upload_personal_scene_narration(
    video_id: uuid.UUID, scene_id: uuid.UUID, request: Request,
    user: User = Depends(get_current_user),
    _: None = Depends(RateLimiter(limit=12, window_seconds=60, scope="personal_voice_upload")),
    db: AsyncSession = Depends(get_db),
):
    """Save only the owner's own/licensed narration as a private WAV asset.

    One recording replaces one scene. This is NOT automated voice cloning.
    Re-rendering the existing storyboard includes the newly recorded audio.
    """
    video = await require_video_owner(db, video_id, user.id)
    await db.refresh(video, with_for_update=True)
    ensure_editable(video)
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_UPLOAD_BYTES):
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio recording exceeds 12 MB")
    raw = await request.body()
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio recording exceeds 12 MB")
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id, Scene.video_id == video.id).with_for_update()
    )
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene not found for this video")
    try:
        wav_bytes, seconds = await asyncio.to_thread(
            normalize_recording, raw, request.headers.get("content-type", ""),
            float(scene.duration_seconds),
        )
    except PersonalVoiceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    key, checksum, size = await asyncio.to_thread(
        storage_service.put_object, wav_bytes,
        content_type="audio/wav", prefix=f"videos/{video.id}/personal-narration",
    )
    asset = Asset(
        owner_id=user.id, type=AssetType.AUDIO, storage_key=key,
        mime_type="audio/wav", checksum=checksum, size_bytes=size,
        provider_metadata={
            "provider": "personal_recording",
            "original_file_type": request.headers.get("content-type", "").split(";")[0][:48],
            "duration_seconds": round(seconds, 2),
        },
    )
    db.add(asset)
    await db.flush()
    scene.audio_asset_id = asset.id
    video.needs_rerender = True
    await db.commit()
    return {
        "scene_id": str(scene.id), "audio_asset_id": str(asset.id),
        "duration_seconds": round(seconds, 2),
        "needs_rerender": True, "audio_state": "recorded",
    }


EDITOR_MIN_DURATION = 0.5
EDITOR_MAX_DURATION = 60.0
EDITOR_TRANSITIONS = {"cut", "fade_black"}


def original_scene_duration(scene: Scene) -> float:
    """The initial rendered duration is the upper trim bound, not a new asset."""
    meta = scene.metadata_json or {}
    stored = meta.get("editor_original_duration_seconds")
    try:
        original = float(stored) if stored is not None else float(scene.duration_seconds)
    except (TypeError, ValueError, OverflowError):
        return float(scene.duration_seconds)
    if not math.isfinite(original) or original <= 0:
        return float(scene.duration_seconds)
    return original


def scene_transition(scene: Scene) -> str:
    transition = (scene.metadata_json or {}).get("editor_transition_in", "cut")
    return transition if transition in EDITOR_TRANSITIONS else "cut"


class SceneEditUpdate(BaseModel):
    duration_seconds: float | None = Field(default=None, ge=EDITOR_MIN_DURATION, le=EDITOR_MAX_DURATION)
    transition_in: Literal["cut", "fade_black"] | None = None

    @model_validator(mode="after")
    def check_has_changes(self):
        if self.duration_seconds is None and self.transition_in is None:
            raise ValueError("Specify duration_seconds or transition_in")
        if self.duration_seconds is not None and not math.isfinite(self.duration_seconds):
            raise ValueError("Clip duration must be finite")
        return self


def apply_scene_edit(scene: Scene, payload: SceneEditUpdate) -> bool:
    """Adjust playback only: existing image, stock video and WAV stay untouched."""
    meta = dict(scene.metadata_json or {})
    changed = False
    if payload.duration_seconds is not None:
        original = original_scene_duration(scene)
        if payload.duration_seconds > original + 0.0001:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Cannot extend a clip beyond its original media duration",
            )
        duration = round(payload.duration_seconds, 2)
        if duration != round(float(scene.duration_seconds), 2):
            meta.setdefault("editor_original_duration_seconds", original)
            scene.duration_seconds = duration
            changed = True
    if payload.transition_in is not None and payload.transition_in != scene_transition(scene):
        meta["editor_transition_in"] = payload.transition_in
        changed = True
    if changed:
        scene.metadata_json = meta
    return changed


@router.patch("/{video_id}/storyboard/scenes/{scene_id}/edit")
async def edit_scene_timeline(
    video_id: uuid.UUID,
    scene_id: uuid.UUID,
    payload: SceneEditUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-only clip trim and transition settings, serialized with re-render."""
    video = await require_video_owner(db, video_id, user.id)
    await db.refresh(video, with_for_update=True)
    ensure_editable(video)
    result = await db.execute(
        select(Scene).where(Scene.video_id == video.id, Scene.id == scene_id).with_for_update()
    )
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scene not found for this video")
    changed = apply_scene_edit(scene, payload)
    if changed:
        video.needs_rerender = True
        await db.commit()
    return {
        "scene_id": str(scene.id),
        "duration_seconds": scene.duration_seconds,
        "max_duration_seconds": original_scene_duration(scene),
        "transition_in": scene_transition(scene),
        "needs_rerender": video.needs_rerender,
        "changed": changed,
    }


class SceneOrderUpdate(BaseModel):
    scene_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


def apply_scene_order(scenes: list[Scene], ids: list[uuid.UUID]) -> bool:
    """Validate an exact permutation before mutating any scene.

    Reorder keeps scene audio, stock footage, captions and saved assets bound
    to the original scene ID. It only changes playback order.
    """
    if len(ids) != len(set(ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate scene IDs")
    current_ids = {scene.id for scene in scenes}
    if len(ids) != len(scenes) or set(ids) != current_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Scene order must include every scene belonging to this video exactly once",
        )
    ordered = sorted(scenes, key=lambda scene: scene.sequence)
    if [scene.id for scene in ordered] == ids:
        return False
    by_id = {scene.id: scene for scene in scenes}
    for sequence, scene_id in enumerate(ids, start=1):
        by_id[scene_id].sequence = sequence
    return True


@router.patch("/{video_id}/storyboard/order")
async def update_scene_order(
    video_id: uuid.UUID,
    payload: SceneOrderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist clip reordering for the FFmpeg renderer and subtitle timeline."""
    video = await require_video_owner(db, video_id, user.id)
    await db.refresh(video, with_for_update=True)
    ensure_editable(video)
    result = await db.execute(
        select(Scene).where(Scene.video_id == video.id).order_by(Scene.sequence).with_for_update()
    )
    scenes = list(result.scalars().all())
    changed = apply_scene_order(scenes, payload.scene_ids)
    if changed:
        video.needs_rerender = True
        await db.commit()
    return {
        "video_id": str(video.id),
        "scene_ids": [str(scene_id) for scene_id in payload.scene_ids],
        "changed": changed,
        "needs_rerender": video.needs_rerender,
    }


@router.patch("/{video_id}/storyboard/scenes/{scene_id}")
async def update_scene_prompt(
    video_id: uuid.UUID,
    scene_id: uuid.UUID,
    payload: ScenePromptUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    video = await require_video_owner(db, video_id, user.id)
    await db.refresh(video, with_for_update=True)
    ensure_editable(video)
    scene = await get_owned_scene(db, video.id, scene_id)
    prompt = payload.visual_prompt.strip()
    if len(prompt) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Visual prompt is too short")
    scene.visual_prompt = prompt
    # A changed prompt must not silently re-use the old stock footage.
    scene.metadata_json = {k: v for k, v in (scene.metadata_json or {}).items()
                           if k not in ("stock_footage_key", "stock_source_url")}
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
    settings = get_settings()
    charged_id = str(uuid.uuid4()) if settings.image_provider != "mock" and settings.credit_enforcement_enabled else None
    if charged_id:
        await credit_service.debit(
            db, user.id, settings.scene_regeneration_credits,
            reference_type="scene_regeneration", reference_id=charged_id,
            metadata={"video_id": str(video.id), "scene_id": str(scene.id)},
        )
        await db.commit()
    try:
        result = await visual_service.generate_scene_image(prompt=scene.visual_prompt, aspect_ratio=video.aspect_ratio)
        storage_key, _c, _s = await asyncio.to_thread(
            storage_service.put_object,
            result.image_bytes,
            content_type=f"image/{result.format}",
            prefix=f"videos/{video.id}/images",
        )
    except Exception:
        # Either the paid image provider or the media upload can fail.
        # In both cases a usable scene image was not delivered.
        await db.rollback()
        if charged_id:
            await credit_service.refund(db, user.id, reference_type="scene_regeneration", reference_id=charged_id)
            await db.commit()
        raise
    from app.db.models.asset import Asset, AssetType

    # Recheck after the external provider call: another request may have
    # queued re-rendering while an image was being generated.
    await db.refresh(video, with_for_update=True)
    if video.status != VideoStatus.READY:
        if charged_id:
            await db.rollback()
            await credit_service.refund(db, user.id, reference_type="scene_regeneration", reference_id=charged_id)
            await db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Video started rendering during scene regeneration")
    scene = await get_owned_scene(db, video.id, scene_id)
    asset = Asset(
        owner_id=user.id, type=AssetType.IMAGE, storage_key=storage_key,
        mime_type=f"image/{result.format}",
        provider_metadata={"provider": result.provider, "model": (
            get_settings().openai_image_model if result.provider == "openai" else "mock"
        )},
    )
    db.add(asset)
    await db.flush()
    scene.visual_asset_id = asset.id
    scene.metadata_json = {k: v for k, v in (scene.metadata_json or {}).items()
                           if k not in ("stock_footage_key", "stock_source_url")}
    video.needs_rerender = True
    await db.commit()
    return {"scene_id": str(scene.id), "visual_asset_id": str(asset.id)}
