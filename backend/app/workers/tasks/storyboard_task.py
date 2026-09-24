"""Persists the validated plan as Script + Scene rows."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas.video_plan import VideoPlan
from app.db.models.scene import Scene
from app.db.models.script import Script
from app.db.models.video import Video
from app.services.content_service import persist_plan


async def run(db: AsyncSession, video: Video, plan: VideoPlan) -> tuple[Script, list[Scene]]:
    return await persist_plan(db, video, plan)
