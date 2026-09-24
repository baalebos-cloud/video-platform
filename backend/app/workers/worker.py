"""
arq worker process entrypoint.

Run with:  arq app.workers.worker.WorkerSettings
(see infra/docker/worker.Dockerfile and docker-compose.yml)
"""
from arq.connections import RedisSettings

from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.workers.tasks.pipeline_task import generation_pipeline
from app.workers.tasks.publish_task import publish_task

settings = get_settings()
configure_logging(settings.debug)
logger = get_logger("worker")


async def startup(ctx):
    logger.info("worker.startup", env=settings.app_env)


async def shutdown(ctx):
    logger.info("worker.shutdown")


class WorkerSettings:
    functions = [generation_pipeline, publish_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 900  # 15 minutes — generous ceiling for a full render
