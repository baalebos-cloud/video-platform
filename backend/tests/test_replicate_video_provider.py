"""Offline contract tests for the Replicate generative-video adapter.
Never contact Replicate; every HTTP call goes through httpx.MockTransport."""
import json

import httpx
import pytest
from pydantic import ValidationError

from app.ai.providers.openai_http import MediaProviderError
from app.ai.providers.video.replicate import ReplicateVideoProvider
from app.config.settings import Settings


def mock_client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_replicate_creates_prediction_polls_and_downloads():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/predictions"):
            body = json.loads(request.content)
            assert body["input"]["prompt"].startswith("A cinematic city skyline")
            assert "Camera: slow push-in." in body["input"]["prompt"]
            assert body["input"]["image"].startswith("data:image/png;base64,")
            return httpx.Response(201, json={
                "status": "starting",
                "urls": {"get": "https://api.replicate.com/v1/predictions/abc123"},
            })
        if "predictions/abc123" in str(request.url):
            return httpx.Response(200, json={
                "status": "succeeded",
                "output": "https://replicate.delivery/output.mp4",
            })
        if "replicate.delivery" in request.url.host:
            return httpx.Response(200, content=b"\x00\x00\x00\x18ftypmp4" + b"x" * 100)
        raise AssertionError(f"unexpected request: {request.url}")

    provider = ReplicateVideoProvider(
        api_token="secret-token",
        model="kwaivgi/kling-v1.6-standard",
        client_factory=mock_client(handler),
        poll_interval_seconds=0,
    )
    result = await provider.generate_clip({
        "prompt": "A cinematic city skyline at dusk",
        "camera": "slow push-in",
        "duration_seconds": 5,
        "reference_image_bytes": b"fake-png-bytes",
        "reference_image_format": "png",
    })
    assert result.provider == "replicate"
    assert result.format == "mp4"
    assert result.video_bytes.startswith(b"\x00\x00\x00\x18ftypmp4")
    assert calls[0].headers["Authorization"] == "Bearer secret-token"
    assert "/models/kwaivgi/kling-v1.6-standard/predictions" in calls[0].url.path


@pytest.mark.asyncio
async def test_replicate_failed_prediction_does_not_leak_provider_text():
    def handler(request):
        if request.url.path.endswith("/predictions"):
            return httpx.Response(201, json={
                "status": "processing",
                "urls": {"get": "https://api.replicate.com/v1/predictions/zzz"},
            })
        return httpx.Response(200, json={
            "status": "failed",
            "error": "nsfw content detected: secret-internal-reason",
        })

    provider = ReplicateVideoProvider(
        api_token="secret-token", model="owner/model",
        client_factory=mock_client(handler), poll_interval_seconds=0,
    )
    with pytest.raises(MediaProviderError) as error:
        await provider.generate_clip({"prompt": "test scene"})
    assert "secret-internal-reason" not in str(error.value)


@pytest.mark.asyncio
async def test_replicate_rate_limit_maps_to_429():
    provider = ReplicateVideoProvider(
        api_token="secret-token", model="owner/model",
        client_factory=mock_client(lambda request: httpx.Response(429, json={"detail": "rate limited"})),
    )
    with pytest.raises(MediaProviderError, match="429"):
        await provider.generate_clip({"prompt": "test scene"})


@pytest.mark.asyncio
async def test_replicate_requires_api_token():
    provider = ReplicateVideoProvider(api_token="", model="owner/model")
    with pytest.raises(MediaProviderError, match="token"):
        await provider.generate_clip({"prompt": "test scene"})


def test_replicate_settings_require_token_and_valid_model_shape():
    with pytest.raises(ValidationError, match="REPLICATE_API_TOKEN"):
        Settings(_env_file=None, video_provider="replicate", replicate_api_token=None)
    with pytest.raises(ValidationError, match="REPLICATE_VIDEO_MODEL"):
        Settings(_env_file=None, video_provider="replicate", replicate_api_token="x",
                 replicate_video_model="not-a-valid-slug")


def test_replicate_extra_input_parses_json_object_only():
    settings = Settings(_env_file=None, video_provider="replicate",
                         replicate_api_token="x",
                         replicate_video_extra_input_raw='{"duration": 5}')
    assert settings.replicate_video_extra_input == {"duration": 5}
    settings = Settings(_env_file=None, replicate_video_extra_input_raw="not json")
    assert settings.replicate_video_extra_input == {}
