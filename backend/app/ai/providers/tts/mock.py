"""
Mock text-to-speech provider — generates a short silent/tone WAV placeholder
so the render pipeline has real audio bytes to compose with, without calling
an external TTS API. Replace with a Google/ElevenLabs/etc. adapter for
production (see docs/voice-system.md).
"""
import io
import math
import struct
from typing import Any

from app.ai.providers.base import VoiceProvider, VoiceSynthesisResult


def _generate_tone_wav(duration_seconds: float, frequency: float = 220.0, sample_rate: int = 16000) -> bytes:
    """Generates a minimal valid PCM WAV tone, used as a stand-in for real narration audio."""
    n_samples = int(duration_seconds * sample_rate)
    buf = io.BytesIO()
    amplitude = 3000
    frames = b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * frequency * (i / sample_rate))))
        for i in range(n_samples)
    )
    byte_rate = sample_rate * 2
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(frames)))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, byte_rate, 2, 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(frames)))
    buf.write(frames)
    return buf.getvalue()


class MockVoiceProvider(VoiceProvider):
    name = "mock"

    async def list_voices(self, locale: str | None = None) -> list[dict[str, Any]]:
        catalog = [
            {"voice_id": "mock-female-confident", "locale": "en-US", "gender": "female"},
            {"voice_id": "mock-female-confident-ng", "locale": "en-NG", "gender": "female"},
            {"voice_id": "mock-male-narrator", "locale": "en-US", "gender": "male"},
        ]
        if locale:
            return [v for v in catalog if v["locale"] == locale]
        return catalog

    async def synthesize(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        text = request.get("text", "")
        estimated_seconds = max(1.0, len(text.split()) / 2.5)  # ~150 wpm
        return VoiceSynthesisResult(
            audio_bytes=_generate_tone_wav(estimated_seconds),
            format="wav",
            duration_seconds=estimated_seconds,
            provider=self.name,
            voice_id=request.get("voice_id") or "mock-female-confident",
        )

    async def preview(self, request: dict[str, Any]) -> VoiceSynthesisResult:
        return VoiceSynthesisResult(
            audio_bytes=_generate_tone_wav(3.0),
            format="wav",
            duration_seconds=3.0,
            provider=self.name,
            voice_id=request.get("voice_id") or "mock-female-confident",
        )

    def supports(self, locale: str) -> bool:
        return True
