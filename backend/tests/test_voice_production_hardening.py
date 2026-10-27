"""Recorded-voice production/export regression tests. No provider calls required."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.ai.director.director import PlanValidationError
from app.api.v1 import assets
from app.db.models.asset import AssetType
from app.db.models.video import VideoStatus
from app.workers.tasks.pipeline_task import require_live_output_providers


def test_production_allows_recorded_and_licensed_voice_without_unused_tts():
    settings = SimpleNamespace(
        app_env="production", voice_provider="mock", image_provider="cloudflare",
    )
    for mode in ("recorded", "cloned"):
        require_live_output_providers(
            {"llm_provider": "gemini"}, settings, voice_mode=mode,
        )
    with pytest.raises(PlanValidationError, match="TTS provider"):
        require_live_output_providers(
            {"llm_provider": "gemini"}, settings, voice_mode="auto",
        )
    with pytest.raises(PlanValidationError, match="real planning"):
        require_live_output_providers(
            {"llm_provider": "mock"}, settings, voice_mode="recorded",
        )


def owned_video_and_asset(*, needs_rerender=False, voice_mode="recorded"):
    user_id, asset_id = uuid.uuid4(), uuid.uuid4()
    video = SimpleNamespace(
        id=uuid.uuid4(), status=VideoStatus.READY, needs_rerender=needs_rerender,
        voice_preferences={"mode": voice_mode}, output_asset_id=asset_id,
    )
    final_asset = SimpleNamespace(
        id=asset_id, owner_id=user_id, storage_key="videos/final.mp4",
        type=AssetType.FINAL_VIDEO, mime_type="video/mp4",
    )
    return user_id, video, final_asset


@pytest.mark.asyncio
async def test_recorded_voice_old_silent_export_is_rejected_until_rerender():
    owner, video, final_asset = owned_video_and_asset(needs_rerender=True)
    db = AsyncMock()
    db.get.return_value = final_asset
    video_result = MagicMock()
    video_result.scalar_one_or_none.return_value = video
    db.execute.return_value = video_result
    with pytest.raises(HTTPException) as err:
        await assets.get_asset(
            final_asset.id, download=True, user=SimpleNamespace(id=owner), db=db,
        )
    assert err.value.status_code == 409
    assert "Re-render" in err.value.detail


@pytest.mark.asyncio
async def test_recorded_voice_does_not_export_when_scene_has_placeholder():
    owner, video, final_asset = owned_video_and_asset()
    scene = SimpleNamespace(audio_asset_id=uuid.uuid4())
    placeholder = SimpleNamespace(
        id=scene.audio_asset_id, owner_id=owner,
        provider_metadata={"recording_pending": True, "provider": "recording_pending"},
    )
    db = AsyncMock()
    db.get.return_value = final_asset
    video_row = MagicMock()
    video_row.scalar_one_or_none.return_value = video
    scenes_row = MagicMock()
    scenes_row.scalars.return_value.all.return_value = [scene]
    audio_row = MagicMock()
    audio_row.scalars.return_value.all.return_value = [placeholder]
    db.execute.side_effect = [video_row, scenes_row, audio_row]
    with pytest.raises(HTTPException) as err:
        await assets.get_asset(
            final_asset.id, download=True, user=SimpleNamespace(id=owner), db=db,
        )
    assert err.value.status_code == 409
    assert "Complete" in err.value.detail


@pytest.mark.asyncio
async def test_fully_rerendered_personal_voice_is_downloadable():
    owner, video, final_asset = owned_video_and_asset()
    scene = SimpleNamespace(audio_asset_id=uuid.uuid4())
    voice = SimpleNamespace(
        id=scene.audio_asset_id, owner_id=owner,
        provider_metadata={"provider": "personal_recording"},
    )
    db = AsyncMock()
    db.get.return_value = final_asset
    video_row = MagicMock()
    video_row.scalar_one_or_none.return_value = video
    scenes_row = MagicMock()
    scenes_row.scalars.return_value.all.return_value = [scene]
    audio_row = MagicMock()
    audio_row.scalars.return_value.all.return_value = [voice]
    db.execute.side_effect = [video_row, scenes_row, audio_row]
    with patch.object(assets, "get_signed_url", return_value="https://storage.example/final"):
        result = await assets.get_asset(
            final_asset.id, download=True, user=SimpleNamespace(id=owner), db=db,
        )
    assert result.signed_url == "https://storage.example/final"
    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_automatic_voice_keeps_previous_mp4_access_when_edits_are_pending():
    owner, video, final_asset = owned_video_and_asset(
        needs_rerender=True, voice_mode="auto",
    )
    db = AsyncMock()
    db.get.return_value = final_asset
    video_row = MagicMock()
    video_row.scalar_one_or_none.return_value = video
    db.execute.return_value = video_row
    with patch.object(assets, "get_signed_url", return_value="https://storage.example/old"):
        result = await assets.get_asset(
            final_asset.id, download=True, user=SimpleNamespace(id=owner), db=db,
        )
    assert result.signed_url == "https://storage.example/old"
