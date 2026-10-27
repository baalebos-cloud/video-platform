"""Cloudflare auth/preflight tests use HTTPX MockTransport; never make paid inference calls."""
import httpx
import pytest

from app.ai.providers.cloudflare_http import (
    CloudflareRequestError,
    run_cloudflare_model,
    verify_cloudflare_access,
)
from app.workers.tasks.pipeline_task import provider_failure_details


ACCOUNT = "0123456789abcdef0123456789abcdef"
MODEL = "@cf/myshell-ai/melotts"


def factory(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_preflight_uses_read_only_get_not_inference():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True, "result": []})

    status = await verify_cloudflare_access(
        account_id=" " + ACCOUNT + " ", api_token=" safe-token ",
        client_factory=factory(handler),
    )
    assert status == 200
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].headers["Authorization"] == "Bearer safe-token"
    assert calls[0].url.path.endswith("/ai/models/search")
    assert calls[0].url.params["search"] == "melotts"


@pytest.mark.asyncio
async def test_preflight_surfaces_http_unauthorized_status():
    status = await verify_cloudflare_access(
        account_id=ACCOUNT, api_token="invalid-but-well-formed-token",
        client_factory=factory(lambda request: httpx.Response(403)),
    )
    assert status == 403


@pytest.mark.asyncio
async def test_wrong_account_id_blocks_before_network():
    def no_requests(_request):
        raise AssertionError("Invalid account ID should never be sent")

    with pytest.raises(CloudflareRequestError, match="invalid_account_id"):
        await run_cloudflare_model(
            account_id="not-a-cloudflare-account-id",
            api_token="safe-token",
            model=MODEL, payload={"prompt": "Test", "lang": "en"},
            client_factory=factory(no_requests),
        )


@pytest.mark.asyncio
async def test_bad_authorization_header_blocks_before_network_and_has_safe_error():
    with pytest.raises(CloudflareRequestError) as e:
        await run_cloudflare_model(
            account_id=ACCOUNT, api_token="token\nAuthorization: unsafe",
            model=MODEL, payload={"prompt": "Test", "lang": "en"},
            client_factory=factory(lambda request: httpx.Response(200)),
        )
    assert e.value.reason == "invalid_token_format"
    code, message, status = provider_failure_details("generating_assets", e.value)
    assert code == "media_cloudflare_token"
    assert "unsafe" not in message
    assert status is None


@pytest.mark.asyncio
async def test_request_error_retains_only_safe_classification():
    def fail(request):
        raise httpx.ConnectError("private transport details", request=request)

    with pytest.raises(CloudflareRequestError) as e:
        await run_cloudflare_model(
            account_id=ACCOUNT, api_token="secret-token", model=MODEL,
            payload={"prompt": "Speech", "lang": "en"},
            client_factory=factory(fail),
        )
    assert e.value.reason == "connection_failed"
    code, message, status = provider_failure_details("generating_assets", e.value)
    assert code == "media_cloudflare_connection"
    assert status is None
    assert "secret-token" not in str(e.value) + message
    assert "private transport" not in str(e.value) + message


@pytest.mark.asyncio
async def test_api_rejects_401_without_exposing_body():
    with pytest.raises(Exception, match="401") as e:
        await run_cloudflare_model(
            account_id=ACCOUNT, api_token="not-valid-token", model=MODEL,
            payload={"prompt": "Speech", "lang": "en"},
            client_factory=factory(lambda request: httpx.Response(
                401, json={"errors": ["never log this secret!"]},
            )),
        )
    assert "secret!" not in str(e.value)


@pytest.mark.asyncio
async def test_whitespace_on_railway_variable_is_trimmed():
    def handle(req):
        assert req.headers["Authorization"] == "Bearer good-token"
        return httpx.Response(200, json={"result": {"audio": "bXAz"}})

    result = await run_cloudflare_model(
        account_id=" " + ACCOUNT + " ", api_token=" good-token\n",
        model=" " + MODEL + " ",
        payload={"prompt": "Speech", "lang": "en"},
        client_factory=factory(handle),
    )
    assert result.status_code == 200
