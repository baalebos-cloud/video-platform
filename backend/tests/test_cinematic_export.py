"""Cinematic export regression tests that make no live API calls or paid media requests."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.v1.videos import GenerateVideoRequest
from app.services import render_service, storage_service


def test_cinematic_scene_export_is_full_bleed_and_social_compatible(monkeypatch):
    commands = []
    monkeypatch.setattr(render_service, "_run", lambda cmd: commands.append(cmd))
    render_service.render_scene_clip(
        Path("/tmp/photo.png"), Path("/tmp/voice.wav"), 3.0, Path("/tmp/movie.mp4"),
        aspect_ratio="9:16", cinematic_motion=True,
    )
    cmd = commands[0]
    filters = cmd[cmd.index("-vf") + 1]
    assert "force_original_aspect_ratio=increase" in filters
    assert "crop=1080:1920" in filters
    assert "zoompan=" in filters
    assert "pad=" not in filters
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert "+faststart" in cmd


def test_landscape_uses_landscape_frame_without_letterboxing(monkeypatch):
    commands = []
    monkeypatch.setattr(render_service, "_run", lambda cmd: commands.append(cmd))
    render_service.render_scene_clip(
        Path("/tmp/photo.png"), Path("/tmp/voice.wav"), 3.0, Path("/tmp/movie.mp4"),
        aspect_ratio="16:9",
    )
    filters = commands[0][commands[0].index("-vf") + 1]
    assert "crop=1920:1080" in filters
    assert "zoompan=" not in filters


def test_unsupported_ratio_rejected_before_ffmpeg():
    with pytest.raises(render_service.RenderError, match="Unsupported aspect ratio"):
        render_service.render_scene_clip(Path("a"), Path("b"), 1, Path("c"), aspect_ratio="2:1")


def test_download_url_forces_mp4_attachment(monkeypatch):
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://assets.example.com/signed"
    monkeypatch.setattr(storage_service, "_client", lambda **kwargs: client)
    url = storage_service.get_signed_url("videos/x/final/abc", download_filename="baalebos-123.mp4")
    assert url == "https://assets.example.com/signed"
    params = client.generate_presigned_url.call_args.kwargs["Params"]
    assert params["ResponseContentDisposition"] == 'attachment; filename="baalebos-123.mp4"'
    assert params["ResponseContentType"] == "video/mp4"


def test_preview_url_does_not_force_download(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(storage_service, "_client", lambda **kwargs: client)
    storage_service.get_signed_url("videos/x/final/abc")
    params = client.generate_presigned_url.call_args.kwargs["Params"]
    assert "ResponseContentDisposition" not in params


def test_new_video_defaults_to_clean_export():
    import uuid
    payload = GenerateVideoRequest(project_id=uuid.uuid4(), topic="Cinematic future of AI")
    assert payload.caption_style == "none"
    with pytest.raises(ValidationError):
        GenerateVideoRequest(project_id=uuid.uuid4(), topic="Test", caption_style="watermark")
