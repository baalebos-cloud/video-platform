"""Own-voice scene recording and Nigerian-language generation safety tests."""
import io
import subprocess
import uuid
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1.videos import GenerateVideoRequest
from app.api.v1 import storyboards
from app.db.models.video import VideoStatus
from app.services.personal_voice_service import (
    PersonalVoiceError, empty_narration, normalize_recording,
)
from app.workers.tasks import voice_task


def wav_length_seconds(audio):
    with wave.open(io.BytesIO(audio), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getframerate() == 24000
        return reader.getnframes() / reader.getframerate()


def make_request(audio=b"sample", media="audio/webm", consent=True):
    headers = [
        (b"content-type", media.encode()),
        (b"content-length", str(len(audio)).encode()),
    ]
    if consent:
        headers.append((b"x-voice-consent", b"confirmed"))
    async def receive():
        return {"type": "http.request", "body": audio, "more_body": False}
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers},
                   receive=receive)


@pytest.mark.parametrize("lang,locale", [
    ("English", "en-NG"), ("Nigerian Pidgin", "pcm-NG"), ("Yoruba", "yo-NG"),
])
def test_supported_languages_allow_explicit_self_recorded_mode(lang, locale):
    body = GenerateVideoRequest(
        project_id=uuid.uuid4(), topic="Educational film", language=lang,
        locale=locale, voice={"mode": "recorded"}, duration_seconds=180,
    )
    assert body.voice.mode == "recorded"


@pytest.mark.parametrize("lang,locale", [
    ("Nigerian Pidgin", "pcm-NG"), ("Yoruba", "yo-NG"),
])
def test_unsupported_cloudflare_languages_block_auto_tts(lang, locale):
    with pytest.raises(ValidationError, match="require your recorded narration"):
        GenerateVideoRequest(project_id=uuid.uuid4(), topic="Training video",
                             language=lang, locale=locale, voice={"mode": "auto"})


def test_language_locale_mismatch_is_rejected():
    with pytest.raises(ValidationError, match="locale matching"):
        GenerateVideoRequest(project_id=uuid.uuid4(), topic="Video topic",
                             language="Yoruba", locale="en-US", voice={"mode": "recorded"})


def test_default_english_auto_remains_backwards_compatible():
    payload = GenerateVideoRequest(project_id=uuid.uuid4(), topic="Teaching engineering")
    assert payload.voice.mode == "auto"
    assert payload.locale == "en-US"


def test_silent_placeholder_is_real_pcm_wav():
    wav = empty_narration()
    assert abs(wav_length_seconds(wav) - 0.5) < 0.001


def test_audio_upload_is_transcoded_and_measured(monkeypatch):
    fake_pcm = b"\x00\x00" * 24000 * 3
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=fake_pcm))
    converted, duration = normalize_recording(b"compressed", "audio/webm;codecs=opus", 5.0)
    assert duration == 3.0
    assert wav_length_seconds(converted) == 3.0


def test_incorrect_or_overlong_recordings_fail_without_silent_truncation(monkeypatch):
    with pytest.raises(PersonalVoiceError, match="Use a WAV"):
        normalize_recording(b"invalid", "application/pdf", 5)
    with pytest.raises(PersonalVoiceError, match="3 MB"):
        normalize_recording(b"a" * (3 * 1024 * 1024 + 1), "audio/webm", 5)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=b"\x00\x00" * 24000 * 7))
    with pytest.raises(PersonalVoiceError, match="fit within"):
        normalize_recording(b"compressed", "audio/webm", 4)


@pytest.mark.asyncio
async def test_recorded_narration_skips_provider_api_and_preserves_scene_length():
    video = SimpleNamespace(
        id=uuid.uuid4(), locale="yo-NG", language="Yoruba",
        voice_preferences={"mode": "recorded"},
    )
    scene = SimpleNamespace(id=uuid.uuid4(), duration_seconds=14.0, narration="Báwo ni?")
    with patch.object(voice_task.voice_service, "synthesize_narration", new_callable=AsyncMock) as synth, \
         patch.object(voice_task.storage_service, "put_object", return_value=("key", "hash", 24044)):
        key, duration = await voice_task.run(video, scene)
    synth.assert_not_awaited()
    assert key == "key"
    assert duration == 14.0


@pytest.mark.asyncio
async def test_upload_is_owned_and_marks_video_for_rerender_without_tts():
    video_id, scene_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    video = SimpleNamespace(id=video_id, status=VideoStatus.READY, needs_rerender=False)
    scene = SimpleNamespace(id=scene_id, video_id=video_id, duration_seconds=10.0, audio_asset_id=None)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: scene)
    user = SimpleNamespace(id=user_id)
    with patch.object(storyboards, "require_video_owner", new_callable=AsyncMock, return_value=video), \
         patch.object(storyboards, "normalize_recording", return_value=(empty_narration(), 0.5)), \
         patch.object(storyboards.storage_service, "put_object", return_value=("key", "hash", 24044)):
        reply = await storyboards.upload_personal_scene_narration(
            video_id, scene_id, make_request(), user=user, db=db, _=None,
        )
    assert reply["audio_state"] == "recorded"
    assert reply["needs_rerender"]
    assert video.needs_rerender
    assert scene.audio_asset_id is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_requires_explicit_recording_consent():
    with pytest.raises(HTTPException) as error:
        await storyboards.upload_personal_scene_narration(
            uuid.uuid4(), uuid.uuid4(), make_request(consent=False),
            user=SimpleNamespace(id=uuid.uuid4()), db=AsyncMock(), _=None,
        )
    assert error.value.status_code == 400
