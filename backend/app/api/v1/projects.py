"""Project CRUD."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.project import Project
from app.db.models.user import User
from app.db.models.video import Video, VideoStatus
from app.db.session import get_db
from app.security.permissions import require_project_owner

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    niche: str | None = None
    brand_context: dict = Field(default_factory=dict)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    niche: str | None
    brand_context: dict
    description: str | None

    class Config:
        from_attributes = True


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Project:
    project = Project(user_id=user.id, **payload.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[Project]:
    result = await db.execute(select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Project:
    return await require_project_owner(db, project_id, user.id)


class ProjectVideoSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic: str
    status: VideoStatus
    progress: int
    platform: str
    language: str
    duration_seconds: int
    output_asset_id: uuid.UUID | None
    thumbnail_asset_id: uuid.UUID | None
    created_at: datetime


class ProjectVideoPage(BaseModel):
    items: list[ProjectVideoSummary]
    total: int
    limit: int
    offset: int


@router.get("/{project_id}/videos", response_model=ProjectVideoPage)
async def list_project_videos(
    project_id: uuid.UUID,
    status_filter: VideoStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectVideoPage:
    # Authorize the parent project even when it has no videos.
    await require_project_owner(db, project_id, user.id)
    conditions = [Video.project_id == project_id]
    if status_filter is not None:
        conditions.append(Video.status == status_filter)

    total = await db.scalar(select(func.count(Video.id)).where(*conditions))
    result = await db.execute(
        select(Video).where(*conditions).order_by(Video.created_at.desc(), Video.id.desc()).limit(limit).offset(offset)
    )
    return ProjectVideoPage(
        items=[ProjectVideoSummary.model_validate(v) for v in result.scalars().all()],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    project = await require_project_owner(db, project_id, user.id)
    await db.delete(project)
    await db.commit()
