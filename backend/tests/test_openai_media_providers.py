"""Real-provider contracts tested offline with HTTP transports; never bill CI."""
import base64
import io
import uuid
import wave
from unittest.mock import patch

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.ai.providers.image.openai import OpenAIImageProvider
from app.ai.providers.tts.openai import OpenAIVoiceProvider
from app.ai.providers.openai_http import MediaProviderError
from app.config.settings import Settings


def client_factory(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def fixture_png():
    image = Image.new("RGB", (128, 128), (25, 50, 75))
    memory = io.BytesIO()
    image.save(memory, format="PNG")
    return memory.getvalue()


def fixture_wav():
    memory = io.BytesIO()
    with wave.open(memory, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return memory.getvalue()


@pytest.mark.asyncio
async def test_image_generation_sends_valid_model_dimensions_and_png():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(fixture_png()).decode("ascii")}]}
        )

    provider = OpenAIImageProvider(
        api_key="unit-test-key", quality="medium", client_factory=client_factory(respond),
    )
    result = await provider.generate("Cinematic sunrise over mountains", aspect_ratio="16:9")
    payload = __import__("json").loads(calls[0].content)
    assert calls[0].url.path == "/v1/images/generations"
    assert calls[0].headers["Authorization"] == "Bearer unit-test-key"
    assert payload["size"] == "1536x1024"
    assert payload["output_format"] == "png"
    assert result.provider == "openai" and result.format == "png"
    assert result.image_bytes.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_voice_generation_is_real_wav_with_measured_duration():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=fixture_wav(), headers={"Content-Type": "audio/wav"})

    provider = OpenAIVoiceProvider(api_key="unit-test-key", client_factory=client_factory(respond))
    result = await provider.synthesize({"text": "This is a narration", "voice_id": "alloy", "pace": 1.25})
    payload = __import__("json").loads(calls[0].content)
    assert calls[0].url.path == "/v1/audio/speech"
    assert payload["response_format"] == "wav"
    assert payload["model"] == "gpt-4o-mini-tts"
    assert payload["speed"] == 1.25
    assert result.duration_seconds == pytest.approx(1.0)
    assert result.format == "wav" and result.voice_id == "alloy"


@pytest.mark.asyncio
async def test_errors_do_not_become_mock_content_or_expose_credentials():
    provider = OpenAIImageProvider(
        api_key="secret-in-test",
        client_factory=client_factory(lambda request: httpx.Response(401, json={"error": {"message": "Invalid secret-in-test"}})),
    )
    with pytest.raises(MediaProviderError) as exc:
        await provider.generate("A city street")
    assert "401" in str(exc.value)
    assert "secret-in-test" not in str(exc.value)


@pytest.mark.asyncio
async def test_rate_limit_errors_are_explicit():
    provider = OpenAIVoiceProvider(
        api_key="key",
        client_factory=client_factory(lambda request: httpx.Response(429, json={"error": "rate limit"})),
    )
    with pytest.raises(MediaProviderError, match="429"):
        await provider.synthesize({"text": "Hello"})


@pytest.mark.asyncio
async def test_invalid_image_bytes_fail_closed():
    provider = OpenAIImageProvider(
        api_key="key",
        client_factory=client_factory(lambda request: httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(b"not-an-image").decode()}]}
        )),
    )
    with pytest.raises(MediaProviderError, match="valid PNG"):
        await provider.generate("A sunny field")


@pytest.mark.asyncio
async def test_invalid_voice_id_fails_before_paid_request():
    sent = []

    def respond(request):
        sent.append(request)
        return httpx.Response(200, content=fixture_wav())

    provider = OpenAIVoiceProvider(api_key="key", client_factory=client_factory(respond))
    with pytest.raises(ValueError, match="voice"):
        await provider.synthesize({"text": "Hello", "voice_id": "not-available"})
    assert sent == []


def test_missing_key_rejected_when_real_provider_selected():
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, voice_provider="openai", image_provider="mock", openai_api_key=None)
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, voice_provider="mock", image_provider="openai", openai_api_key="")


def test_mock_remains_default_without_credentials():
    settings = Settings(_env_file=None, voice_provider="mock", image_provider="mock", openai_api_key=None)
    assert settings.voice_provider == "mock" and settings.image_provider == "mock"
