"""
Quota / idempotency enforcement, called before any expensive generation
is queued (blueprint: "Cost control", "Idempotent expensive operations").
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models.generation_job import GenerationJob, JobStatus
from app.db.models.video import Video

settings = get_settings()


async def enforce_max_duration(duration_seconds: int) -> None:
    if duration_seconds > settings.max_video_duration_seconds:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"duration_seconds exceeds the plan maximum of {settings.max_video_duration_seconds}s",
        )


async def enforce_concurrent_job_limit(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(func.count(GenerationJob.id))
        .join(Video, Video.id == GenerationJob.video_id)
        .join(Video.project)
        .where(Video.project.has(user_id=user_id))
        .where(GenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING]))
    )
    active = result.scalar_one()
    if active >= settings.max_concurrent_jobs_per_user:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Concurrent job limit reached ({settings.max_concurrent_jobs_per_user}). "
            "Wait for an existing job to finish or cancel one.",
        )


async def find_existing_job_by_idempotency_key(db: AsyncSession, idempotency_key: str) -> GenerationJob | None:
    result = await db.execute(
        select(GenerationJob).where(GenerationJob.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()
