"""Cloudflare MeloTTS narration. Convert MP3 to measured PCM WAV for FFmpeg."""
import asyncio
import base64
import binascii
import io
import subprocess
import wave
from collections.abc import Callable
from typing import Any

import httpx

from app.ai.providers.base import VoiceProvider, VoiceSynthesisResult
from app.ai.providers.cloudflare_http import run_cloudflare_model
from app.ai.providers.openai_http import MediaProviderError

MAX_MP3_BYTES = 12 * 1024 * 1024


def mp3_to_wav(data: bytes) -> tuple[bytes, float]:
    if not data or len(data) > MAX_MP3_BYTES:
        raise MediaProviderError("Cloudflare narration exceeds audio size limit")
    try:
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le",
             "-ac", "1", "-ar", "24000", "pipe:1"],
            input=data, capture_output=True, timeout=60, check=True,
        )
        pcm = result.stdout
        if len(pcm) > 70 * 1024 * 1024:
            raise ValueError("Decoded audio too large")
        duration = len(pcm) / (24000 * 2)
        if not 0.1 <= duration <= 900:
            raise ValueError("Invalid narration duration")
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        return output.getvalue(), duration
    except (subprocess.SubprocessError, OSError, wave.Error, ValueError):
        raise MediaProviderError("Could not decode Cloudflare narration") from None


class CloudflareVoiceProvider(VoiceProvider):
    name = "cloudflare"

    def __init__(self, *, account_id: str, api_token: str,
                 model: str = "@cf/myshell-ai/melotts",
                 client_factory: Callable[[], httpx.AsyncClient] | None = None):
        self.account_id, self.api_token, self.model = account_id, api_token, model
        self.client_factory = client_factory or httpx.AsyncClient

    async def list_voices(self, locale: str | None = None) -> list[dict[str, Any]]:
        return [{"voice_id": "melotts-default", "locale": locale or "en-US", "gender": None}]

    def supports(self, locale: str) -> bool:
        return locale.split("-")[0].lower() in {"en", "fr", "es", "de", "it", "ja", "ko", "zh"}

    async def synthesize(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        text = request.get("text")
        locale = str(request.get("locale") or "en-US")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 3000:
            raise ValueError("Narration must contain 1–3000 characters")
        if not self.supports(locale):
            raise ValueError("This Cloudflare TTS model does not support that language")
        voice_id = request.get("voice_id")
        if voice_id and voice_id != "melotts-default":
            raise ValueError("Unsupported Cloudflare voice")
        response = await run_cloudflare_model(
            account_id=self.account_id, api_token=self.api_token, model=self.model,
            payload={"prompt": text, "lang": locale.split("-")[0].lower()},
            client_factory=self.client_factory,
        )
        try:
            if response.headers.get("content-type", "").startswith("audio/mpeg"):
                mp3 = response.content
            else:
                document = response.json()
                if document.get("success") is False:
                    raise ValueError("Unsuccessful inference")
                encoded = document.get("result", {}).get("audio")
                if not isinstance(encoded, str) or len(encoded) > MAX_MP3_BYTES * 2:
                    raise ValueError("Invalid audio payload")
                mp3 = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError, KeyError, binascii.Error):
            raise MediaProviderError("Cloudflare returned invalid narration audio") from None
        wav_bytes, duration = await asyncio.to_thread(mp3_to_wav, mp3)
        return VoiceSynthesisResult(audio_bytes=wav_bytes, format="wav",
                                    duration_seconds=duration, provider=self.name, voice_id="melotts-default")

    async def preview(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        return await self.synthesize({"text": request.get("text") or "A preview of the voice.",
                                      "locale": request.get("locale") or "en-US"})
