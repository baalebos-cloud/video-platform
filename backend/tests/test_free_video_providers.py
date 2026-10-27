"""Offline free-provider contract tests: never contact Gemini, Cloudflare, or Pixabay."""
import base64
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.ai.providers.llm.gemini import GeminiLLMProvider
from app.ai.providers.image.cloudflare import CloudflareImageProvider
from app.ai.providers.tts.cloudflare import CloudflareVoiceProvider
from app.ai.providers.openai_http import MediaProviderError
from app.config.settings import Settings
from app.services import render_service, stock_footage_service


def mock_client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_gemini_uses_secret_header_and_json_mode():
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": '{"title":"Video","scenes":[]}'}]}}]
        })
    provider = GeminiLLMProvider(api_key="a-key", client_factory=mock_client(handler))
    result = await provider.complete("director instructions", "the user topic", json_mode=True)
    assert result.provider == "gemini"
    assert json.loads(result.text)["title"] == "Video"
    assert received[0].headers["x-goog-api-key"] == "a-key"
    sent = json.loads(received[0].content)
    assert sent["generationConfig"]["responseMimeType"] == "application/json"
    assert "temperature" not in sent["generationConfig"]
    assert "topP" not in sent["generationConfig"]
    assert "topK" not in sent["generationConfig"]
    assert received[0].url.path.endswith("/models/gemini-3.5-flash-lite:generateContent")


@pytest.mark.asyncio
async def test_gemini_failures_do_not_fall_back_to_mock():
    provider = GeminiLLMProvider(
        api_key="secret-value",
        client_factory=mock_client(lambda request: httpx.Response(429, json={"error":"secret-value"})),
    )
    with pytest.raises(MediaProviderError, match="429") as error:
        await provider.complete("system", "topic", json_mode=True)
    assert "secret-value" not in str(error.value)


@pytest.mark.asyncio
async def test_cloudflare_flux_jpeg_is_converted_to_png():
    image = Image.new("RGB", (128, 128), (70, 50, 15))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True, "result": {
            "image": base64.b64encode(buf.getvalue()).decode(),
        }})
    provider = CloudflareImageProvider(
        account_id="0123456789abcdef0123456789abcdef", api_token="token",
        client_factory=mock_client(handler),
    )
    result = await provider.generate("A cinematic mountain", aspect_ratio="9:16")
    assert result.format == "png" and result.provider == "cloudflare"
    assert result.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert calls[0].headers["Authorization"] == "Bearer token"
    assert "/ai/run/@cf/black-forest-labs/flux-1-schnell" in calls[0].url.path


@pytest.mark.asyncio
async def test_cloudflare_melotts_normalizes_narration(monkeypatch):
    expected = (b"RIFF" + b"0" * 44, 1.5)
    monkeypatch.setattr("app.ai.providers.tts.cloudflare.mp3_to_wav", lambda data: expected)
    def handler(request):
        assert json.loads(request.content)["lang"] == "en"
        return httpx.Response(200, json={"result": {
            "audio": base64.b64encode(b"fake-mp3-bytes").decode(),
        }})
    provider = CloudflareVoiceProvider(
        account_id="0123456789abcdef0123456789abcdef", api_token="token", client_factory=mock_client(handler),
    )
    result = await provider.synthesize({"text": "Hello from the platform", "locale": "en-US"})
    assert result.format == "wav"
    assert result.duration_seconds == 1.5
    assert result.voice_id == "melotts-default"
    assert result.audio_bytes.startswith(b"RIFF")


def test_free_provider_settings_fail_closed_without_secrets():
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        Settings(_env_file=None, llm_provider="gemini", gemini_api_key=None)
    with pytest.raises(ValidationError, match="CLOUDFLARE"):
        Settings(_env_file=None, image_provider="cloudflare",
                 cloudflare_account_id=None, cloudflare_api_token=None)
    with pytest.raises(ValidationError, match="PIXABAY_API_KEY"):
        Settings(_env_file=None, stock_footage_enabled=True, pixabay_api_key=None)
    with pytest.raises(ValidationError, match="PIXABAY_VIDEO_API_URL"):
        Settings(_env_file=None, pixabay_video_api_url="http://localhost/")


def test_stock_search_filters_prompt_and_download_domain():
    assert stock_footage_service.search_terms("cinematic wide shot, beautiful futuristic city skyline") == "futuristic city skyline"
    assert stock_footage_service._safe_pixabay_cdn_url("https://cdn.pixabay.com/video/2026/abc.mp4")
    assert not stock_footage_service._safe_pixabay_cdn_url("https://evil.example/video.mp4")
    assert not stock_footage_service._safe_pixabay_cdn_url("http://cdn.pixabay.com/a.mp4")


@pytest.mark.asyncio
async def test_pixabay_fetch_caches_result_24_hours(monkeypatch):
    stored = {}
    class Cache:
        async def get(self, k):
            return stored.get(k)
        async def set(self, k, v, ex):
            assert ex == 86400
            stored[k] = v
    monkeypatch.setattr(stock_footage_service, "get_redis", lambda: Cache())
    monkeypatch.setattr(stock_footage_service, "get_settings", lambda: SimpleNamespace(
        stock_footage_enabled=True, pixabay_api_key="secret",
    ))
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "pixabay.com":
            return httpx.Response(200, json={"hits": [{
                "pageURL": "https://pixabay.com/videos/id-42/",
                "videos": {"medium": {"url": "https://cdn.pixabay.com/videos/x.mp4", "size": 12000}},
            }]})
        return httpx.Response(200, content=b"x" * 12000)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        stock_footage_service.httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    first = await stock_footage_service.find_stock_clip("futuristic city")
    second = await stock_footage_service.find_stock_clip("futuristic city")
    assert first and second and first.source_page_url.endswith("id-42/")
    assert sum("pixabay.com/api/videos" in url for url in seen) == 1


def test_stock_clip_ffmpeg_has_real_video_and_24fps(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(render_service, "_run", lambda cmd: commands.append(cmd))
    render_service.render_stock_clip(
        tmp_path / "input.mp4", tmp_path / "voice.wav", 5.5,
        tmp_path / "final.mp4", aspect_ratio="9:16",
    )
    args = commands[0]
    filters = args[args.index("-vf") + 1]
    assert "crop=1080:1920" in filters and "fps=24" in filters
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-c:a") + 1] == "aac"


def test_saved_stock_footage_is_reused_on_rerender():
    import uuid
    from app.db.models.asset import AssetType
    from app.workers.tasks.rerender_task import make_asset_manifest

    owner = uuid.uuid4()
    image_id, audio_id = uuid.uuid4(), uuid.uuid4()
    scene = SimpleNamespace(
        id=uuid.uuid4(), visual_asset_id=image_id, audio_asset_id=audio_id,
        duration_seconds=4.2, metadata_json={"stock_footage_key": "video/stock.mp4"},
    )
    assets = {
        image_id: SimpleNamespace(id=image_id, owner_id=owner, type=AssetType.IMAGE,
                                  storage_key="video/preview.png"),
        audio_id: SimpleNamespace(id=audio_id, owner_id=owner, type=AssetType.AUDIO,
                                  storage_key="video/speech.wav"),
    }
    manifest = make_asset_manifest([scene], assets, owner)
    assert manifest[str(scene.id)]["video_key"] == "video/stock.mp4"


def test_gemini_default_matches_current_free_tier_model():
    settings = Settings(_env_file=None)
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert GeminiLLMProvider(api_key="test").model == settings.gemini_model
