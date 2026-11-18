"""Offline tests for chunked publish uploads and the llm_gateway_url SSRF guard.
Never contacts YouTube/TikTok/the gateway — storage and HTTP are mocked throughout."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.ai.providers.llm.baalebos_gateway import BaalebosGatewayLLMProvider
from app.config.settings import Settings
from app.services import publishing_service


def fake_storage(monkeypatch, total_size: int):
    """Serves `total_size` bytes of deterministic content via ranged reads,
    so chunk boundaries and counts can be asserted precisely."""
    content = bytes((i % 251) for i in range(total_size))

    def fake_size(storage_key):
        return total_size

    def fake_range(storage_key, start, end_inclusive):
        return content[start:end_inclusive + 1]

    monkeypatch.setattr(publishing_service.storage_service, "get_object_size", fake_size)
    monkeypatch.setattr(publishing_service.storage_service, "get_object_range_bytes", fake_range)
    return content


@pytest.mark.asyncio
async def test_youtube_upload_streams_in_8mb_chunks_not_whole_file(monkeypatch):
    total_size = publishing_service.CHUNK_SIZE * 2 + 1024  # 3 chunks, last one small
    content = fake_storage(monkeypatch, total_size)

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, headers={"location": "https://www.googleapis.com/upload/resume/abc"})
        # PUT chunk
        is_last = request.headers["Content-Range"].endswith(f"/{total_size}") and \
            int(request.headers["Content-Range"].split("-")[1].split("/")[0]) + 1 == total_size
        if is_last:
            return httpx.Response(200, json={"id": "yt-video-123"})
        return httpx.Response(308)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    with patch("httpx.AsyncClient", lambda **kw: original_client(transport=transport, **kw)):
        result = await publishing_service.YouTubePublishingProvider().publish(
            "video/final.mp4", {"title": "Test"}, access_token="tok",
        )

    assert result == {"external_post_id": "yt-video-123", "status": "published"}
    put_requests = [r for r in requests if r.method == "PUT"]
    assert len(put_requests) == 3
    # No single request body exceeds one chunk — the whole file was never materialized at once.
    assert all(len(r.content) <= publishing_service.CHUNK_SIZE for r in put_requests)
    assert sum(len(r.content) for r in put_requests) == total_size
    # Content-Range headers partition the file contiguously with no gaps/overlaps.
    ranges = []
    for r in put_requests:
        spec = r.headers["Content-Range"]  # "bytes start-end/total"
        start, rest = spec.removeprefix("bytes ").split("-")
        end = rest.split("/")[0]
        ranges.append((int(start), int(end)))
    ranges.sort()
    assert ranges[0][0] == 0 and ranges[-1][1] == total_size - 1
    for (s1, e1), (s2, e2) in zip(ranges, ranges[1:]):
        assert e1 + 1 == s2


@pytest.mark.asyncio
async def test_tiktok_upload_sends_correct_chunk_count(monkeypatch):
    total_size = publishing_service.CHUNK_SIZE + 500  # 2 chunks
    fake_storage(monkeypatch, total_size)
    puts = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "init" in str(request.url):
            body = json.loads(request.content)
            assert body["source_info"]["total_chunk_count"] == 2
            return httpx.Response(200, json={
                "data": {"upload_url": "https://open-upload.tiktokapis.com/upload",
                          "publish_id": "pub-1"},
            })
        puts.append(request)
        return httpx.Response(206) if len(puts) == 1 else httpx.Response(201)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    with patch("httpx.AsyncClient", lambda **kw: original_client(transport=transport, **kw)):
        result = await publishing_service.TikTokInboxPublishingProvider().publish(
            "video/final.mp4", {"title": "Test"}, access_token="tok",
        )
    assert result["external_post_id"] == "pub-1"
    assert len(puts) == 2


def test_llm_gateway_url_is_safe_rejects_internal_and_non_https():
    assert Settings(_env_file=None, llm_gateway_url="https://gateway.baalebo.xyz/webhook/x").llm_gateway_url_is_safe
    assert not Settings(_env_file=None, llm_gateway_url="http://gateway.baalebo.xyz/x").llm_gateway_url_is_safe
    assert not Settings(_env_file=None, llm_gateway_url="https://localhost/x").llm_gateway_url_is_safe
    assert not Settings(_env_file=None, llm_gateway_url="https://169.254.169.254/latest/meta-data").llm_gateway_url_is_safe
    assert not Settings(_env_file=None, llm_gateway_url=None).llm_gateway_url_is_safe


@pytest.mark.asyncio
async def test_gateway_provider_falls_back_to_mock_on_unsafe_url(monkeypatch):
    monkeypatch.setattr(
        "app.ai.providers.llm.baalebos_gateway.get_settings",
        lambda: Settings(_env_file=None, llm_gateway_url="http://169.254.169.254/latest/meta-data"),
    )
    called = AsyncMock()
    with patch("httpx.AsyncClient", side_effect=AssertionError("must not call the network for an unsafe URL")):
        provider = BaalebosGatewayLLMProvider()
        result = await provider.complete("system", "topic", json_mode=True)
    assert result.provider == "mock"
