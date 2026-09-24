"""Job status polling."""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.generation_job import GenerationJob
from app.db.models.user import User
from app.db.session import get_db
from app.security.permissions import require_video_owner

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    type: str
    status: str
    attempts: int
    error_code: str | None
    error_message: str | None

    class Config:
        from_attributes = True


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.get(GenerationJob, job_id)
    if job is None:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    await require_video_owner(db, job.video_id, user.id)
    return job
