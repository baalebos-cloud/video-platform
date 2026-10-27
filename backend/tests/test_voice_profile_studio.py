"""Voice reference enrollment, safe feature gating, and personal audio trimming."""
import base64
import io
import uuid
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1 import voice_profiles
from app.api.v1.videos import GenerateVideoRequest
from app.config.settings import Settings
from app.db.models.asset import AssetType
from app.services.personal_voice_service import PersonalVoiceError, normalize_recording
from app.services.voice_clone_service import VoiceCloneUnavailable, synthesize_personal_voice


def req(audio=b"some-webm-audio", *, consent="self", name="My voice", language="Yoruba"):
    headers = [
        (b"content-type", b"audio/webm"),
        (b"content-length", str(len(audio)).encode()),
        (b"x-voice-consent", consent.encode()),
        (b"x-voice-name", name.encode()),
        (b"x-voice-language", language.encode()),
    ]
    async def receive():
        return {"type": "http.request", "body": audio, "more_body": False}
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers}, receive)


def settings(**kwargs):
    return Settings(
        _env_file=None,
        voice_clone_endpoint=kwargs.pop("voice_clone_endpoint", None),
        voice_clone_token=kwargs.pop("voice_clone_token", None),
        voice_clone_license_approved=kwargs.pop("voice_clone_license_approved", False),
        **kwargs,
    )


def test_voice_cloning_is_off_by_default():
    assert not settings().voice_clone_enabled
    assert not settings(voice_clone_endpoint="https://voice.test/api/synthesize",
                        voice_clone_token="demo", voice_clone_license_approved=False).voice_clone_enabled
    assert not settings(voice_clone_endpoint="http://voice.test/api/synthesize",
                        voice_clone_token="demo", voice_clone_license_approved=True).voice_clone_enabled
    assert settings(voice_clone_endpoint="https://voice.test/api/synthesize",
                    voice_clone_token="demo", voice_clone_license_approved=True).voice_clone_enabled


@pytest.mark.asyncio
async def test_no_inference_when_license_is_not_approved():
    with patch("app.services.voice_clone_service.get_settings", return_value=settings()), \
         patch("app.services.voice_clone_service.storage_service.get_object_bytes") as storage:
        with pytest.raises(VoiceCloneUnavailable, match="not configured"):
            await synthesize_personal_voice(
                text="Narration", locale="yo-NG", reference_key="key", max_scene_seconds=10
            )
        storage.assert_not_called()


def test_cloned_request_requires_reference_id():
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="Select your enrolled"):
        GenerateVideoRequest(
            project_id=uuid.uuid4(), topic="Test video",
            voice={"mode": "cloned"},
        )


def test_user_reference_not_treated_as_an_existing_narration():
    own = SimpleNamespace(
        id=uuid.uuid4(), owner_id=uuid.uuid4(), type=AssetType.AUDIO,
        provider_metadata={"provider": "personal_voice_reference", "consent": "self_recorded"},
    )
    assert voice_profiles.is_voice_profile(own)
    own.provider_metadata = {"provider": "personal_recording"}
    assert not voice_profiles.is_voice_profile(own)


