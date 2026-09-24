"""Generates and validates the AI Video Director's plan (script + storyboard spec)."""
from app.ai.schemas.video_plan import VideoPlan
from app.db.models.video import Video
from app.services.content_service import generate_plan_for_video


async def run(video: Video) -> tuple[VideoPlan, dict]:
    return await generate_plan_for_video(video)
