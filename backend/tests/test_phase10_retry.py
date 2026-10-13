"""Failed video retry is strictly owner scoped, idempotent, and cost-aware."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from app.api.v1 import videos
from app.db.models.video import VideoStatus

def failed_source():
    return SimpleNamespace(
        id=uuid.uuid4(), status=VideoStatus.FAILED,
        project_id=uuid.uuid4(), topic="How batteries work", language="English",
        locale="en-US", duration_seconds=60, platform="youtube_shorts",
        visual_style="cinematic", creativity="high", voice_preferences={},
    )

@pytest.mark.asyncio
async def test_retry_rejects_healthy_video():
    src = failed_source()
    src.status = VideoStatus.READY
    db = AsyncMock()
    db.scalar.return_value = src
    with patch.object(videos, "require_video_owner", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await videos.retry_failed_video(src.id, user=SimpleNamespace(id=uuid.uuid4()), db=db)
    assert exc.value.status_code == 409

@pytest.mark.asyncio
async def test_retry_returns_existing_idempotent_attempt():
    src = failed_source()
    result = SimpleNamespace(video_id=uuid.uuid4(), id=uuid.uuid4(),
                             status=SimpleNamespace(value="queued"))
    db = AsyncMock()
    db.scalar.return_value = src
    with patch.object(videos, "require_video_owner", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "find_existing_job_by_idempotency_key",
                      new_callable=AsyncMock, return_value=result), \
         patch.object(videos.video_service, "start_generation", new_callable=AsyncMock) as create:
        response = await videos.retry_failed_video(src.id, user=SimpleNamespace(id=uuid.uuid4()), db=db)
    assert response.video_id == result.video_id
    create.assert_not_awaited()

@pytest.mark.asyncio
async def test_retry_creates_new_video_and_preserves_original():
    src = failed_source()
    db = AsyncMock()
    db.scalar.return_value = src
    new = SimpleNamespace(id=uuid.uuid4())
    job = SimpleNamespace(id=uuid.uuid4())
    with patch.object(videos, "require_video_owner", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "find_existing_job_by_idempotency_key",
                      new_callable=AsyncMock, return_value=None), \
         patch.object(videos.quota_service, "enforce_concurrent_job_limit", new_callable=AsyncMock), \
         patch.object(videos.video_service, "start_generation", new_callable=AsyncMock, return_value=(new,job)) as create:
        response = await videos.retry_failed_video(src.id, user=SimpleNamespace(id=uuid.uuid4()), db=db)
    assert response.video_id == new.id
    assert src.status == VideoStatus.FAILED
    assert create.await_args.kwargs["topic"] == src.topic
    assert create.await_args.kwargs["idempotency_key"]
