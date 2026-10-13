"""
Video service — creates video + job records and enqueues the async
generation pipeline. This is the synchronous, fast-responding half of
the flow described in blueprint section 24 ("Example Backend Service
Flow"); the actual generation work happens in app/workers.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.generation_job import GenerationJob, JobStatus, JobType
from app.db.models.video import Video, VideoStatus
from app.db.models.project import Project
from app.services import credit_service
from app.config.settings import get_settings
from app.workers.queue import enqueue


async def start_generation(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    topic: str,
    language: str,
    locale: str,
    duration_seconds: int,
    platform: str,
    visual_style: str,
    creativity: str,
    voice_preferences: dict,
    idempotency_key: str | None,
    input_hash: str,
) -> tuple[Video, GenerationJob]:
    video = Video(
        project_id=project_id,
        topic=topic,
        language=language,
        locale=locale,
        duration_seconds=duration_seconds,
        platform=platform,
        aspect_ratio="16:9" if platform == "youtube_landscape" else "9:16",
        visual_style=visual_style,
        creativity=creativity,
        voice_preferences=voice_preferences,
        status=VideoStatus.QUEUED,
    )
    db.add(video)
    await db.flush()

    job = GenerationJob(
        video_id=video.id,
        type=JobType.VIDEO_GENERATION,
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        input_hash=input_hash,
    )
    db.add(job)
    await db.flush()
    settings = get_settings()
    if settings.credit_enforcement_enabled:
        project = await db.get(Project, project_id)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
        await credit_service.debit(
            db, project.user_id, credit_service.generation_price(duration_seconds),
            reference_type="video_generation", reference_id=str(job.id),
            metadata={
                "video_id": str(video.id), "duration_seconds": duration_seconds,
                "voice_provider": settings.voice_provider, "image_provider": settings.image_provider,
            },
        )
    await db.commit()

    try:
        queue_job_id = await enqueue("generation_pipeline", {"video_id": str(video.id), "job_id": str(job.id)})
        if not queue_job_id:
            raise RuntimeError("Queue rejected the job")
    except Exception:
        # Database inserts have committed, so persist a visible failed state
        # rather than leaving the user with an indefinitely queued job.
        video.status = VideoStatus.FAILED
        video.error_message = "Unable to queue generation. Please try again."
        job.status = JobStatus.FAILED
        job.error_code = "queue_unavailable"
        job.error_message = video.error_message
        if settings.credit_enforcement_enabled:
            await credit_service.refund(
                db, project.user_id,
                reference_type="video_generation", reference_id=str(job.id),
            )
        await db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Generation queue unavailable")
    return video, job
