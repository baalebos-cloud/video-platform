"""
Simple Redis-backed sliding-window rate limiter for expensive endpoints
(generation, rendering, publishing).

This is intentionally dependency-light: a fixed-window counter keyed by
user + route is sufficient for an MVP and is easy to reason about in
an incident. Swap for a token-bucket implementation if burst traffic
patterns demand it.
"""
import time

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from app.config.settings import get_settings

settings = get_settings()
_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


class RateLimiter:
    """Usage: Depends(RateLimiter(limit=5, window_seconds=60, scope="generate"))"""

    def __init__(self, limit: int, window_seconds: int, scope: str):
        self.limit = limit
        self.window_seconds = window_seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        user = getattr(request.state, "user", None)
        identity = str(user.id) if user else request.client.host if request.client else "anonymous"
        redis = get_redis()
        window = int(time.time() // self.window_seconds)
        key = f"ratelimit:{self.scope}:{identity}:{window}"
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, self.window_seconds)
        if current > self.limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit exceeded for '{self.scope}'. Try again shortly.",
            )
