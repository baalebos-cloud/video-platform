"""Smoke tests for the mock AI provider adapters — these must work with zero external credentials."""
import pytest

from app.ai.providers.image.mock import MockImageProvider
from app.ai.providers.llm.mock import MockLLMProvider
from app.ai.providers.tts.mock import MockVoiceProvider


@pytest.mark.asyncio
async def test_mock_llm_returns_valid_json_plan():
    import json

    provider = MockLLMProvider()
    response = await provider.complete("system", "user", json_mode=True)
    payload = json.loads(response.text)
    assert "scenes" in payload
    assert payload["title"]


@pytest.mark.asyncio
async def test_mock_voice_provider_synthesizes_audio():
    provider = MockVoiceProvider()
    result = await provider.synthesize({"text": "hello world", "voice_id": "mock-female-confident"})
    assert result.audio_bytes.startswith(b"RIFF")
    assert result.duration_seconds > 0


@pytest.mark.asyncio
async def test_mock_image_provider_generates_bytes():
    provider = MockImageProvider()
    result = await provider.generate("a cinematic scene", aspect_ratio="9:16")
    assert len(result.image_bytes) > 0
