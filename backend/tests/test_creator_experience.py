"""New creator UI API helpers and caption editing validation."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import captions, creator
from app.db.models.video import VideoStatus
from app.services.caption_service import generate_captions
from app.services.render_service import CAPTION_STYLES


def scene(sequence, narration, caption=None, duration=4.0):
    return SimpleNamespace(
        id=uuid.uuid4(), video_id=uuid.uuid4(), sequence=sequence,
        narration=narration, caption_text=caption, duration_seconds=duration,
    )


def test_caption_rows_respect_scene_offsets_and_manual_overrides():
    first, second = scene(1, "Hello, world"), scene(2, "Second text", "New subtitle", 2.5)
    rows = captions.caption_rows([second, first])
    assert rows[0]["text"] == "Hello, world"
    assert rows[1]["text"] == "New subtitle"
    assert rows[1]["start_seconds"] == 4.0
    assert rows[1]["end_seconds"] == 6.5


def test_caption_payload_validation_and_safe_styles():
    with pytest.raises(ValidationError):
        captions.CaptionEdit(scene_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        captions.CaptionEdit(style="subtitles=malicious")
    assert set(CAPTION_STYLES) == {"classic", "bold", "social", "minimal"}


@pytest.mark.asyncio
async def test_caption_write_requires_video_ownership():
    db = AsyncMock()
    with patch.object(captions, "require_video_owner", new_callable=AsyncMock) as owner:
        owner.side_effect = HTTPException(403, "Forbidden")
        with pytest.raises(HTTPException) as error:
            await captions.edit_captions(
                uuid.uuid4(), captions.CaptionEdit(style="bold"),
                user=SimpleNamespace(id=uuid.uuid4()), db=db,
            )
    assert error.value.status_code == 403
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_caption_write_rejects_in_progress_video():
    video = SimpleNamespace(id=uuid.uuid4(), status=VideoStatus.RENDERING)
    db = AsyncMock()
    with patch.object(captions, "require_video_owner", new_callable=AsyncMock, return_value=video):
        with pytest.raises(HTTPException) as error:
            await captions.edit_captions(
                video.id, captions.CaptionEdit(style="social"),
                user=SimpleNamespace(id=uuid.uuid4()), db=db,
            )
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


def test_creator_totals_deduplicate_snapshots():
    post_id = uuid.uuid4()
    new = SimpleNamespace(
        published_video_id=post_id, views=80, likes=5, shares=2,
        comments=1, created_at=datetime.now(timezone.utc),
    )
    old = SimpleNamespace(
        published_video_id=post_id, views=50, likes=2, shares=0,
        comments=0, created_at=datetime.now(timezone.utc),
    )
    latest = creator.latest_snapshot_by_post([new, old])
    posts = [SimpleNamespace(id=post_id, platform="youtube")]
    totals = creator.aggregate_platforms(posts, latest)
    assert totals[0]["views"] == 80
    assert totals[0]["likes"] == 5
