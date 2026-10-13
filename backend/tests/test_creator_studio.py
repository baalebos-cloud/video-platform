"""Creator studio regression checks: authorization, scoped listing, media and export format."""
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1 import projects, storyboards
from app.db.models.video import VideoStatus
from app.services import render_service, storage_service


@pytest.mark.asyncio
async def test_project_videos_rejects_other_user_before_query():
    db = AsyncMock()
    user = SimpleNamespace(id=uuid.uuid4())
    with patch.object(projects, "require_project_owner", new_callable=AsyncMock) as owner:
        owner.side_effect = HTTPException(403, "Not yours")
        with pytest.raises(HTTPException) as exc:
            await projects.list_project_videos(
                uuid.uuid4(), status_filter=None, limit=12, offset=0, user=user, db=db
            )
    assert exc.value.status_code == 403
    db.execute.assert_not_awaited()
    db.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_videos_returns_paginated_owned_results():
    db = AsyncMock()
    db.scalar.return_value = 0
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    user = SimpleNamespace(id=uuid.uuid4())
    project_id = uuid.uuid4()
    with patch.object(projects, "require_project_owner", new_callable=AsyncMock) as owner:
        page = await projects.list_project_videos(
            project_id, status_filter=VideoStatus.READY, limit=12, offset=0, user=user, db=db
        )
    owner.assert_awaited_once_with(db, project_id, user.id)
    assert page.items == [] and page.total == 0
    assert db.scalar.await_count == 1 and db.execute.await_count == 1
    assert project_id.hex in str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_prompt_edit_rejects_scene_from_different_video():
    video_id = uuid.uuid4()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=uuid.uuid4(), video_id=uuid.uuid4())
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock) as owned:
        owned.return_value = SimpleNamespace(id=video_id, status=VideoStatus.READY)
        with pytest.raises(HTTPException) as exc:
            await storyboards.update_scene_prompt(
                video_id, uuid.uuid4(),
                storyboards.ScenePromptUpdate(visual_prompt="A daytime aerial landscape"),
                user=SimpleNamespace(id=uuid.uuid4()), db=db,
            )
    assert exc.value.status_code == 404
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_edit_blocks_generation_in_progress():
    video_id = uuid.uuid4()
    db = AsyncMock()
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock) as owned:
        owned.return_value = SimpleNamespace(id=video_id, status=VideoStatus.RENDERING)
        with pytest.raises(HTTPException) as exc:
            await storyboards.update_scene_prompt(
                video_id, uuid.uuid4(),
                storyboards.ScenePromptUpdate(visual_prompt="Nighttime skyline"),
                user=SimpleNamespace(id=uuid.uuid4()), db=db,
            )
    assert exc.value.status_code == 409
    db.get.assert_not_awaited()


def test_signed_media_uses_public_endpoint_client():
    with patch.object(storage_service, "_client") as client:
        client.return_value.generate_presigned_url.return_value = "https://media.example/test"
        assert storage_service.get_signed_url("private/video.mp4") == "https://media.example/test"
    client.assert_called_once_with(public=True)


def test_landscape_render_scales_to_widescreen():
    with patch.object(render_service, "_run") as run:
        render_service.render_scene_clip(
            Path("image.png"), Path("audio.wav"), 4.0, Path("out.mp4"), aspect_ratio="16:9"
        )
    cmd = run.call_args.args[0]
    assert "1920:1080" in cmd[cmd.index("-vf") + 1]


def test_invalid_render_ratio_is_rejected():
    with pytest.raises(render_service.RenderError):
        render_service.render_scene_clip(
            Path("image.png"), Path("audio.wav"), 4.0, Path("out.mp4"), aspect_ratio="invalid"
        )
