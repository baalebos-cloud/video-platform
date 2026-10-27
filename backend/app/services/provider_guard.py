"""Global UTC-day provider usage guard (request limit, not a dollar budget).

Use Redis MULTI/EXEC rather than EVAL so shared Railway Redis instances and
ACLs that disable Lua scripting can still enforce the atomic request counter.
Never proceed to Cloudflare when Redis quota enforcement is unavailable.
"""
from datetime import datetime, timedelta, timezone

from redis.exceptions import RedisError

from app.ai.providers.openai_http import MediaProviderError
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.security.rate_limit import get_redis

logger = get_logger("services.provider_guard")


class MediaGuardError(MediaProviderError):
    """Non-secret reason code for a blocked media call."""

    def __init__(self, reason: str):
        if reason not in {"redis_unavailable", "daily_quota_exceeded"}:
            raise ValueError("Unknown media-guard failure reason")
        self.reason = reason
        super().__init__(reason)


async def claim_media_call(kind: str) -> None:
    settings = get_settings()
    if kind not in {"voice", "image", "voice_preview"}:
        raise ValueError("Unknown media operation")

    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = max(1, int((tomorrow - now).total_seconds()) + 60)
    key = f"provider:media:global:{now:%Y-%m-%d}"

    try:
        # Both commands execute atomically. Updating expiry on each claim
        # holds the same daily UTC boundary, including under concurrency.
        async with get_redis().pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, ttl)
            result = await pipe.execute()
        count = int(result[0])
        if count < 1 or result[1] is not True:
            raise ValueError("Invalid atomic quota counter response")
    except (RedisError, OSError, TypeError, ValueError) as exc:
        logger.error(
            "provider_guard.redis_unavailable",
            media_kind=kind,
            redis_error_type=type(exc).__name__,
        )
        raise MediaGuardError("redis_unavailable") from None

    if count > settings.max_daily_live_media_calls:
        logger.warning(
            "provider_guard.daily_quota_exceeded",
            media_kind=kind,
            requests=count,
            configured_daily_limit=settings.max_daily_live_media_calls,
        )
        raise MediaGuardError("daily_quota_exceeded")
