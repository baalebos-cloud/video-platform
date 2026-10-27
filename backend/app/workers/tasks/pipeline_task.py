"""
The umbrella "generation_pipeline" arq task — mirrors blueprint section
24.1 (worker flow) end to end: plan -> script -> storyboard -> voice ->
visuals -> captions -> timeline -> render -> asset registration.

Every stage updates the GenerationJob and Video rows so the frontend can
poll GET /api/v1/videos/{id} for live progress, and every stage is wrapped
so a failure marks the job FAILED with a stable error_code rather than
crashing the worker silently.
"""
import re
import uuid

from app.ai.director.director import PlanValidationError
from app.ai.providers.openai_http import MediaProviderError
from app.ai.providers.cloudflare_http import CloudflareRequestError
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.config.release import current_release
from app.db.models.asset import Asset, AssetType
from app.db.models.project import Project
from app.db.models.scene import Scene
from app.db.models.generation_job import GenerationJob, JobStatus
from app.db.models.video import Video, VideoStatus
from app.db.session import session_scope
from app.services.storage_service import put_object
from app.workers.tasks import render_task, script_task, storyboard_task, visual_task, voice_task
from app.services import credit_service
from app.services.provider_guard import MediaGuardError

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
    # Commit each stage, so clients can observe progress from other DB sessions.
    await db.commit()


def require_live_output_providers(
    plan_metadata: dict, provider_settings, voice_mode: str = "auto",
) -> None:
    """Require real planning/visuals, and TTS only when the video uses TTS.

    Recorded narration and an independently licensed cloned voice never call
    the platform's ordinary voice provider, so its mock setting is irrelevant.
    """
    if provider_settings.app_env != "production":
        return
    if (
        (voice_mode == "auto" and provider_settings.voice_provider == "mock")
        or provider_settings.image_provider == "mock"
        or plan_metadata.get("llm_provider") == "mock"
    ):
        raise PlanValidationError(
            "Production requires real planning and image providers. "
            "Automatic narration also requires a real voice provider."
        )



def provider_failure_details(stage: str, exc: MediaProviderError) -> tuple[str, str, int | None]:
    """Convert already-sanitized provider failures into stable, actionable states.

    Never forward raw third-party response bodies, exception headers or tokens.
    """
    if isinstance(exc, CloudflareRequestError):
        labels = {
            "missing_credentials": (
                "media_cloudflare_missing_credentials",
                "Cloudflare Workers AI credentials are missing on the Railway worker.",
            ),
            "invalid_account_id": (
                "media_cloudflare_account",
                "Cloudflare Workers AI account ID format is invalid. Copy the 32-character Account ID, not the API token.",
            ),
            "invalid_token_format": (
                "media_cloudflare_token",
                "Cloudflare Workers AI API token contains invalid formatting. Check the Railway secret without sharing it.",
            ),
            "invalid_model": (
                "media_cloudflare_model",
                "Cloudflare model ID is invalid. Check CLOUDFLARE_TTS_MODEL and CLOUDFLARE_IMAGE_MODEL.",
            ),
            "invalid_client_request": (
                "media_cloudflare_request",
                "Cloudflare request could not be constructed. Verify the worker's Cloudflare configuration.",
            ),
            "connection_failed": (
                "media_cloudflare_connection",
                "Cloudflare connection failed before a response. Check worker outbound networking and Cloudflare status.",
            ),
            "request_timeout": (
                "media_cloudflare_timeout",
                "Cloudflare request timed out. Retry when provider connectivity recovers.",
            ),
        }
        code, detail = labels[exc.reason]
        return (code, detail, None)
    if isinstance(exc, MediaGuardError):
        if exc.reason == "daily_quota_exceeded":
            return (
                "media_daily_limit",
                "Daily media-call safety limit reached. Check MAX_DAILY_LIVE_MEDIA_CALLS "
                "and your providers' free-tier allowances before starting another video.",
                None,
            )
        return (
            "media_guard_redis_unavailable",
            "Media request quota could not be verified in Redis. "
            "Check the worker's Redis connection and provider_guard logs.",
            None,
        )
    match = re.search(r"\bHTTP (400|401|403|404|408|429|500|502|503|504)\b", str(exc))
    http_status = int(match.group(1)) if match else None
    planning = stage == "planning"
    scope = "planning" if planning else "media"
    display = "Gemini planning" if planning else "AI media generation"

    if http_status in (401, 403):
        return (f"{scope}_credentials", f"{display} was denied access (HTTP {http_status}). Check the provider key and API permissions in Railway.", http_status)
    if http_status == 404:
        return (f"{scope}_model", f"{display} model was not found (HTTP 404). Check the configured model ID and project access.", http_status)
    if http_status == 429:
        return (f"{scope}_quota", f"{display} reached a quota or rate limit (HTTP 429). Check your provider's free-tier usage before retrying.", http_status)
    if http_status == 400:
        return (f"{scope}_request", f"{display} rejected its request (HTTP 400). Check the model and request format.", http_status)
    if http_status in (408, 500, 502, 503, 504):
        return (f"{scope}_unavailable", f"{display} is temporarily unavailable (HTTP {http_status}). Retry later.", http_status)
    return (f"{scope}_unavailable", f"{display} could not complete the request. Check worker logs and provider status.", None)


