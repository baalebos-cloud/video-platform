"""
Video generation lifecycle — this is the centerpiece endpoint described
in blueprint section 8.2 (`POST /videos/generate`) plus status/progress
polling (8.4).
"""
import hashlib
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
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
    voice: VoicePreferences = VoicePreferences()


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
    estimated_remaining_seconds: int | None = None

    class Config:
        from_attributes = True


@router.post("/generate", response_model=GenerateVideoResponse, dependencies=[Depends(generate_rate_limiter)])
async def generate_video(
    payload: GenerateVideoRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateVideoResponse:
    await require_project_owner(db, payload.project_id, user.id)
    await quota_service.enforce_max_duration(payload.duration_seconds)
    await quota_service.enforce_concurrent_job_limit(db, user.id)

    key = idempotency_key or hashlib.sha256(
        f"{user.id}:{payload.model_dump_json()}".encode()
    ).hexdigest()

    existing_job = await quota_service.find_existing_job_by_idempotency_key(db, key)
    if existing_job is not None:
        return GenerateVideoResponse(
            video_id=existing_job.video_id,
            status="queued",
            job_id=existing_job.id,
            message="Video generation already queued for this idempotency key",
        )

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
    )

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
