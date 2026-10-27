"""Three-phase voice regression tests (offline, no paid provider calls)."""
import io
import uuid
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1 import voice_profiles
from app.db.models.asset import AssetType
from app.services import personal_voice_service as personal, voice_clone_service as clone


def wav_bytes(seconds=6.0):
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(24000)
        writer.writeframes(b"\x00\x00" * int(seconds * 24000))
    return output.getvalue()


def profile(owner=None, *, revoked=False, consent="explicit"):
    return SimpleNamespace(
        id=uuid.uuid4(), owner_id=owner or uuid.uuid4(),
        type=AssetType.AUDIO, storage_key="users/id/voice-references/key",
        provider_metadata={
            "purpose": "voice_profile", "revoked": revoked, "consent": consent,
            "language": "Yoruba", "duration_seconds": 8.0, "name": "Own voice",
        },
    )


def test_voice_profiles_have_strict_user_ownership_and_revocation():
    owner, stranger = uuid.uuid4(), uuid.uuid4()
    item = profile(owner)
    assert voice_profiles.is_voice_profile(item, owner)
    assert not voice_profiles.is_voice_profile(item, stranger)
    item.provider_metadata["consent"] = "missing"
    assert not voice_profiles.is_voice_profile(item, owner)
    item.provider_metadata["consent"] = "explicit"
    item.provider_metadata["revoked"] = True
    assert not voice_profiles.is_voice_profile(item, owner)


def test_license_gate_defaults_to_unavailable():
    with patch.object(clone, "get_settings", return_value=SimpleNamespace(
        voice_clone_license_confirmed=False, voice_clone_api_url=None, voice_clone_api_token=None
    )):
        with pytest.raises(clone.VoiceCloneUnavailable, match="licensed"):
            clone.configured_clone_url()


@pytest.mark.parametrize("url", [
    "http://provider.example/clone",
    "https://localhost/clone",
    "https://127.0.0.1/infer",
    "https://169.254.169.254/latest",
    "https://user:pass@provider.example/clone",
])
def test_clone_url_must_be_https_public_service(url):
    with patch.object(clone, "get_settings", return_value=SimpleNamespace(
        voice_clone_license_confirmed=True,
        voice_clone_api_url=url, voice_clone_api_token="server-token",
    )):
        with pytest.raises(clone.VoiceCloneUnavailable):
            clone.configured_clone_url()


def test_approved_https_voice_gateway_contract_is_enabled():
    with patch.object(clone, "get_settings", return_value=SimpleNamespace(
        voice_clone_license_confirmed=True,
        voice_clone_api_url="https://tts.example.org/v1/speak",
        voice_clone_api_token="token",
    )):
        assert clone.configured_clone_url() == "https://tts.example.org/v1/speak"


@pytest.mark.asyncio
async def test_revoked_profile_cannot_be_used_for_cloning_or_requested_by_stranger():
    owner = uuid.uuid4()
    item = profile(owner, revoked=True)
    with pytest.raises(clone.VoiceCloneUnavailable, match="active, consented"):
        clone.validate_clone_profile(item, owner)
    with pytest.raises(clone.VoiceCloneUnavailable):
        clone.validate_clone_profile(profile(owner), uuid.uuid4())


@pytest.mark.asyncio
async def test_reference_upload_requires_both_consent_headers():
    from starlette.requests import Request
    async def receive():
        return {"type": "http.request", "body": b"dummy", "more_body": False}
    request = Request({"type": "http", "method": "POST", "path": "/",
                       "headers": [(b"content-type", b"audio/wav")]}, receive=receive)
    with pytest.raises(HTTPException) as error:
        await voice_profiles.create_profile(request, user=SimpleNamespace(id=uuid.uuid4()),
                                           db=AsyncMock(), _=None)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_reference_enrollment_stores_private_audio_and_consent():
    from starlette.requests import Request
    owner = uuid.uuid4()
    data = b"audio"
    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}
    request = Request({"type": "http", "method": "POST", "path": "/",
                       "headers": [
                           (b"content-type", b"audio/webm"),
                           (b"x-voice-consent", b"confirmed"),
                           (b"x-clone-consent", b"confirmed"),
                           (b"x-voice-name", b"Training voice"),
                           (b"x-voice-language", b"Yoruba"),
                       ]}, receive=receive)
    db = AsyncMock()
    added = []
    db.add = MagicMock(side_effect=lambda asset: (setattr(asset, "id", uuid.uuid4()), added.append(asset)))
    with patch.object(voice_profiles, "normalize_recording", return_value=(wav_bytes(), 6.0)), \
         patch.object(voice_profiles.storage_service, "put_object",
                      return_value=("users/private/reference", "sha256", 240000)):
        result = await voice_profiles.create_profile(
            request, user=SimpleNamespace(id=owner), db=db, _=None,
        )
    assert result["language"] == "Yoruba"
    assert result["status"] == "reference_saved"
    assert added[0].owner_id == owner
    assert added[0].provider_metadata["consent"] == "explicit"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reference_revocation_removes_private_storage_object():
    owner = uuid.uuid4()
    asset = profile(owner)
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: asset)
    with patch.object(voice_profiles.storage_service, "delete_object", return_value=None) as deleted:
        await voice_profiles.revoke_profile(asset.id, user=SimpleNamespace(id=owner), db=db)
    assert asset.provider_metadata["revoked"] is True
    deleted.assert_called_once_with(asset.storage_key)
    db.commit.assert_awaited_once()


def test_trimmed_pcm_start_end_exactly_and_no_silent_padding():
    pcm = b"\x01\x00" * (24000 * 8)
    with patch.object(personal.subprocess, "run", return_value=SimpleNamespace(stdout=pcm)):
        audio, seconds = personal.normalize_recording(
            b"compressed", "audio/webm", 4, trim_start=2, trim_end=5,
        )
    assert seconds == 3
    with wave.open(io.BytesIO(audio), "rb") as reader:
        assert reader.getnframes() == 3 * 24000


def test_invalid_audio_trim_cannot_fake_completion():
    pcm = b"\x01\x00" * (24000 * 4)
    with patch.object(personal.subprocess, "run", return_value=SimpleNamespace(stdout=pcm)):
        with pytest.raises(personal.PersonalVoiceError, match="Invalid trim end"):
            personal.normalize_recording(b"abc", "audio/webm", 8, trim_start=3, trim_end=3.1)
        with pytest.raises(personal.PersonalVoiceError, match="Trim range exceeds"):
            personal.normalize_recording(b"abc", "audio/webm", 8, trim_start=1, trim_end=7)