def scene_runtime_floor(scenes: list[Scene], requested_seconds: int) -> dict[str, float]:
    """Distribute a full-length video's requested runtime across planned scenes.

    The director must first validate sufficient spoken content. The TTS audio
    may speak faster than predicted; preserving each scene's planned runtime
    prevents a 180-second project silently exporting as a short-form MP4.
    Short-form videos keep their previous measured-narration behavior.
    """
    if requested_seconds < 90:
        return {}
    planned = sum(max(0.0, float(scene.duration_seconds)) for scene in scenes)
    if planned <= 0:
        raise PlanValidationError("AI director supplied no usable long-form scene durations.")
    ratio = max(1.0, requested_seconds / planned)
    return {
        str(scene.id): round(float(scene.duration_seconds) * ratio, 3)
        for scene in scenes
    }


async def generation_pipeline(ctx, payload: dict) -> None:
    video_id = uuid.UUID(payload["video_id"])
    job_id = uuid.UUID(payload["job_id"])

    async with session_scope() as db:
        video = await db.get(Video, video_id)
        job = await db.get(GenerationJob, job_id)
        if video is None or job is None:
            logger.error("pipeline.missing_records", video_id=str(video_id), job_id=str(job_id))
            return

        project = await db.get(Project, video.project_id)
        if project is None:
            logger.error("pipeline.missing_project", video_id=str(video_id))
            return

        job.attempts += 1
        logger.info("pipeline.worker_revision", video_id=str(video_id), **current_release())
        try:
            # --- 1. Plan (script + storyboard spec) ---
            await _mark_stage(db, video, job, "planning", 5)
            plan, plan_metadata = await script_task.run(video)
            require_live_output_providers(
                plan_metadata, get_settings(),
                voice_mode=(video.voice_preferences or {}).get("mode", "auto"),
            )

            await _mark_stage(db, video, job, "scripting", STAGE_WEIGHTS["planning"])
            await _mark_stage(db, video, job, "storyboarding", STAGE_WEIGHTS["planning"] + STAGE_WEIGHTS["scripting"])
            script, scenes = await storyboard_task.run(db, video, plan)
            runtime_floor = scene_runtime_floor(scenes, video.duration_seconds)

            # --- 2. Per-scene asset generation (voice + visuals) ---
            await _mark_stage(
                db, video, job, "generating_assets",
                STAGE_WEIGHTS["planning"] + STAGE_WEIGHTS["scripting"] + STAGE_WEIGHTS["storyboarding"],
            )
            scene_assets: dict[str, dict] = {}
            provider_settings = get_settings()
            for scene in scenes:
                logger.info(
                    "pipeline.scene_voice_started",
                    video_id=str(video_id), scene_sequence=scene.sequence,
                    provider=provider_settings.voice_provider,
                )
                audio_key, voice_seconds = await voice_task.run(video, scene, owner_id=project.user_id)
                duration = max(voice_seconds, runtime_floor.get(str(scene.id), 0.0))
                logger.info(
                    "pipeline.scene_voice_ready",
                    video_id=str(video_id), scene_sequence=scene.sequence,
                    measured_voice_seconds=round(voice_seconds, 2),
                    planned_clip_seconds=round(duration, 2),
                )
                logger.info(
                    "pipeline.scene_visual_started",
                    video_id=str(video_id), scene_sequence=scene.sequence,
                )
                visual = await visual_task.run(video, scene)
                logger.info(
                    "pipeline.scene_visual_ready",
                    video_id=str(video_id), scene_sequence=scene.sequence,
                    provider=visual["provider"],
                )
                image_key = visual["image_key"]
                stock_key = visual.get("video_key")
                if stock_key:
                    scene.metadata_json = {**(scene.metadata_json or {}),
                        "stock_footage_key": stock_key,
                        "stock_source_url": visual.get("source_url")}

                audio_asset = Asset(
                    owner_id=project.user_id,
                    type=AssetType.AUDIO,
                    storage_key=audio_key,
                    mime_type="audio/wav",
                    provider_metadata={
                        "provider": "recording_pending" if (video.voice_preferences or {}).get("mode") == "recorded" else provider_settings.voice_provider,
                        "recording_pending": (video.voice_preferences or {}).get("mode") == "recorded",
                        "model": (
                            provider_settings.openai_tts_model
                            if provider_settings.voice_provider == "openai"
                            else provider_settings.cloudflare_tts_model
                            if provider_settings.voice_provider == "cloudflare" else "mock"
                        ),
                    },
                )
                image_asset = Asset(
                    owner_id=project.user_id,
                    type=AssetType.IMAGE,
                    storage_key=image_key,
                    mime_type="image/png",
                    provider_metadata={
                        "provider": visual["provider"],
                        "model": (
                            provider_settings.openai_image_model
                            if visual["provider"] == "openai"
                            else provider_settings.cloudflare_image_model
                            if visual["provider"] == "cloudflare" else "stock"
                        ),
                        **({"source_url": visual["source_url"]} if visual.get("source_url") else {}),
                    },
                )
                db.add_all([audio_asset, image_asset])
                await db.flush()
                scene.audio_asset_id = audio_asset.id
                scene.visual_asset_id = image_asset.id
                scene.duration_seconds = duration
                scene_assets[str(scene.id)] = {
                    "image_key": image_key, "audio_key": audio_key, "duration": duration,
                    **({"video_key": stock_key} if stock_key else {}),
                }
            await db.flush()

            # --- 3. Render final video ---
            await _mark_stage(
                db, video, job, "rendering",
                STAGE_WEIGHTS["planning"] + STAGE_WEIGHTS["scripting"]
                + STAGE_WEIGHTS["storyboarding"] + STAGE_WEIGHTS["generating_assets"],
            )
            render_result = await render_task.run(video, scenes, scene_assets)

            # --- 4. Register final asset ---
            final_asset = Asset(
                owner_id=project.user_id,
                type=AssetType.FINAL_VIDEO,
                storage_key=render_result["final_video_key"],
                mime_type="video/mp4",
            )
            thumbnail_asset = Asset(
                owner_id=project.user_id,
                type=AssetType.THUMBNAIL,
                storage_key=render_result["thumbnail_key"],
                mime_type="image/png",
            )
            db.add_all([final_asset, thumbnail_asset])
            await db.flush()

            video.output_asset_id = final_asset.id
            video.thumbnail_asset_id = thumbnail_asset.id
            video.status = VideoStatus.READY
            video.progress = 100
            video.current_stage = "completed"
            job.status = JobStatus.SUCCEEDED
            job.output_asset_ids = [str(final_asset.id)]

            logger.info("pipeline.succeeded", video_id=str(video_id))

        except MediaProviderError as exc:
            # Third-party providers sanitize their own exceptions, but we also
            # map them to fixed descriptions rather than publishing exception text.
            code, message, http_status = provider_failure_details(video.current_stage or "", exc)
            job.status = JobStatus.FAILED
            job.error_code = code
            job.error_message = message
            video.status = VideoStatus.FAILED
            video.error_message = message
            await credit_service.refund(
                db, project.user_id, reference_type="video_generation", reference_id=str(job.id)
            )
            logger.error(
                "pipeline.provider_failed", video_id=str(video_id),
                stage=video.current_stage, error_code=code, provider_http_status=http_status,
            )

        except PlanValidationError as exc:
            job.status = JobStatus.FAILED
            job.error_code = "plan_validation_failed"
            job.error_message = str(exc)
            video.status = VideoStatus.FAILED
            video.error_message = str(exc)
            await credit_service.refund(db, project.user_id, reference_type="video_generation", reference_id=str(job.id))
            logger.error("pipeline.plan_validation_failed", video_id=str(video_id), error=str(exc))

        except Exception as exc:  # noqa: BLE001 — top-level pipeline guard; see docs/runbooks/
            job.status = JobStatus.FAILED
            job.error_code = "pipeline_error"
            # Never put provider exceptions (which may contain secrets or
            # untrusted HTTP response bodies) in customer-visible responses.
            job.error_message = "Video generation failed. You may retry from the studio."
            video.status = VideoStatus.FAILED
            video.error_message = job.error_message
            await credit_service.refund(db, project.user_id, reference_type="video_generation", reference_id=str(job.id))
            logger.error("pipeline.failed", video_id=str(video_id), error_type=type(exc).__name__)
