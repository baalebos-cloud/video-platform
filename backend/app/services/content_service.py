"""
Content service — orchestrates script + storyboard generation via the
AI Video Director, and persists the results.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.director.director import create_plan
from app.ai.schemas.video_plan import VideoPlan
from app.db.models.scene import Scene
from app.db.models.script import Script
from app.db.models.video import Video
from app.config.logging import get_logger

logger = get_logger("services.content")


async def generate_plan_for_video(video: Video) -> tuple[VideoPlan, dict]:
    return await create_plan(
        topic=video.topic,
        language=video.language,
        locale=video.locale,
        platform=video.platform,
        duration=video.duration_seconds,
        voice_preferences=video.voice_preferences,
        visual_style=video.visual_style,
        creativity=video.creativity,
    )


async def persist_plan(db: AsyncSession, video: Video, plan: VideoPlan) -> tuple[Script, list[Scene]]:
    script = Script(video_id=video.id, version=1, content=plan.script, language=video.language)
    db.add(script)

    scenes: list[Scene] = []
    for scene_spec in plan.scenes:
        scene = Scene(
            video_id=video.id,
            sequence=scene_spec.sequence,
            narration=scene_spec.narration,
            visual_prompt=scene_spec.visual_prompt,
            duration_seconds=scene_spec.duration_seconds,
            camera=scene_spec.camera,
            lighting=scene_spec.lighting,
            on_screen_text=scene_spec.on_screen_text,
            continuity_reference_ids=scene_spec.continuity_reference_ids,
            negative_constraints=scene_spec.negative_constraints,
            metadata_json={
                "title": plan.title,
                "hook": plan.hook,
                "hashtags": plan.hashtags,
                "cta": plan.cta,
                "thumbnail_prompt": plan.thumbnail_prompt,
            },
        )
        db.add(scene)
        scenes.append(scene)

    await db.flush()
    logger.info("content.plan_persisted", video_id=str(video.id), scene_count=len(scenes))
    return script, scenes
