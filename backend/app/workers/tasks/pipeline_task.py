"""
The umbrella "generation_pipeline" arq task — mirrors blueprint section
24.1 (worker flow) end to end: plan -> script -> storyboard -> voice ->
visuals -> captions -> timeline -> render -> asset registration.

Every stage updates the GenerationJob and Video rows so the frontend can
poll GET /api/v1/videos/{id} for live progress, and every stage is wrapped
so a failure marks the job FAILED with a stable error_code rather than
crashing the worker silently.
"""
import uuid

from app.ai.director.director import PlanValidationError
from app.config.logging import get_logger
from app.db.models.generation_job import GenerationJob, JobStatus
from app.db.models.video import Video, VideoStatus
from app.db.session import session_scope
from app.services.storage_service import put_object
from app.workers.tasks import render_task, script_task, storyboard_task, visual_task, voice_task

logger = get_logger("workers.pipeline")

STAGE_WEIGHTS = {
    "planning": 10,
    "scripting": 10,
    "storyboarding": 10,
    "generating_assets": 50,
    "rendering": 15,
    "finalizing": 5,
}


async def _mark_stage(db, video: Video, job: GenerationJob, stage: str, progress: int) -> None:
    video.status = VideoStatus(stage) if stage in VideoStatus._value2member_map_ else video.status
    video.current_stage = stage
    video.progress = progress
    job.status = JobStatus.RUNNING
    await db.flush()


async def generation_pipeline(ctx, payload: dict) -> None:
    video_id = uuid.UUID(payload["video_id"])
    job_id = uuid.UUID(payload["job_id"])

    async with session_scope() as db:
        video = await db.get(Video, video_id)
        job = await db.get(GenerationJob, job_id)
        if video is None or job is None:
            logger.error("pipeline.missing_records", video_id=str(video_id), job_id=str(job_id))
            return

        job.attempts += 1
        try:
            # --- 1. Plan (script + storyboard spec) ---
            await _mark_stage(db, video, job, "planning", 5)
            plan, plan_metadata = await script_task.run(video)

            await _mark_stage(db, video, job, "scripting", STAGE_WEIGHTS["planning"])
            await _mark_stage(db, video, job, "storyboarding", STAGE_WEIGHTS["planning"] + STAGE_WEIGHTS["scripting"])
            script, scenes = await storyboard_task.run(db, video, plan)

            # --- 2. Per-scene asset generation (voice + visuals) ---
            await _mark_stage(
                db, video, job, "generating_assets",
                STAGE_WEIGHTS["planning"] + STAGE_WEIGHTS["scripting"] + STAGE_WEIGHTS["storyboarding"],
            )
            scene_assets: dict[str, dict] = {}
            for scene in scenes:
                audio_key, duration = await voice_task.run(video, scene)
                image_key = await visual_task.run(video, scene)
                scene.duration_seconds = duration
                scene_assets[str(scene.id)] = {"image_key": image_key, "audio_key": audio_key, "duration": duration}
            await db.flush()

            # --- 3. Render final video ---
            await _mark_stage(
                db, video, job, "rendering",
                STAGE_WEIGHTS["planning"] + STAGE_WEIGHTS["scripting"]
                + STAGE_WEIGHTS["storyboarding"] + STAGE_WEIGHTS["generating_assets"],
            )
            render_result = await render_task.run(video, scenes, scene_assets)

            # --- 4. Register final asset ---
            from app.db.models.asset import Asset, AssetType
            from app.db.models.project import Project

            project = await db.get(Project, video.project_id)

            final_asset = Asset(
                owner_id=project.user_id,
                type=AssetType.FINAL_VIDEO,
                storage_key=render_result["final_video_key"],
                mime_type="video/mp4",
            )
            db.add(final_asset)
            await db.flush()

            video.output_asset_id = final_asset.id
            video.status = VideoStatus.READY
            video.progress = 100
            video.current_stage = "completed"
            job.status = JobStatus.SUCCEEDED
            job.output_asset_ids = [str(final_asset.id)]

            logger.info("pipeline.succeeded", video_id=str(video_id))

        except PlanValidationError as exc:
            job.status = JobStatus.FAILED
            job.error_code = "plan_validation_failed"
            job.error_message = str(exc)
            video.status = VideoStatus.FAILED
            video.error_message = str(exc)
            logger.error("pipeline.plan_validation_failed", video_id=str(video_id), error=str(exc))

        except Exception as exc:  # noqa: BLE001 — top-level pipeline guard; see docs/runbooks/
            job.status = JobStatus.FAILED
            job.error_code = "pipeline_error"
            job.error_message = str(exc)[:2000]
            video.status = VideoStatus.FAILED
            video.error_message = str(exc)[:2000]
            logger.error("pipeline.failed", video_id=str(video_id), error=str(exc))
