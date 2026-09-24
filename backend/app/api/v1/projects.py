"""Project CRUD."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.project import Project
from app.db.models.user import User
from app.db.session import get_db
from app.security.permissions import require_project_owner

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    niche: str | None = None
    brand_context: dict = {}
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


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    project = await require_project_owner(db, project_id, user.id)
    await db.delete(project)
    await db.commit()
