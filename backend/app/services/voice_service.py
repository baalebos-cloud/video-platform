"""
Voice orchestrator — selects a voice configuration and routes the
synthesis request to the configured TTS provider (blueprint section 9).
"""
from app.ai.providers.base import VoiceSynthesisResult
from app.ai.providers.registry import select_provider


async def list_voices(locale: str | None = None) -> list[dict]:
    provider = select_provider("voice")
    return await provider.list_voices(locale)


async def synthesize_narration(
    *, text: str, locale: str, voice_preferences: dict | None = None
) -> VoiceSynthesisResult:
    provider = select_provider("voice")
    request = {
        "text": text,
        "locale": locale,
        "voice_id": (voice_preferences or {}).get("voice_id"),
        "style": (voice_preferences or {}).get("style"),
        "emotion": (voice_preferences or {}).get("emotion"),
        "pace": (voice_preferences or {}).get("pace", 1.0),
        "pitch": (voice_preferences or {}).get("pitch"),
        "format": "wav",
    }
    return await provider.synthesize(request)


async def preview_voice(*, voice_id: str, sample_text: str = "This is a preview of the selected voice.") -> VoiceSynthesisResult:
    provider = select_provider("voice")
    return await provider.preview({"voice_id": voice_id, "text": sample_text})
