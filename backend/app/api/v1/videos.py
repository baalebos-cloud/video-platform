"""
Video generation lifecycle — this is the centerpiece endpoint described
in blueprint section 8.2 (`POST /videos/generate`) plus status/progress
polling (8.4).
"""
import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from typing import Literal
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.db.models.script import Script
from app.db.models.scene import Scene
from app.db.models.generation_job import GenerationJob, JobType, JobStatus
from app.db.models.asset import Asset, AssetType
from app.workers.queue import enqueue
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.session import get_db
from app.security.permissions import require_project_owner, require_video_owner
from app.security.rate_limit import RateLimiter
from app.services import quota_service, video_service

router = APIRouter(prefix="/videos", tags=["videos"])

generate_rate_limiter = RateLimiter(limit=10, window_seconds=60, scope="video_generate")


class VoicePreferences(BaseModel):
    mode: Literal["auto", "recorded"] = "auto"
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
    language: Literal["English", "Nigerian Pidgin", "Yoruba"] = "English"
    locale: str = "en-US"
    duration_seconds: int = Field(default=60, ge=5, le=180)
    platform: str = "youtube_shorts"
    visual_style: str = "cinematic_realistic"
    creativity: str = "high"
    caption_style: Literal["none", "classic", "bold", "social", "minimal"] = "none"
    voice: VoicePreferences = Field(default_factory=VoicePreferences)

    @model_validator(mode="after")
    def ensure_supported_narration(self):
        locale_options = {
            "English": {"en-US", "en-NG", "en-GB"},
            "Nigerian Pidgin": {"pcm-NG"},
            "Yoruba": {"yo-NG"},
        }
        if self.locale not in locale_options[self.language]:
            raise ValueError("Select the locale matching the chosen language")
        if self.language != "English" and self.voice.mode != "recorded":
            raise ValueError(
                "Yoruba and Nigerian Pidgin require your recorded narration; "
                "the configured automatic TTS does not support these languages"
            )
        return self


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
    needs_rerender: bool = False

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
    settings = get_settings()
    if settings.app_env == "production":
        if settings.image_provider == "mock" or settings.voice_provider == "mock" or settings.llm_provider == "mock":
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Production video generation needs real AI planning, image and voice providers; configure the Railway worker and API.",
            )
        if settings.llm_provider == "baalebos_ai" and not settings.llm_gateway_url:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "AI planning gateway is not configured",
            )
    await require_project_owner(db, payload.project_id, user.id)
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

    await quota_service.enforce_max_duration(payload.duration_seconds)
    await quota_service.enforce_concurrent_job_limit(db, user.id)
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
            caption_style=payload.caption_style,
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


def public_generation_error_message(message: str | None) -> str | None:
    """Legacy failures were stored verbatim; do not re-expose Pydantic payloads.

    Updating the worker cannot retroactively repair failed generation jobs.
    This message explicitly distinguishes saved failures from new attempts.
    """
    if message and message.startswith("AI director output failed validation:") and "validation errors for VideoPlan" in message:
        return (
            "This video failed under an older AI director. Its error was saved at "
            "generation time. Deploy the latest worker and start a new video "
            "to verify the fix."
        )
    return message


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
        error_message=public_generation_error_message(video.error_message),
        output_asset_id=video.output_asset_id,
        thumbnail_asset_id=video.thumbnail_asset_id,
        project_id=video.project_id,
        topic=video.topic,
        platform=video.platform,
        language=video.language,
        duration_seconds=video.duration_seconds,
        needs_rerender=video.needs_rerender,
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


class RerenderResponse(BaseModel):
    video_id: uuid.UUID
    job_id: uuid.UUID
    status: str


