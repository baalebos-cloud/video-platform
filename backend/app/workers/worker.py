"""
arq worker process entrypoint.

Run with:  arq app.workers.worker.WorkerSettings
(see infra/docker/worker.Dockerfile and docker-compose.yml)
"""
from arq.connections import RedisSettings

from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.config.release import current_release
from app.ai.providers.cloudflare_http import CloudflareRequestError, verify_cloudflare_access
from app.workers.tasks.pipeline_task import generation_pipeline
from app.workers.tasks.publish_task import publish_task
from app.workers.tasks.rerender_task import rerender_video

settings = get_settings()
configure_logging(settings.debug)
logger = get_logger("worker")


async def startup(ctx):
    logger.info("worker.startup", env=settings.app_env, **current_release())
    if settings.voice_provider == "cloudflare" or settings.image_provider == "cloudflare":
        try:
            status = await verify_cloudflare_access(
                account_id=settings.cloudflare_account_id or "",
                api_token=settings.cloudflare_api_token or "",
            )
        except CloudflareRequestError as exc:
            logger.error(
                "worker.cloudflare_preflight_failed",
                reason=exc.reason, probe="read_only_model_search",
            )
        else:
            logger.info(
                "worker.cloudflare_preflight_result",
                http_status=status,
                authorized=status == 200,
                probe="read_only_model_search",
            )


async def shutdown(ctx):
    logger.info("worker.shutdown")


class WorkerSettings:
    functions = [generation_pipeline, publish_task, rerender_video]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    # A full-HD FFmpeg render is memory intensive. Process one video at a time.
    max_jobs = 1
    job_timeout = 900  # 15 minutes — generous ceiling for a full render
