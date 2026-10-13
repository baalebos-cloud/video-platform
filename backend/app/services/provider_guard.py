"""Global per-day live-provider request circuit breaker (NOT a dollar limit)."""
from datetime import datetime, timedelta, timezone

from redis.exceptions import RedisError

from app.ai.providers.openai_http import MediaProviderError
from app.config.settings import get_settings
from app.security.rate_limit import get_redis

# Atomic INCR + first-use TTL, safe across independent API and worker processes.
_CLAIM_SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""


async def claim_media_call(kind: str) -> None:
    settings = get_settings()
    if not kind or kind not in {"voice", "image", "voice_preview"}:
        raise ValueError("Unknown paid media operation")
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = max(1, int((tomorrow - now).total_seconds()) + 60)
    key = f"provider:media:global:{now:%Y-%m-%d}"
    try:
        count = await get_redis().eval(_CLAIM_SCRIPT, 1, key, ttl)
    except (RedisError, OSError):
        raise MediaProviderError("Provider request limit unavailable; live generation stopped safely") from None
    if int(count) > settings.max_daily_live_media_calls:
        raise MediaProviderError("Daily live-media request limit reached; try again tomorrow")
