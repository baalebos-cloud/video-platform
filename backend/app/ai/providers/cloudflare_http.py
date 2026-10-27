"""Restricted REST client for Cloudflare Workers AI; never log secret headers or bodies."""
from collections.abc import Callable

import httpx

from app.ai.providers.openai_http import MediaProviderError


async def run_cloudflare_model(
    *, account_id: str, api_token: str, model: str, payload: dict,
    client_factory: Callable[[], httpx.AsyncClient],
) -> httpx.Response:
    if not account_id or not api_token:
        raise MediaProviderError("Cloudflare account ID and API token are required")
    if not model.startswith("@cf/") or ".." in model or "?" in model or "#" in model:
        raise MediaProviderError("Unsupported Cloudflare model name")
    # Fixed Cloudflare domain. Do not accept a caller-provided API origin.
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    try:
        async with client_factory() as client:
            response = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                timeout=180,
            )
    except httpx.RequestError:
        raise MediaProviderError("Cloudflare AI request failed (network or timeout)") from None
    if not 200 <= response.status_code < 300:
        raise MediaProviderError(f"Cloudflare AI rejected request (HTTP {response.status_code})")
    if len(response.content) > 35 * 1024 * 1024:
        raise MediaProviderError("Cloudflare AI response exceeded size limit")
    return response