@router.post("/{video_id}/rerender", response_model=RerenderResponse)
async def rerender_video(
    video_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(RateLimiter(limit=3, window_seconds=60, scope="video_rerender")),
    db: AsyncSession = Depends(get_db),
) -> RerenderResponse:
    """Queue a render of persisted scene images/audio, without buying new AI assets."""
    await require_video_owner(db, video_id, user.id)
    await quota_service.enforce_concurrent_job_limit(db, user.id)

    # Serialize against another request and storyboard mutations. Unlike a
    # read-then-write check, this prevents two simultaneous render jobs.
    result = await db.execute(select(Video).where(Video.id == video_id).with_for_update().execution_options(populate_existing=True))
    video = result.scalar_one()
    if video.status != VideoStatus.READY or video.output_asset_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Video is not ready for re-rendering")
    if not video.needs_rerender:
        raise HTTPException(status.HTTP_409_CONFLICT, "Regenerate a scene image before re-rendering")

    result = await db.execute(select(Scene).where(Scene.video_id == video.id))
    scenes = list(result.scalars().all())
    if not scenes or any(s.visual_asset_id is None or s.audio_asset_id is None for s in scenes):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Some scenes have no saved images or narration. Create a new video to enable re-rendering.",
        )

    job = GenerationJob(video_id=video.id, type=JobType.RENDER, status=JobStatus.QUEUED)
    db.add(job)
    video.status = VideoStatus.RENDERING
    video.progress = 85
    video.current_stage = "rerender_queued"
    video.error_message = None
    await db.commit()
    await db.refresh(job)

    try:
        queued_id = await enqueue("rerender_video", {"video_id": str(video.id), "job_id": str(job.id)})
        if not queued_id:
            raise RuntimeError("Queue rejected render job")
    except Exception:
        video.status = VideoStatus.READY
        video.progress = 100
        video.current_stage = "rerender_failed"
        video.error_message = "Unable to queue re-render. Please retry."
        job.status = JobStatus.FAILED
        job.error_code = "queue_unavailable"
        job.error_message = video.error_message
        await db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Re-render queue unavailable")

    return RerenderResponse(video_id=video.id, job_id=job.id, status="queued")


class RetryGenerationResponse(BaseModel):
    video_id: uuid.UUID
    job_id: uuid.UUID
    status: str
    message: str


@router.post("/{video_id}/retry", response_model=RetryGenerationResponse)
async def retry_failed_video(
    video_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(RateLimiter(limit=3, window_seconds=60, scope="retry_failed_video")),
    db: AsyncSession = Depends(get_db),
) -> RetryGenerationResponse:
    """Start one new video per failed source, preserving the failed original.

    A retry is a NEW generation and may cost credits; it is never an
    unsafe replay of a worker's partially completed side effects.
    """
    await require_video_owner(db, video_id, user.id)
    source = await db.scalar(select(Video).where(Video.id == video_id).with_for_update())
    if source is None or source.status != VideoStatus.FAILED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed videos can be retried")
    retry_key = hashlib.sha256(f"{user.id}:retry:{video_id}".encode()).hexdigest()
    previous = await quota_service.find_existing_job_by_idempotency_key(db, retry_key)
    if previous:
        return RetryGenerationResponse(video_id=previous.video_id, job_id=previous.id,
            status=previous.status.value, message="Existing retry returned")

    await quota_service.enforce_concurrent_job_limit(db, user.id)
    from app.config.settings import get_settings
    if source.duration_seconds > get_settings().max_video_duration_seconds:
        raise HTTPException(status.HTTP_409_CONFLICT, "Video duration now exceeds the generation limit")
    # Snapshot all source settings so the retry is reproducible.
    spec = {
        "project_id": str(source.project_id), "topic": source.topic,
        "language": source.language, "locale": source.locale,
        "duration_seconds": source.duration_seconds,
        "platform": source.platform, "visual_style": source.visual_style,
        "creativity": source.creativity, "voice_preferences": source.voice_preferences,
    }
    fingerprint = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    try:
        video, job = await video_service.start_generation(
            db, project_id=source.project_id, topic=source.topic,
            language=source.language, locale=source.locale,
            duration_seconds=source.duration_seconds, platform=source.platform,
            visual_style=source.visual_style, creativity=source.creativity,
            voice_preferences=source.voice_preferences, caption_style=source.caption_style,
            idempotency_key=retry_key,
            input_hash=fingerprint,
        )
    except IntegrityError:
        await db.rollback()
        previous = await quota_service.find_existing_job_by_idempotency_key(db, retry_key)
        if previous:
            return RetryGenerationResponse(video_id=previous.video_id, job_id=previous.id,
                status=previous.status.value, message="Existing retry returned")
        raise
    return RetryGenerationResponse(video_id=video.id, job_id=job.id, status="queued",
        message="New generation queued. Your original failed video is preserved.")


@router.get("/{video_id}/jobs")
async def video_job_history(
    video_id: uuid.UUID,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Owner-only recent attempt history for support and generation diagnosis."""
    await require_video_owner(db, video_id, user.id)
    result = await db.execute(select(GenerationJob).where(
        GenerationJob.video_id == video_id,
    ).order_by(GenerationJob.created_at.desc()).limit(20))
    return {"items": [
        {"id": str(job.id), "type": job.type.value, "status": job.status.value,
         "attempts": job.attempts, "error_code": job.error_code,
         "created_at": job.created_at, "updated_at": job.updated_at}
        for job in result.scalars().all()
    ]}
