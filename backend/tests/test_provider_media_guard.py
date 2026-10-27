"""Offline regression for quota guard blocking media calls before Cloudflare.

Redis MULTI/EXEC replaces Lua EVAL, provides a fixed UTC-day TTL,
and preserves safe failure-closed behavior with actionable codes.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from redis.exceptions import ResponseError

from app.services import provider_guard
from app.services.provider_guard import MediaGuardError
from app.workers.tasks.pipeline_task import provider_failure_details


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def incr(self, key):
        self.commands.append(("incr", key))
        return self

    def expire(self, key, ttl):
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        if self.client.should_raise:
            raise ResponseError("EVAL and Lua are denied")
        self.client.calls.append(self.commands)
        self.client.count += 1
        return [self.client.count, True]


class FakeRedis:
    def __init__(self, *, initial=0, should_raise=False):
        self.count = initial
        self.should_raise = should_raise
        self.calls = []

    def pipeline(self, *, transaction):
        assert transaction is True
        return FakePipeline(self)

    def eval(self, *_):
        raise AssertionError("Lua EVAL must never be called")


@pytest.mark.asyncio
async def test_atomic_quota_claim_works_when_redis_disallows_lua():
    redis = FakeRedis()
    with patch.object(provider_guard, "get_redis", return_value=redis), \
         patch.object(provider_guard, "get_settings", return_value=SimpleNamespace(max_daily_live_media_calls=4)):
        await provider_guard.claim_media_call("voice")
        await provider_guard.claim_media_call("image")
    assert redis.count == 2
    assert len(redis.calls) == 2
    for call in redis.calls:
        assert call[0][0] == "incr"
        assert call[1][0] == "expire"
        assert call[1][2] > 0
        assert call[0][1] == call[1][1]
        assert call[0][1].startswith("provider:media:global:")


@pytest.mark.asyncio
async def test_quota_limit_remains_fail_closed_and_actionable():
    redis = FakeRedis(initial=2)
    with patch.object(provider_guard, "get_redis", return_value=redis), \
         patch.object(provider_guard, "get_settings", return_value=SimpleNamespace(max_daily_live_media_calls=2)):
        with pytest.raises(MediaGuardError) as e:
            await provider_guard.claim_media_call("voice")
    assert e.value.reason == "daily_quota_exceeded"
    code, message, status = provider_failure_details("generating_assets", e.value)
    assert code == "media_daily_limit"
    assert "Daily media-call" in message
    assert status is None


@pytest.mark.asyncio
async def test_unavailable_redis_does_not_call_provider():
    redis = FakeRedis(should_raise=True)
    with patch.object(provider_guard, "get_redis", return_value=redis), \
         patch.object(provider_guard, "get_settings", return_value=SimpleNamespace(max_daily_live_media_calls=8)):
        with pytest.raises(MediaGuardError) as e:
            await provider_guard.claim_media_call("voice")
    assert e.value.reason == "redis_unavailable"
    code, message, status = provider_failure_details("generating_assets", e.value)
    assert code == "media_guard_redis_unavailable"
    assert "Redis" in message
    assert "EVAL" not in message
    assert status is None


@pytest.mark.asyncio
async def test_invalid_quota_counter_response_fails_closed():
    redis = FakeRedis()
    redis.count = -2
    with patch.object(provider_guard, "get_redis", return_value=redis), \
         patch.object(provider_guard, "get_settings", return_value=SimpleNamespace(max_daily_live_media_calls=9)):
        with pytest.raises(MediaGuardError, match="redis_unavailable"):
            await provider_guard.claim_media_call("voice")


@pytest.mark.asyncio
async def test_unknown_media_operation_is_rejected():
    with pytest.raises(ValueError, match="Unknown media"):
        await provider_guard.claim_media_call("video")
