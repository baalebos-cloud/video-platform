"""Editing a video timeline must only reorder the owner's saved scenes."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1 import storyboards
from app.db.models.video import VideoStatus


def scene_ids(count=3):
    return [uuid.uuid4() for _ in range(count)]


def fake_scenes(ids):
    return [SimpleNamespace(id=scene_id, sequence=i + 1, narration=f"Clip {i+1}",
                            visual_asset_id=uuid.uuid4(), audio_asset_id=uuid.uuid4())
            for i, scene_id in enumerate(ids)]


def test_reorder_is_a_permutation_that_preserves_original_assets():
    ids = scene_ids()
    scenes = fake_scenes(ids)
    first_visual, first_audio = scenes[0].visual_asset_id, scenes[0].audio_asset_id
    assert storyboards.apply_scene_order(scenes, [ids[2], ids[0], ids[1]])
    assert [s.sequence for s in scenes] == [2, 3, 1]
    assert scenes[0].visual_asset_id == first_visual
    assert scenes[0].audio_asset_id == first_audio
    assert scenes[0].narration == "Clip 1"


def test_noop_reorder_returns_false():
    ids = scene_ids()
    scenes = fake_scenes(ids)
    assert not storyboards.apply_scene_order(scenes, ids)
    assert [s.sequence for s in scenes] == [1, 2, 3]


@pytest.mark.parametrize("new_order", [
    lambda ids: [ids[0], ids[0], ids[1]],
    lambda ids: [ids[0], ids[1]],
    lambda ids: [ids[0], ids[1], uuid.uuid4()],
])
def test_foreign_missing_and_duplicate_scene_ids_rejected_atomically(new_order):
    ids = scene_ids()
    scenes = fake_scenes(ids)
    with pytest.raises(HTTPException) as error:
        storyboards.apply_scene_order(scenes, new_order(ids))
    assert error.value.status_code == 422
    assert [s.sequence for s in scenes] == [1, 2, 3]


@pytest.mark.asyncio
async def test_reorder_endpoint_requires_ready_video_and_marks_re_render():
    ids = scene_ids()
    scenes = fake_scenes(ids)
    video = SimpleNamespace(id=uuid.uuid4(), status=VideoStatus.READY, needs_rerender=False)
    user = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: scenes))
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock, return_value=video):
        answer = await storyboards.update_scene_order(
            video.id, storyboards.SceneOrderUpdate(scene_ids=[ids[1], ids[0], ids[2]]),
            user=user, db=db,
        )
    assert answer["changed"] is True
    assert answer["needs_rerender"] is True
    assert video.needs_rerender
    assert scenes[0].sequence == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reorder_rejects_video_that_is_rendering():
    ids = scene_ids()
    video = SimpleNamespace(id=uuid.uuid4(), status=VideoStatus.RENDERING, needs_rerender=False)
    db = AsyncMock()
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock, return_value=video):
        with pytest.raises(HTTPException) as error:
            await storyboards.update_scene_order(
                video.id, storyboards.SceneOrderUpdate(scene_ids=ids), user=SimpleNamespace(id=uuid.uuid4()), db=db,
            )
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()
