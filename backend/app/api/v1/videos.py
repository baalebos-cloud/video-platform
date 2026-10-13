"""
Video generation lifecycle — this is the centerpiece endpoint described
in blueprint section 8.2 (`POST /videos/generate`) plus status/progress
polling (8.4).
"""
import hashlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.script import Script
from app.db.models.user import User
from app.db.models.video import Video
from app.db.session import get_db
from app.security.permissions import require_project_owner, require_video_owner
from app.security.rate_limit import RateLimiter
from app.services import quota_service, video_service

router = APIRouter(prefix="/videos", tags=["videos"])

generate_rate_limiter = RateLimiter(limit=10, window_seconds=60, scope="video_generate")


class VoicePreferences(BaseModel):
    provider: str | None = None
    voice_id: str | None = None
    gender: str | None = None
    personality: str | None = None
    emotion: str | None = None
    pace: float = 1.0
    pitch: str | None = None


class GenerateVideoRequest(BaseModel):
    project_id: uuid.UUID
    topic: str = Field(min_length=3, max_length=1024)
    language: str = "English"
    locale: str = "en-US"
    duration_seconds: int = Field(default=60, ge=5, le=600)
    platform: str = "youtube_shorts"
    visual_style: str = "cinematic_realistic"
    creativity: str = "high"
    voice: VoicePreferences = Field(default_factory=VoicePreferences)


class GenerateVideoResponse(BaseModel):
    video_id: uuid.UUID
    status: str
    job_id: uuid.UUID
    message: str


class VideoStatusResponse(BaseModel):
    video_id: uuid.UUID
    status: str
    progress: int
    current_stage: str | None
    error_message: str | None = None
    estimated_remaining_seconds: int | None = None
    output_asset_id: uuid.UUID | None = None
    thumbnail_asset_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    topic: str | None = None
    platform: str | None = None
    language: str | None = None
    duration_seconds: int | None = None

    class Config:
        from_attributes = True


@router.post("/generate", response_model=GenerateVideoResponse)
async def generate_video(
    payload: GenerateVideoRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    _: None = Depends(generate_rate_limiter),
    db: AsyncSession = Depends(get_db),
) -> GenerateVideoResponse:
    await require_project_owner(db, payload.project_id, user.id)
    await quota_service.enforce_max_duration(payload.duration_seconds)
    await quota_service.enforce_concurrent_job_limit(db, user.id)

    input_hash = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    # A client-supplied retry key is namespaced to the user. Without a key,
    # repeated intentional generations of the same prompt remain possible.
    key: str | None = None
    if idempotency_key is not None:
        if not 1 <= len(idempotency_key.strip()) <= 128:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Idempotency-Key length")
        key = hashlib.sha256(f"{user.id}:{idempotency_key}".encode()).hexdigest()

    async def existing_response() -> GenerateVideoResponse | None:
        if key is None:
            return None
        existing = await quota_service.find_existing_job_by_idempotency_key(db, key)
        if existing is None:
            return None
        if existing.input_hash != input_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key was reused with a different request")
        return GenerateVideoResponse(
            video_id=existing.video_id,
            status=existing.status.value,
            job_id=existing.id,
            message="Existing generation returned for this idempotency key",
        )

    previous = await existing_response()
    if previous is not None:
        return previous

    try:
        video, job = await video_service.start_generation(
            db,
            project_id=payload.project_id,
            topic=payload.topic,
            language=payload.language,
            locale=payload.locale,
            duration_seconds=payload.duration_seconds,
            platform=payload.platform,
            visual_style=payload.visual_style,
            creativity=payload.creativity,
            voice_preferences=payload.voice.model_dump(),
            idempotency_key=key,
            input_hash=input_hash,
        )
    except IntegrityError:
        # A concurrent request may have inserted the same retry key after
        # our initial lookup; the unique DB index resolves that race.
        await db.rollback()
        previous = await existing_response()
        if previous is not None:
            return previous
        raise

    return GenerateVideoResponse(
        video_id=video.id, status="queued", job_id=job.id, message="Video generation queued"
    )


@router.get("/{video_id}", response_model=VideoStatusResponse)
async def get_video_status(
    video_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> VideoStatusResponse:
    video = await require_video_owner(db, video_id, user.id)
    return VideoStatusResponse(
        video_id=video.id,
        status=video.status.value,
        progress=video.progress,
        current_stage=video.current_stage,
        error_message=video.error_message,
        output_asset_id=video.output_asset_id,
        thumbnail_asset_id=video.thumbnail_asset_id,
        project_id=video.project_id,
        topic=video.topic,
        platform=video.platform,
        language=video.language,
        duration_seconds=video.duration_seconds,
    )


@router.post("/{video_id}/script")
async def regenerate_script(
    video_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    video = await require_video_owner(db, video_id, user.id)
    from app.services.content_service import generate_plan_for_video, persist_plan

    plan, _metadata = await generate_plan_for_video(video)
    script, scenes = await persist_plan(db, video, plan)
    await db.commit()
    return {"script_id": script.id, "scene_count": len(scenes)}


@router.get("/{video_id}/scripts", response_model=list[dict])
async def list_scripts(
    video_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await require_video_owner(db, video_id, user.id)
    result = await db.execute(select(Script).where(Script.video_id == video_id).order_by(Script.version.desc()))
    return [
        {"id": str(s.id), "version": s.version, "content": s.content, "status": s.status.value}
        for s in result.scalars().all()
    ]
