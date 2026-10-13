"""Recovery token digest and per-address Redis throttling."""
import hashlib
import hmac
import time

from app.config.settings import get_settings
from app.security.rate_limit import get_redis


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def limit_password_reset_email(email: str) -> bool:
    # Obscure the normalized address in Redis keyspace; never store addresses
    # or raw tokens in rate-limit keys.
    salt = get_settings().jwt_secret.encode("utf-8")
    address_key = hmac.new(salt, email.encode("utf-8"), hashlib.sha256).hexdigest()
    redis = get_redis()
    bucket = int(time.time() // 3600)
    key = f"ratelimit:password_reset_address:{address_key}:{bucket}"
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, 3600)
    return current <= 3
