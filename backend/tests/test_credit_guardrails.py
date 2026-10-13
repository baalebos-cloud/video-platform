"""Credit accounting and paid-provider safety regression suite.

All tests are local mocks. They do not contact providers or move real money.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config.settings import Settings
from app.db.models.billing import CreditLedgerEntry, LedgerEntryType
from app.services import credit_service, provider_guard, video_service
from app.ai.providers.openai_http import MediaProviderError


def config(**overrides):
    settings = dict(
        _env_file=None, app_env="test", credit_enforcement_enabled=True,
        credits_per_30_seconds=10, voice_provider="mock", image_provider="mock",
    )
    settings.update(overrides)
    return Settings(**settings)


@pytest.mark.parametrize("duration,expected", [(1, 10), (30, 10), (31, 20), (60, 20), (61, 30)])
def test_credit_quote_rounds_up_by_30_seconds(duration, expected):
    with patch.object(credit_service, "get_settings", return_value=config()):
        assert credit_service.generation_price(duration) == Decimal(expected)


@pytest.mark.asyncio
async def test_debit_rejects_negative_balance():
    user_id = uuid.uuid4()
    db = AsyncMock()
    with patch.object(credit_service, "get_settings", return_value=config()), \
         patch.object(credit_service, "_lock_user", new_callable=AsyncMock), \
         patch.object(credit_service, "balance", new_callable=AsyncMock, return_value=Decimal(1)):
        db.scalar.return_value = None
        with pytest.raises(HTTPException) as error:
            await credit_service.debit(
                db, user_id, 10, reference_type="video_generation", reference_id="job-1"
            )
    assert error.value.status_code == 402
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_debit_persists_negative_crd_with_reference():
    user_id = uuid.uuid4()
    db = AsyncMock()
    db.scalar.return_value = None
    with patch.object(credit_service, "get_settings", return_value=config()), \
         patch.object(credit_service, "_lock_user", new_callable=AsyncMock), \
         patch.object(credit_service, "balance", new_callable=AsyncMock, return_value=Decimal(100)):
        await credit_service.debit(
            db, user_id, Decimal(20), reference_type="video_generation",
            reference_id="job-123", metadata={"video_id": "video-123"},
        )
    entry = db.add.call_args.args[0]
    assert entry.entry_type == LedgerEntryType.DEBIT
    assert entry.currency == "CRD"
    assert entry.amount == -20
    assert entry.reference_id == "job-123"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_refund_is_idempotent_and_matches_debit():
    user_id = uuid.uuid4()
    db = AsyncMock()
    debit_entry = SimpleNamespace(amount=Decimal("-30.00"))
    existing_refund_id = None
    db.scalar.side_effect = [debit_entry, existing_refund_id]
    with patch.object(credit_service, "_lock_user", new_callable=AsyncMock):
        assert await credit_service.refund(
            db, user_id, reference_type="video_generation", reference_id="job-3"
        ) is True
    refund = db.add.call_args.args[0]
    assert refund.amount == Decimal("30.00")
    assert refund.entry_type == LedgerEntryType.REFUND
    db.flush.assert_awaited_once()

    db.add.reset_mock()
    db.scalar.side_effect = [debit_entry, uuid.uuid4()]
    with patch.object(credit_service, "_lock_user", new_callable=AsyncMock):
        assert await credit_service.refund(
            db, user_id, reference_type="video_generation", reference_id="job-3"
        ) is False
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_refund_without_original_debit_writes_nothing():
    db = AsyncMock()
    db.scalar.return_value = None
    with patch.object(credit_service, "_lock_user", new_callable=AsyncMock):
        assert not await credit_service.refund(
            db, uuid.uuid4(), reference_type="video_generation", reference_id="not-exists",
        )
    db.add.assert_not_called()


def test_production_real_media_requires_credits_enforcement():
    with pytest.raises(ValidationError, match="CREDIT_ENFORCEMENT_ENABLED"):
        config(
            app_env="production", voice_provider="openai", openai_api_key="test-key",
            credit_enforcement_enabled=False, jwt_secret="some-long-production-secret-at-least-32-bytes",
        )


@pytest.mark.asyncio
async def test_provider_guard_blocks_calls_after_daily_limit():
    redis = SimpleNamespace(eval=AsyncMock(side_effect=[1, 3]))
    settings = config(max_daily_live_media_calls=2)
    with patch.object(provider_guard, "get_redis", return_value=redis), \
         patch.object(provider_guard, "get_settings", return_value=settings):
        await provider_guard.claim_media_call("voice")
        with pytest.raises(MediaProviderError, match="Daily live-media request limit"):
            await provider_guard.claim_media_call("image")
    assert redis.eval.await_count == 2


@pytest.mark.asyncio
async def test_provider_guard_fails_closed_when_redis_down():
    redis = SimpleNamespace(eval=AsyncMock(side_effect=RedisConnectionError("not connected")))
    with patch.object(provider_guard, "get_redis", return_value=redis):
        with pytest.raises(MediaProviderError, match="unavailable"):
            await provider_guard.claim_media_call("voice_preview")


@pytest.mark.asyncio
async def test_queue_failure_refunds_reserved_credits():
    project_id, owner_id = uuid.uuid4(), uuid.uuid4()
    db = AsyncMock()
    async def assign_ids(*_args):
        # SQLAlchemy UUID IDs are assigned on construction in real sessions;
        # emulate the flush-generated IDs here.
        pass

    settings = config()
    with patch.object(video_service, "get_settings", return_value=settings), \
         patch.object(video_service.credit_service, "get_settings", return_value=settings), \
         patch.object(video_service.credit_service, "debit", new_callable=AsyncMock) as debit, \
         patch.object(video_service.credit_service, "refund", new_callable=AsyncMock) as refund, \
         patch.object(video_service, "enqueue", new_callable=AsyncMock, side_effect=RuntimeError("redis disconnected")):
        with patch.object(video_service, "Project") as project_class:
            # Real DB model may be constructed; the DB get is enough.
            db.get.return_value = SimpleNamespace(user_id=owner_id)
            with pytest.raises(HTTPException) as exc:
                await video_service.start_generation(
                    db, project_id=project_id, topic="Test video",
                    language="English", locale="en-US", duration_seconds=30,
                    platform="youtube_shorts", visual_style="cinematic_realistic",
                    creativity="high", voice_preferences={}, idempotency_key=None,
                    input_hash="sha",
                )
    assert exc.value.status_code == 503
    debit.assert_awaited_once()
    refund.assert_awaited_once()
    db.commit.assert_awaited()
