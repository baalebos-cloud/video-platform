"""Optional private reference-audio synthesis with an operator-licensed service.

The endpoint is NEVER inferred from a user upload or public repository.
It is an operator-owned HTTPS service behind bearer authentication, with
a narrow documented JSON contract and no fallback to a paid TTS vendor.

POST {VOICE_CLONE_ENDPOINT}
{ text, locale, reference_audio_wav_base64 }
-> { audio_wav_base64 }  (24kHz WAV preferred)

Models such as WazobiaVoice with non-commercial research licenses must
NOT be deployed here for a commercial service without a separate license.
"""
import asyncio
import base64
import binascii

import httpx

from app.config.settings import get_settings
from app.services import storage_service
from app.services.personal_voice_service import PersonalVoiceError, normalize_recording

MAX_REFERENCE_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 3 * 1024 * 1024


class VoiceCloneUnavailable(RuntimeError):
    pass


async def synthesize_personal_voice(
    *, text: str, locale: str, reference_key: str, max_scene_seconds: float,
) -> tuple[bytes, float]:
    settings = get_settings()
    if not settings.voice_clone_enabled:
        raise VoiceCloneUnavailable(
            "Automatic personal-voice synthesis is not configured or commercially licensed"
        )
    if locale not in {"en-NG", "en-US", "en-GB", "pcm-NG", "yo-NG"}:
        raise VoiceCloneUnavailable("Language is not supported by this voice-profile integration")
    if not text.strip() or len(text) > 2800:
        raise VoiceCloneUnavailable("Scene narration must contain 1-2800 characters")
    try:
        reference = await asyncio.to_thread(storage_service.get_object_bytes, reference_key)
        if len(reference) > MAX_REFERENCE_BYTES or not reference.startswith(b"RIFF"):
            raise VoiceCloneUnavailable("Saved reference audio is not a supported WAV recording")
        async with httpx.AsyncClient(timeout=90, follow_redirects=False, trust_env=False) as client:
            response = await client.post(
                settings.voice_clone_endpoint,
                headers={"Authorization": f"Bearer {settings.voice_clone_token}"},
                json={
                    "text": text,
                    "locale": locale,
                    "reference_audio_wav_base64": base64.b64encode(reference).decode("ascii"),
                },
            )
        if response.status_code != 200:
            raise VoiceCloneUnavailable(
                f"Licensed personal-voice inference failed (HTTP {response.status_code})"
            )
        if len(response.content) > MAX_RESPONSE_BYTES * 2:
            raise VoiceCloneUnavailable("Voice inference response exceeded the size limit")
        payload = response.json()
        audio = base64.b64decode(payload["audio_wav_base64"], validate=True)
        if not audio or len(audio) > MAX_RESPONSE_BYTES:
            raise VoiceCloneUnavailable("Voice inference audio was empty or oversized")
        result, seconds = await asyncio.to_thread(
            normalize_recording, audio, "audio/wav", max_scene_seconds
        )
        return result, seconds
    except VoiceCloneUnavailable:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, binascii.Error, PersonalVoiceError):
        # Never forward third-party responses or potentially sensitive URLs.
        raise VoiceCloneUnavailable("Licensed personal-voice inference could not produce valid audio") from None