@pytest.mark.asyncio
async def test_consent_is_required_before_enrolling():
    with pytest.raises(HTTPException) as exc:
        await voice_profiles.create_voice_profile(
            req(consent="confirmed"), user=SimpleNamespace(id=uuid.uuid4()),
            db=AsyncMock(), _=None,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_reference_upload_creates_private_scoped_audio_asset():
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    db.add = MagicMock(side_effect=lambda asset: setattr(asset, "id", uuid.uuid4()))
    db.refresh = AsyncMock(side_effect=lambda asset: setattr(asset, "created_at", None))
    with patch.object(voice_profiles, "normalize_recording", return_value=(b"RIFF-sample", 9.5)), \
         patch.object(voice_profiles.storage_service, "put_object",
                      return_value=(f"users/{user_id}/voice-profiles/key", "digest", 100)):
        result = await voice_profiles.create_voice_profile(
            req(), user=user, db=db, _=None,
        )
    assert result["status"] == "reference_saved"
    assert result["duration_seconds"] == 9.5
    assert result["language"] == "Yoruba"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_delete_requires_owner_and_deletes_storage():
    profile_id, owner_id = uuid.uuid4(), uuid.uuid4()
    stored = SimpleNamespace(
        id=profile_id, owner_id=owner_id, storage_key="private-reference",
        type=AssetType.AUDIO,
        provider_metadata={"provider": "personal_voice_reference", "consent": "self_recorded"},
    )
    db = AsyncMock()
    db.get.return_value = stored
    with patch.object(voice_profiles.storage_service, "delete_object") as delete:
        with pytest.raises(HTTPException) as err:
            await voice_profiles.delete_voice_profile(
                profile_id, user=SimpleNamespace(id=uuid.uuid4()), db=db
            )
        assert err.value.status_code == 404
        delete.assert_not_called()
        await voice_profiles.delete_voice_profile(
            profile_id, user=SimpleNamespace(id=owner_id), db=db
        )
    delete.assert_called_once_with("private-reference")
    db.delete.assert_awaited_once_with(stored)
    db.commit.assert_awaited_once()


def test_recording_trim_is_bounded_and_passed_to_ffmpeg(monkeypatch):
    import subprocess
    commands = []
    def fake_run(command, **kwargs):
        commands.append(command)
        # 2 seconds of normalized PCM audio
        return SimpleNamespace(stdout=b"\x00\x00" * 24000 * 2)
    monkeypatch.setattr(subprocess, "run", fake_run)
    output, duration = normalize_recording(
        b"compressed", "audio/webm", 4, trim_start=3, trim_end=5
    )
    assert duration == 2
    with wave.open(io.BytesIO(output), "rb") as wav:
        assert wav.getframerate() == 24000
    assert commands[0][commands[0].index("-ss") + 1] == "3"
    assert commands[0][commands[0].index("-t") + 1] == "2"
    with pytest.raises(PersonalVoiceError, match="Trimmed audio"):
        normalize_recording(b"compressed", "audio/webm", 4, trim_start=2, trim_end=15)
    with pytest.raises(PersonalVoiceError, match="Invalid audio trim"):
        normalize_recording(b"compressed", "audio/webm", 4, trim_start=float("nan"))


@pytest.mark.asyncio
async def test_licensed_cloning_contract_uses_private_reference_without_logging_content():
    wav = b"RIFF" + b"\x00" * 20
    with patch("app.services.voice_clone_service.get_settings", return_value=settings(
        voice_clone_endpoint="https://voice.example.org/api/synthesize",
        voice_clone_token="operator-token", voice_clone_license_approved=True,
    )), patch("app.services.voice_clone_service.storage_service.get_object_bytes", return_value=wav), \
        patch("app.services.voice_clone_service.normalize_recording", return_value=(b"processed", 7.0)), \
        patch("app.services.voice_clone_service.httpx.AsyncClient") as client_mock:
        client = client_mock.return_value.__aenter__.return_value
        client.post = AsyncMock(return_value=SimpleNamespace(
            status_code=200, content=b"small",
            json=lambda: {"audio_wav_base64": base64.b64encode(b"RIFF+audio").decode()},
        ))
        result, seconds = await synthesize_personal_voice(
            text="Hello", locale="yo-NG", reference_key="owner/reference", max_scene_seconds=9,
        )
    assert result == b"processed" and seconds == 7.0
    assert client.post.await_count == 1
    args = client.post.await_args
    assert args.args[0] == "https://voice.example.org/api/synthesize"
    assert args.kwargs["json"]["locale"] == "yo-NG"
    assert args.kwargs["headers"]["Authorization"] == "Bearer operator-token"
