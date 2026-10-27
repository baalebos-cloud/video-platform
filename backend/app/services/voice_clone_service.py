"""Opt-in adapter contract for an independently licensed voice-cloning service.

The Baalebos app DOES NOT bundle model weights or an unlicensed voice model.
Only an operator-supplied HTTPS endpoint with explicit commercial approval
can synthesize from a user's private consented reference. The contract is:
POST JSON {text, language, reference_wav_base64}, return mono WAV bytes.
"""
import base64
import ipaddress
import urllib.parse
import uuid

import httpx

from app.config.settings import get_settings
from app.db.models.asset import Asset
from app.services.personal_voice_service import PersonalVoiceError, normalize_recording
from app.services.provider_guard import claim_media_call
from app.services import storage_service


class VoiceCloneUnavailable(ValueError):
    pass


def configured_clone_url() -> str:
    settings = get_settings()
    if not (settings.voice_clone_license_confirmed and settings.voice_clone_api_url
            and settings.voice_clone_api_token):
        raise VoiceCloneUnavailable(
            "Automatic voice cloning is not configured with an approved licensed provider"
        )
    parsed = urllib.parse.urlsplit(settings.voice_clone_api_url)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password or parsed.fragment:
        raise VoiceCloneUnavailable("Voice cloning endpoint must be an approved HTTPS service")
    if hostname.lower() in {"localhost", "metadata.google.internal"} or hostname.endswith(".local"):
        raise VoiceCloneUnavailable("Voice cloning endpoint cannot use a local/internal host")
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not addr.is_global:
            raise VoiceCloneUnavailable("Voice cloning endpoint cannot target private networks")
    return settings.voice_clone_api_url


def validate_clone_profile(asset: Asset | None, owner_id: uuid.UUID) -> None:
    from app.api.v1.voice_profiles import is_voice_profile
    if not is_voice_profile(asset, owner_id):
        raise VoiceCloneUnavailable("An active, consented voice profile belonging to you is required")


async def synthesize_cloned_scene(
    text: str, language: str, asset: Asset, owner_id: uuid.UUID,
) -> tuple[bytes, float]:
    """One scene, quota guarded, bounded inference and strict WAV normalization."""
    url = configured_clone_url()
    validate_clone_profile(asset, owner_id)
    if language not in {"English", "Nigerian Pidgin", "Yoruba"}:
        raise VoiceCloneUnavailable("Unsupported cloned narration language")
    if not 3 <= len(text) <= 2800:
        raise VoiceCloneUnavailable("Scene narration is missing or too long")
    reference = storage_service.get_object_bytes(asset.storage_key)
    if len(reference) > 2 * 1024 * 1024:
        raise VoiceCloneUnavailable("Voice reference is unexpectedly large")
    await claim_media_call("voice")
    payload = {
        "text": text,
        "language": {"English": "en", "Nigerian Pidgin": "pcm", "Yoruba": "yo"}[language],
        "reference_wav_base64": base64.b64encode(reference).decode("ascii"),
    }
    # No user-supplied URL, model or token. Never log raw audio or text.
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=False, trust_env=False) as client:
            response = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {settings.voice_clone_api_token}"},
            )
    except httpx.RequestError:
        raise VoiceCloneUnavailable("Licensed voice provider is unavailable") from None
    if response.status_code != 200:
        raise VoiceCloneUnavailable(f"Licensed voice provider refused synthesis (HTTP {response.status_code})")
    if not response.headers.get("content-type", "").lower().startswith(("audio/wav", "audio/x-wav", "audio/wave")):
        raise VoiceCloneUnavailable("Licensed voice provider returned no WAV audio")
    if len(response.content) > 7 * 1024 * 1024:
        raise VoiceCloneUnavailable("Licensed voice provider response is too large")
    try:
        normalized, duration = normalize_recording(response.content, "audio/wav", 60)
    except PersonalVoiceError:
        raise VoiceCloneUnavailable("Licensed voice provider returned invalid narration audio") from None
    return normalized, duration
