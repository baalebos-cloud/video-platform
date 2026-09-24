"""
Video service — creates video + job records and enqueues the async
generation pipeline. This is the synchronous, fast-responding half of
the flow described in blueprint section 24 ("Example Backend Service
Flow"); the actual generation work happens in app/workers.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.generation_job import GenerationJob, JobStatus, JobType
from app.db.models.video import Video, VideoStatus
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
) -> tuple[Video, GenerationJob]:
    video = Video(
        project_id=project_id,
        topic=topic,
        language=language,
        locale=locale,
        duration_seconds=duration_seconds,
        platform=platform,
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
    )
    db.add(job)
    await db.flush()
    await db.commit()

    await enqueue("generation_pipeline", {"video_id": str(video.id), "job_id": str(job.id)})
    return video, job
