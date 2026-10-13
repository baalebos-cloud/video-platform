"""Batch caption safety and SRT formatting."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.api.v1 import captions
from app.db.models.video import VideoStatus

def scene(order, seconds, text):
    return SimpleNamespace(id=uuid.uuid4(), sequence=order, duration_seconds=seconds,
        caption_text=text, narration="Original narration")

def test_srt_text_and_time_are_deterministic():
    s = scene(2, 1.5, "Hello\n  world")
    output = captions.captions_as_srt([s])
    assert "00:00:00,000 --> 00:00:01,500" in output
    assert "Hello world" in output

def test_blank_captions_not_exported():
    s = scene(1, 3.0, " ")
    assert captions.captions_as_srt([s]) == ""

def test_batch_limits_and_duplicate_scenes():
    with pytest.raises(ValidationError):
        captions.BulkCaptionEdit(edits=[])

@pytest.mark.asyncio
async def test_batch_rejects_duplicate_scene_ids():
    user = SimpleNamespace(id=uuid.uuid4())
    s = scene(1, 2.0, "old")
    video = SimpleNamespace(id=uuid.uuid4(), status=VideoStatus.READY)
    db = AsyncMock()
    with patch.object(captions, "require_video_owner", new_callable=AsyncMock, return_value=video):
        with pytest.raises(HTTPException) as exc:
            await captions.batch_edit_captions(video.id, captions.BulkCaptionEdit(
                edits=[captions.BulkCaptionItem(scene_id=s.id, text="one"),
                       captions.BulkCaptionItem(scene_id=s.id, text="two")],
            ), user=user, db=db)
    assert exc.value.status_code == 422
    db.commit.assert_not_awaited()

@pytest.mark.asyncio
async def test_batch_rejects_foreign_scene_without_writing():
    video = SimpleNamespace(id=uuid.uuid4(), status=VideoStatus.READY)
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    with patch.object(captions, "require_video_owner", new_callable=AsyncMock, return_value=video):
        with pytest.raises(HTTPException) as exc:
            await captions.batch_edit_captions(video.id, captions.BulkCaptionEdit(
                edits=[captions.BulkCaptionItem(scene_id=uuid.uuid4(), text="changed")],
            ), user=SimpleNamespace(id=uuid.uuid4()), db=db)
    assert exc.value.status_code == 404
    db.commit.assert_not_awaited()

@pytest.mark.asyncio
async def test_batch_marks_video_for_rerender():
    video = SimpleNamespace(id=uuid.uuid4(), status=VideoStatus.READY, needs_rerender=False)
    s = scene(1, 2.0, "old")
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [s]
    db.execute.return_value = result
    with patch.object(captions, "require_video_owner", new_callable=AsyncMock, return_value=video):
        outcome = await captions.batch_edit_captions(video.id, captions.BulkCaptionEdit(
            edits=[captions.BulkCaptionItem(scene_id=s.id, text="new caption")],
        ), user=SimpleNamespace(id=uuid.uuid4()), db=db)
    assert outcome["updated"] == 1
    assert s.caption_text == "new caption"
    assert video.needs_rerender is True
    db.commit.assert_awaited_once()
