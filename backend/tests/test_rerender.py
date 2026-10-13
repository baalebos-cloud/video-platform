"""Phase 2B regression tests for saved-asset rendering, ownership and cost safety."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1 import videos
from app.db.models.asset import AssetType
from app.db.models.video import VideoStatus
from app.workers.tasks.rerender_task import make_asset_manifest


def manifest_example():
    user_id = uuid.uuid4()
    scene = SimpleNamespace(
        id=uuid.uuid4(), visual_asset_id=uuid.uuid4(),
        audio_asset_id=uuid.uuid4(), duration_seconds=6.0,
    )
    image = SimpleNamespace(
        id=scene.visual_asset_id, owner_id=user_id, type=AssetType.IMAGE, storage_key="images/a",
    )
    audio = SimpleNamespace(
        id=scene.audio_asset_id, owner_id=user_id, type=AssetType.AUDIO, storage_key="audio/b",
    )
    return user_id, scene, {image.id: image, audio.id: audio}


def test_manifest_reuses_saved_audio_image_and_duration():
    user, scene, assets = manifest_example()
    manifest = make_asset_manifest([scene], assets, user)
    assert manifest[str(scene.id)] == {
        "image_key": "images/a", "audio_key": "audio/b", "duration": 6.0,
    }


def test_manifest_rejects_cross_owner_audio():
    user, scene, assets = manifest_example()
    assets[scene.audio_asset_id].owner_id = uuid.uuid4()
    with pytest.raises(ValueError, match="valid saved"):
        make_asset_manifest([scene], assets, user)


def test_manifest_rejects_missing_audio():
    user, scene, assets = manifest_example()
    assets.pop(scene.audio_asset_id)
    with pytest.raises(ValueError, match="valid saved"):
        make_asset_manifest([scene], assets, user)


def test_manifest_rejects_wrong_type():
    user, scene, assets = manifest_example()
    assets[scene.audio_asset_id].type = AssetType.IMAGE
    with pytest.raises(ValueError, match="valid saved"):
        make_asset_manifest([scene], assets, user)


@pytest.mark.asyncio
async def test_rerender_never_queries_other_users_video():
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    with patch.object(videos, "require_video_owner", new_callable=AsyncMock) as owner:
        owner.side_effect = HTTPException(403, "Not yours")
        with pytest.raises(HTTPException) as exc:
            await videos.rerender_video(uuid.uuid4(), user=user, db=db)
    assert exc.value.status_code == 403
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_rerender_requires_changed_storyboard():
    user = SimpleNamespace(id=uuid.uuid4())
    video_id = uuid.uuid4()
    video = SimpleNamespace(
        id=video_id, status=VideoStatus.READY,
        needs_rerender=False, output_asset_id=uuid.uuid4(),
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = video
    db.execute.return_value = result
    with patch.object(videos, "require_video_owner", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "enforce_concurrent_job_limit", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await videos.rerender_video(video_id, user=user, db=db)
    assert exc.value.status_code == 409
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_rerender_rejects_missing_saved_narration():
    user = SimpleNamespace(id=uuid.uuid4())
    video_id = uuid.uuid4()
    video = SimpleNamespace(
        id=video_id, status=VideoStatus.READY,
        needs_rerender=True, output_asset_id=uuid.uuid4(),
    )
    scene = SimpleNamespace(visual_asset_id=uuid.uuid4(), audio_asset_id=None)
    db = AsyncMock()
    locked = MagicMock()
    locked.scalar_one.return_value = video
    scenes = MagicMock()
    scenes.scalars.return_value.all.return_value = [scene]
    db.execute.side_effect = [locked, scenes]
    with patch.object(videos, "require_video_owner", new_callable=AsyncMock), \
         patch.object(videos.quota_service, "enforce_concurrent_job_limit", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc:
            await videos.rerender_video(video_id, user=user, db=db)
    assert exc.value.status_code == 409
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_update_detects_render_started_while_waiting_for_row_lock():
    from app.api.v1 import storyboards
    video_id = uuid.uuid4()
    video = SimpleNamespace(id=video_id, status=VideoStatus.READY)
    db = AsyncMock()

    async def change_status_on_lock(instance, *, with_for_update):
        assert with_for_update is True
        instance.status = VideoStatus.RENDERING

    db.refresh.side_effect = change_status_on_lock
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock) as owner:
        owner.return_value = video
        with pytest.raises(HTTPException) as exc:
            await storyboards.update_scene_prompt(
                video_id, uuid.uuid4(),
                storyboards.ScenePromptUpdate(visual_prompt="A new scene image"),
                user=SimpleNamespace(id=uuid.uuid4()), db=db,
            )
    assert exc.value.status_code == 409
    db.get.assert_not_awaited()
    db.commit.assert_not_awaited()
