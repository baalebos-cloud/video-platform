"""Render a new final MP4 using existing, persisted scene assets.

The previous final video remains linked and playable until successful
replacement.  No LLM, TTS, or image provider is called here.
"""
import uuid
from sqlalchemy import select

from app.config.logging import get_logger
from app.db.models.asset import Asset, AssetType
from app.db.models.generation_job import GenerationJob, JobStatus, JobType
from app.db.models.project import Project
from app.db.models.scene import Scene
from app.db.models.video import Video, VideoStatus
from app.db.session import session_scope
from app.workers.tasks import render_task

logger = get_logger("workers.rerender")


def make_asset_manifest(scenes: list[Scene], assets: dict[uuid.UUID, Asset], owner_id: uuid.UUID) -> dict[str, dict]:
    """Reject missing/wrong-owner/wrong-type assets before expensive FFmpeg work."""
    if not scenes:
        raise ValueError("No storyboard scenes available for re-rendering")
    manifest = {}
    for scene in scenes:
        image = assets.get(scene.visual_asset_id)
        audio = assets.get(scene.audio_asset_id)
        if (
            not image or not audio
            or image.owner_id != owner_id or audio.owner_id != owner_id
            or image.type != AssetType.IMAGE or audio.type != AssetType.AUDIO
            or scene.duration_seconds <= 0
        ):
            raise ValueError("A storyboard scene is missing a valid saved image or narration")
        stock_key = (getattr(scene, "metadata_json", None) or {}).get("stock_footage_key")
        manifest[str(scene.id)] = {
            "image_key": image.storage_key,
            "audio_key": audio.storage_key,
            "duration": scene.duration_seconds,
            **({"video_key": stock_key} if stock_key else {}),
        }
    return manifest


async def rerender_video(ctx, payload: dict) -> None:
    video_id = uuid.UUID(payload["video_id"])
    job_id = uuid.UUID(payload["job_id"])

    async with session_scope() as db:
        job = await db.get(GenerationJob, job_id)
        video = await db.get(Video, video_id)
        if (
            not job or not video or job.video_id != video.id
            or job.type != JobType.RENDER or job.status != JobStatus.QUEUED
            or video.status != VideoStatus.RENDERING
        ):
            logger.warning("rerender.invalid_job_state", video_id=str(video_id), job_id=str(job_id))
            return

        job.status = JobStatus.RUNNING
        job.attempts += 1
        video.progress = 90
        video.current_stage = "rerendering"
        await db.commit()

        try:
            project = await db.get(Project, video.project_id)
            if project is None:
                raise ValueError("Project not found")
            result = await db.execute(select(Scene).where(Scene.video_id == video.id).order_by(Scene.sequence))
            scenes = list(result.scalars().all())
            asset_ids = [a for s in scenes for a in (s.visual_asset_id, s.audio_asset_id) if a is not None]
            result = await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))
            assets = {a.id: a for a in result.scalars().all()}
            scene_assets = make_asset_manifest(scenes, assets, project.user_id)

            rendered = await render_task.run(video, scenes, scene_assets)
            final_asset = Asset(
                owner_id=project.user_id, type=AssetType.FINAL_VIDEO,
                storage_key=rendered["final_video_key"], mime_type="video/mp4",
            )
            thumbnail = Asset(
                owner_id=project.user_id, type=AssetType.THUMBNAIL,
                storage_key=rendered["thumbnail_key"], mime_type="image/png",
            )
            db.add_all([final_asset, thumbnail])
            await db.flush()

            # Atomic pointer replacement: old final MP4 is untouched until
            # the new render is uploaded and DB asset rows exist.
            video.output_asset_id = final_asset.id
            video.thumbnail_asset_id = thumbnail.id
            video.needs_rerender = False
            video.status = VideoStatus.READY
            video.progress = 100
            video.current_stage = "completed"
            video.error_message = None
            job.status = JobStatus.SUCCEEDED
            job.output_asset_ids = [str(final_asset.id), str(thumbnail.id)]
            await db.commit()
            logger.info("rerender.succeeded", video_id=str(video_id))
        except Exception as exc:
            await db.rollback()
            # Keep existing deliverable and allow re-render retry.
            job = await db.get(GenerationJob, job_id)
            video = await db.get(Video, video_id)
            job.status = JobStatus.FAILED
            job.error_code = "rerender_failed"
            job.error_message = str(exc)[:2000]
            video.status = VideoStatus.READY
            video.progress = 100
            video.current_stage = "rerender_failed"
            video.needs_rerender = True
            video.error_message = "Re-render failed. Original video is still available."
            await db.commit()
            logger.error("rerender.failed", video_id=str(video_id), error=str(exc))
