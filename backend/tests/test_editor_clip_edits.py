"""Non-destructive timeline trims and fade-through-black render integration."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import storyboards
from app.db.models.video import VideoStatus
from app.services import render_service
from app.workers.tasks import render_task


def scene(*, seq: int = 1, duration: float = 5.0, transition: str = "cut"):
    return SimpleNamespace(
        id=uuid.uuid4(), video_id=uuid.uuid4(), sequence=seq,
        duration_seconds=duration, metadata_json={"editor_transition_in": transition},
        visual_asset_id=uuid.uuid4(), audio_asset_id=uuid.uuid4(),
        narration="Saved generated narration", caption_text=None,
    )


def test_trim_preserves_source_media_and_can_be_restored():
    clip = scene()
    image, audio = clip.visual_asset_id, clip.audio_asset_id
    assert storyboards.apply_scene_edit(clip, storyboards.SceneEditUpdate(duration_seconds=2.5))
    assert clip.duration_seconds == 2.5
    assert storyboards.original_scene_duration(clip) == 5.0
    assert clip.visual_asset_id == image and clip.audio_asset_id == audio
    assert not storyboards.apply_scene_edit(clip, storyboards.SceneEditUpdate(duration_seconds=2.5))
    assert storyboards.apply_scene_edit(clip, storyboards.SceneEditUpdate(duration_seconds=5.0))
    assert clip.duration_seconds == 5
    assert storyboards.original_scene_duration(clip) == 5


def test_trim_rejects_lengthening_beyond_source_and_never_mutates():
    clip = scene(duration=3.3)
    with pytest.raises(HTTPException) as error:
        storyboards.apply_scene_edit(clip, storyboards.SceneEditUpdate(duration_seconds=4))
    assert error.value.status_code == 422
    assert clip.duration_seconds == 3.3
    assert "editor_original_duration_seconds" not in clip.metadata_json


@pytest.mark.parametrize("value", [0, -1, 61])
def test_trim_rejects_out_of_bounds(value):
    with pytest.raises(ValidationError):
        storyboards.SceneEditUpdate(duration_seconds=value)


def test_transition_is_optional_and_persisted_without_modifying_duration():
    clip = scene(duration=4)
    assert storyboards.apply_scene_edit(clip, storyboards.SceneEditUpdate(transition_in="fade_black"))
    assert storyboards.scene_transition(clip) == "fade_black"
    assert clip.duration_seconds == 4
    assert not storyboards.apply_scene_edit(clip, storyboards.SceneEditUpdate(transition_in="fade_black"))
    assert storyboards.apply_scene_edit(clip, storyboards.SceneEditUpdate(transition_in="cut"))
    assert storyboards.scene_transition(clip) == "cut"


def test_invalid_original_duration_metadata_is_ignored():
    clip = scene()
    clip.metadata_json["editor_original_duration_seconds"] = "infinity"
    assert storyboards.original_scene_duration(clip) == 5


@pytest.mark.asyncio
async def test_editor_endpoint_is_owner_checked_and_marks_rerender():
    clip = scene()
    user = SimpleNamespace(id=uuid.uuid4())
    video = SimpleNamespace(id=clip.video_id, status=VideoStatus.READY, needs_rerender=False)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: clip)
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock, return_value=video):
        answer = await storyboards.edit_scene_timeline(
            video.id, clip.id, storyboards.SceneEditUpdate(
                duration_seconds=2.0, transition_in="fade_black",
            ), user=user, db=db,
        )
    assert answer["needs_rerender"] is True and answer["changed"] is True
    assert answer["duration_seconds"] == 2.0
    assert answer["max_duration_seconds"] == 5.0
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_editor_endpoint_denies_rendering_state():
    clip = scene()
    user = SimpleNamespace(id=uuid.uuid4())
    video = SimpleNamespace(id=clip.video_id, status=VideoStatus.RENDERING)
    db = AsyncMock()
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock, return_value=video):
        with pytest.raises(HTTPException) as error:
            await storyboards.edit_scene_timeline(
                video.id, clip.id, storyboards.SceneEditUpdate(duration_seconds=2.0),
                user=user, db=db,
            )
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


def test_fade_filters_are_symmetric_and_default_to_clean_cut():
    assert render_service.scene_fade_filters("scale=10:10", 3, fade_in=False, fade_out=False) == (
        "scale=10:10", "apad",
    )
    video, audio = render_service.scene_fade_filters("scale=10:10", 3, fade_in=True, fade_out=True)
    assert "fade=t=in:st=0:d=0.250" in video
    assert "fade=t=out:st=2.750:d=0.250" in video
    assert "afade=t=in:st=0:d=0.250" in audio
    assert "afade=t=out:st=2.750:d=0.250" in audio


def test_ffmpeg_applies_fades_to_both_still_and_stock_clips(tmp_path):
    image, audio, footage, output = (
        tmp_path / "a.png", tmp_path / "a.wav", tmp_path / "a.mp4", tmp_path / "out.mp4"
    )
    commands = []
    with patch.object(render_service, "_run", side_effect=lambda cmd: commands.append(cmd)):
        render_service.render_scene_clip(
            image, audio, 2.5, output, aspect_ratio="9:16",
            fade_in=True, fade_out=True,
        )
        render_service.render_stock_clip(
            footage, audio, 2.5, output, aspect_ratio="9:16",
            fade_in=True, fade_out=True,
        )
    assert len(commands) == 2
    for cmd in commands:
        assert "fade=t=in" in cmd[cmd.index("-vf") + 1]
        assert "fade=t=out" in cmd[cmd.index("-vf") + 1]
        assert "afade=t=in" in cmd[cmd.index("-af") + 1]
        assert "afade=t=out" in cmd[cmd.index("-af") + 1]
        assert cmd[cmd.index("-t") + 1] == "2.5"


def test_re_render_uses_trimmed_duration_and_adjacent_fade_metadata(tmp_path):
    clips = [scene(seq=i, duration=2.5) for i in range(1, 4)]
    clips[1].metadata_json["editor_transition_in"] = "fade_black"
    clips[2].metadata_json["stock_footage_key"] = "licensed-stock-key"
    video = SimpleNamespace(id=uuid.uuid4(), aspect_ratio="9:16", visual_style="classic",
                            caption_style="none")
    manifest = {
        str(clip.id): {"image_key": f"image_{i}", "audio_key": f"audio_{i}", "duration": clip.duration_seconds,
                       **({"video_key": "licensed-stock-key"} if i == 3 else {})}
        for i, clip in enumerate(clips, 1)
    }
    calls = []
    def save_scene(*args, **kwargs):
        calls.append(("still", kwargs))
        args[3].write_bytes(b"rendered")
    def save_stock(*args, **kwargs):
        calls.append(("stock", kwargs))
        args[3].write_bytes(b"rendered")
    def concat(_, output):
        output.write_bytes(b"mp4")
    def thumb(_, output):
        output.write_bytes(b"png")
    with patch.object(render_service, "render_scene_clip", side_effect=save_scene), \
         patch.object(render_service, "render_stock_clip", side_effect=save_stock), \
         patch.object(render_service, "concatenate_clips", side_effect=concat), \
         patch.object(render_service, "generate_thumbnail", side_effect=thumb), \
         patch.object(render_task.storage_service, "get_object_bytes", return_value=b"input"), \
         patch.object(render_task.storage_service, "put_object", return_value=("stored-key", "none", 1)):
        output = render_task._render_sync(video, clips, manifest)
    assert output["duration_seconds"] == 7.5
    assert [k for k, _ in calls] == ["still", "still", "stock"]
    assert calls[0][1]["fade_in"] is False
    assert calls[0][1]["fade_out"] is True
    assert calls[1][1]["fade_in"] is True
    assert calls[1][1]["fade_out"] is False
    assert calls[2][1]["fade_in"] is False
    assert calls[2][1]["fade_out"] is False
