"""
Object-level authorization helpers.

Every project/video-scoped endpoint must call one of these before acting,
to prevent horizontal privilege escalation between users.
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.project import Project
from app.db.models.video import Video


async def require_project_owner(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if project.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this project")
    return project


async def require_video_owner(db: AsyncSession, video_id: uuid.UUID, user_id: uuid.UUID) -> Video:
    result = await db.execute(select(Video).where(Video.id == video_id))
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    await require_project_owner(db, video.project_id, user_id)
    return video
