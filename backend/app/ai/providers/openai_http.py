"""Bounded OpenAI media HTTP helper: never expose credentials or raw provider bodies."""
from collections.abc import Callable

import httpx

OPENAI_API_BASE = "https://api.openai.com/v1"


class MediaProviderError(RuntimeError):
    """Sanitized failure, suitable for recording on a generation job."""


async def post_openai_media(
    *,
    api_key: str,
    endpoint: str,
    payload: dict,
    client_factory: Callable[[], httpx.AsyncClient],
    timeout: float = 180.0,
) -> httpx.Response:
    if not api_key or not api_key.strip():
        raise MediaProviderError("OpenAI API key is not configured")
    try:
        async with client_factory() as client:
            response = await client.post(
                f"{OPENAI_API_BASE}{endpoint}",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=timeout,
            )
    except httpx.RequestError:
        # Never log exception bodies/authorization headers, or accidentally
        # convert a paid-provider failure into synthetic 'successful' output.
        raise MediaProviderError("OpenAI media request failed (network or timeout)") from None

    if not 200 <= response.status_code < 300:
        if response.status_code == 429:
            raise MediaProviderError("OpenAI media provider rate limit or quota reached (HTTP 429)")
        raise MediaProviderError(f"OpenAI media provider rejected the request (HTTP {response.status_code})")
    return response
