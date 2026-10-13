"""YouTube OAuth error handling never leaks provider tokens or error bodies."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from app.services import publishing_oauth as oauth


def settings():
    return SimpleNamespace(
        youtube_client_id="test-client", youtube_client_secret="test-secret",
        tiktok_client_id="other", tiktok_client_secret="other",
        publishing_token_encryption_key="placeholder",
        api_url="https://video-platform-jtng.onrender.com",
        app_env="production",
    )


@pytest.mark.asyncio
async def test_youtube_authorize_requests_upload_and_channel_lookup_scopes():
    db = AsyncMock()
    with patch.object(oauth, "get_settings", return_value=settings()):
        url = await oauth.authorize(db, "youtube", uuid.uuid4())
    parsed = parse_qs(urlparse(url).query)
    assert "https://www.googleapis.com/auth/youtube.upload" in parsed["scope"][0].split()
    assert "https://www.googleapis.com/auth/youtube.readonly" in parsed["scope"][0].split()
    assert parsed["redirect_uri"] == [
        "https://video-platform-jtng.onrender.com/api/v1/publishing/oauth/youtube/callback"
    ]
    assert "test-secret" not in url
    assert len(db.add.call_args.args[0].state_hash) == 64


class FakeHttp:
    def __init__(self, channel_status=403, token_status=200):
        self.channel_status = channel_status
        self.token_status = token_status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, url, data):
        request = httpx.Request("POST", url)
        if self.token_status != 200:
            return httpx.Response(self.token_status, request=request, text="SENSITIVE PROVIDER ERROR")
        return httpx.Response(200, request=request, json={
            "access_token":"SECRET-ACCESS",
            "refresh_token":"SECRET-REFRESH",
            "expires_in":3600,
        })

    async def get(self, url, params, headers):
        assert "SECRET-ACCESS" in headers["Authorization"]
        return httpx.Response(
            self.channel_status, request=httpx.Request("GET", url),
            json={"items":[{"id":"UC0123456789"}]} if self.channel_status == 200
                 else {"error":{"message":"SENSITIVE PROVIDER ERROR"}},
        )


def grant():
    return SimpleNamespace(
        user_id=uuid.uuid4(), platform="youtube",
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_youtube_channel_403_is_actionable_without_secret_leak():
    db=AsyncMock()
    db.scalar.return_value=grant()
    with patch.object(oauth,"get_settings",return_value=settings()), \
         patch.object(oauth.httpx,"AsyncClient",return_value=FakeHttp()):
        with pytest.raises(HTTPException) as info:
            await oauth.complete_authorization(db,"youtube","state-value","oauth-code")
    assert info.value.status_code == 502
    assert "YouTube Data API v3" in info.value.detail
    assert "SECRET" not in info.value.detail


@pytest.mark.asyncio
async def test_google_token_exchange_errors_are_masked():
    db=AsyncMock()
    db.scalar.return_value=grant()
    with patch.object(oauth,"get_settings",return_value=settings()), \
         patch.object(oauth.httpx,"AsyncClient",return_value=FakeHttp(token_status=400)):
        with pytest.raises(HTTPException) as info:
            await oauth.complete_authorization(db,"youtube","state-value","oauth-code")
    assert info.value.status_code == 502
    assert "authorization exchange" in info.value.detail
    assert "SENSITIVE" not in info.value.detail


@pytest.mark.asyncio
async def test_missing_channel_returns_client_guidance():
    db=AsyncMock()
    db.scalar.return_value=grant()
    class EmptyChannel(FakeHttp):
        async def get(self, url, params, headers):
            return httpx.Response(200, request=httpx.Request("GET", url), json={"items":[]})
    with patch.object(oauth,"get_settings",return_value=settings()), \
         patch.object(oauth.httpx,"AsyncClient",return_value=EmptyChannel()):
        with pytest.raises(HTTPException) as info:
            await oauth.complete_authorization(db,"youtube","state-value","oauth-code")
    assert info.value.status_code == 400
    assert "No YouTube channel" in info.value.detail
