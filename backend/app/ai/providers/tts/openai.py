"""OpenAI text-to-speech adapter; produces validated PCM WAV for FFmpeg."""
import io
import wave
from collections.abc import Callable
from typing import Any

import httpx

from app.ai.providers.base import VoiceProvider, VoiceSynthesisResult
from app.ai.providers.openai_http import MediaProviderError, post_openai_media

# Supported built-in OpenAI speech voices (custom voice IDs are out of scope).
BUILTIN_VOICES = (
    "alloy", "ash", "ballad", "coral", "echo", "fable", "onyx",
    "nova", "sage", "shimmer", "verse", "marin", "cedar",
)


class OpenAIVoiceProvider(VoiceProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini-tts",
        default_voice: str = "alloy",
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.default_voice = default_voice
        self.client_factory = client_factory or httpx.AsyncClient
        if default_voice not in BUILTIN_VOICES:
            raise ValueError("Unsupported default OpenAI speech voice")

    async def list_voices(self, locale: str | None = None) -> list[dict[str, Any]]:
        # OpenAI voices are multilingual, not locale-specific. Actual
        # pronunciation should be verified by speakers of the language.
        return [{"voice_id": voice, "locale": locale or "multilingual", "gender": None}
                for voice in BUILTIN_VOICES]

    def supports(self, locale: str) -> bool:
        return True

    async def synthesize(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        value = request.get("text")
        if not isinstance(value, str) or not (1 <= len(value.strip()) <= 4096):
            raise ValueError("OpenAI narration text must contain 1–4096 characters")
        voice = request.get("voice_id") or self.default_voice
        if voice not in BUILTIN_VOICES:
            raise ValueError("Unknown OpenAI voice identifier")
        try:
            speed = float(request.get("pace") or 1.0)
        except (TypeError, ValueError):
            raise ValueError("Voice pace must be numeric") from None
        if not 0.25 <= speed <= 4.0:
            raise ValueError("Voice pace must be between 0.25 and 4.0")

        response = await post_openai_media(
            api_key=self.api_key, endpoint="/audio/speech",
            payload={
                "model": self.model, "voice": voice, "input": value,
                "response_format": "wav", "speed": speed,
            },
            client_factory=self.client_factory, timeout=120.0,
        )
        raw = response.content
        if not 44 <= len(raw) <= 32 * 1024 * 1024 or raw[:4] != b"RIFF":
            raise MediaProviderError("OpenAI speech response is not a valid WAV file")
        try:
            with wave.open(io.BytesIO(raw), "rb") as audio:
                if audio.getcomptype() != "NONE" or audio.getframerate() <= 0:
                    raise ValueError("Unsupported WAV encoding")
                duration = audio.getnframes() / audio.getframerate()
        except (wave.Error, ValueError, EOFError):
            raise MediaProviderError("OpenAI speech response cannot be decoded as PCM WAV") from None
        if duration <= 0 or duration > 1800:
            raise MediaProviderError("OpenAI speech duration is invalid")
        return VoiceSynthesisResult(
            audio_bytes=raw, format="wav", duration_seconds=duration,
            provider=self.name, voice_id=voice,
        )

    async def preview(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        return await self.synthesize({
            "voice_id": request.get("voice_id"), "text": request.get("text") or "Voice preview",
            "pace": 1.0,
        })
