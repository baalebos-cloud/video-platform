"""
Thin wrapper around arq (Redis-backed async job queue) so API code never
imports arq directly — keeps the queueing mechanism swappable.
"""
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from app.config.settings import get_settings

settings = get_settings()
_redis_settings = RedisSettings.from_dsn(settings.redis_url)
_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings)
    return _pool


async def enqueue(function_name: str, payload: dict[str, Any]) -> str:
    pool = await get_pool()
    job = await pool.enqueue_job(function_name, payload)
    return job.job_id if job else ""
