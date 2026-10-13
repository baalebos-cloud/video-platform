"""Regression tests for cross-tenant protection and safe generation defaults."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api.deps import get_current_user
from app.api.v1 import analytics, publishing, storyboards, videos
from app.config.settings import Settings
from app.db.models.user import UserStatus
from app.services.publishing_service import get_publishing_provider


@pytest.mark.asyncio
async def test_analytics_requires_video_ownership():
    db = AsyncMock()
    user = SimpleNamespace(id=uuid.uuid4())
    with patch.object(analytics, "require_video_owner", new_callable=AsyncMock) as owner:
        owner.side_effect = HTTPException(403, "Forbidden")
        with pytest.raises(HTTPException) as exc:
            await analytics.get_analytics(uuid.uuid4(), user=user, db=db)
    assert exc.value.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_scene_regeneration_rejects_scene_from_another_video():
    video_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=uuid.uuid4(), video_id=uuid.uuid4())
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock) as owner:
        owner.return_value = SimpleNamespace(id=video_id)
        with pytest.raises(HTTPException) as exc:
            await storyboards.regenerate_scene(video_id, uuid.uuid4(), user=user, db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_publish_rejects_account_owned_by_another_user():
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(user_id=uuid.uuid4(), platform="mock")
    payload = publishing.PublishRequest(
        video_id=uuid.uuid4(), publishing_account_id=uuid.uuid4(), title="Test"
    )
    with patch.object(publishing, "require_video_owner", new_callable=AsyncMock) as owner:
        owner.return_value = SimpleNamespace(id=payload.video_id, output_asset_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await publishing.publish_video("mock", payload, user=user, db=db)
    assert exc.value.status_code == 404


def test_unconfigured_publishing_provider_must_not_succeed_as_mock():
    with pytest.raises(ValueError, match="not configured"):
        get_publishing_provider("youtube")


@pytest.mark.asyncio
async def test_suspended_account_cannot_use_access_token():
    user = SimpleNamespace(id=uuid.uuid4(), status=UserStatus.SUSPENDED)
    db = AsyncMock()
    db.execute.return_value.scalar_one_or_none.return_value = user
    request = Request({"type": "http", "headers": []})
    auth = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    with patch("app.api.deps.decode_token", return_value={"type": "access", "sub": str(user.id)}):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, credentials=auth, db=db)
    assert exc.value.status_code == 401


def test_production_rejects_placeholder_jwt():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, app_env="production", jwt_secret="replace_me_in_env", debug=False)


@pytest.mark.asyncio
async def test_retry_keys_are_isolated_per_user():
    payload = videos.GenerateVideoRequest(project_id=uuid.uuid4(), topic="An educational short video")
    keys = []
    async def track_existing(db, key):
        keys.append(key)
        return None
    async def start(*args, **kwargs):
        return SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())
    with patch.object(videos, "require_project_owner", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "enforce_max_duration", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "enforce_concurrent_job_limit", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "find_existing_job_by_idempotency_key", side_effect=track_existing), \
         patch.object(videos.video_service, "start_generation", side_effect=start):
        for _ in range(2):
            await videos.generate_video(
                payload, idempotency_key="my-retry-key",
                user=SimpleNamespace(id=uuid.uuid4()), db=AsyncMock()
            )
    assert len(keys) == 2 and keys[0] != keys[1]


@pytest.mark.asyncio
async def test_existing_retry_key_rejects_different_payload():
    payload = videos.GenerateVideoRequest(project_id=uuid.uuid4(), topic="A new topic")
    existing = SimpleNamespace(input_hash="different-payload-hash")
    with patch.object(videos, "require_project_owner", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "enforce_max_duration", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "enforce_concurrent_job_limit", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "find_existing_job_by_idempotency_key", new_callable=AsyncMock, return_value=existing), \
         patch.object(videos.video_service, "start_generation", new_callable=AsyncMock) as create:
        with pytest.raises(HTTPException) as exc:
            await videos.generate_video(
                payload, idempotency_key="same-key",
                user=SimpleNamespace(id=uuid.uuid4()), db=AsyncMock()
            )
    assert exc.value.status_code == 409
    create.assert_not_awaited()
