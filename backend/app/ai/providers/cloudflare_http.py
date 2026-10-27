"""Restricted Workers AI REST client with safe, stage-specific diagnostics.

The previous helper mapped all httpx.RequestError failures to an opaque
'network or timeout' status. A malformed Authorization header, an invalid
account ID and a genuine DNS outage therefore looked identical to users.
Do not log API credentials, raw URLs (account ID embedded) or provider bodies.
"""
import re
from collections.abc import Callable

import httpx

from app.ai.providers.openai_http import MediaProviderError
from app.config.logging import get_logger

logger = get_logger("providers.cloudflare")
_ACCOUNT_ID = re.compile(r"^[a-fA-F0-9]{32}$")


class CloudflareRequestError(MediaProviderError):
    """Sanitized Workers AI failure; reason is an internal fixed enum."""

    def __init__(self, reason: str):
        if reason not in {
            "invalid_account_id", "invalid_token_format", "missing_credentials",
            "invalid_model", "invalid_client_request", "connection_failed",
            "request_timeout",
        }:
            raise ValueError("Unknown Cloudflare failure classification")
        self.reason = reason
        super().__init__(f"Cloudflare request failed: {reason}")


async def run_cloudflare_model(
    *, account_id: str, api_token: str, model: str, payload: dict,
    client_factory: Callable[[], httpx.AsyncClient],
) -> httpx.Response:
    # Normalize whitespace introduced by Railway variable entry, but reject
    # control characters or malformed authorization credentials.
    clean_account = (account_id or "").strip()
    clean_token = (api_token or "").strip()
    clean_model = (model or "").strip()

    if not clean_account or not clean_token:
        raise CloudflareRequestError("missing_credentials")
    if not _ACCOUNT_ID.fullmatch(clean_account):
        raise CloudflareRequestError("invalid_account_id")
    if not clean_token.isascii() or any(ch.isspace() for ch in clean_token) or ":" in clean_token:
        raise CloudflareRequestError("invalid_token_format")
    if not clean_model.startswith("@cf/") or ".." in clean_model or "?" in clean_model or "#" in clean_model:
        raise CloudflareRequestError("invalid_model")

    # Fixed Cloudflare host: do not accept arbitrary URLs from variables.
    url = f"https://api.cloudflare.com/client/v4/accounts/{clean_account}/ai/run/{clean_model}"
    logger.info("cloudflare.request_started", model=clean_model)
    try:
        async with client_factory() as client:
            response = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {clean_token}", "Content-Type": "application/json"},
                timeout=180,
            )
    except httpx.TimeoutException:
        logger.error("cloudflare.request_timeout", model=clean_model)
        raise CloudflareRequestError("request_timeout") from None
    except (httpx.LocalProtocolError, httpx.InvalidURL, httpx.UnsupportedProtocol):
        logger.error("cloudflare.invalid_client_request", model=clean_model)
        raise CloudflareRequestError("invalid_client_request") from None
    except httpx.RequestError as exc:
        logger.error("cloudflare.connection_failed", model=clean_model, failure_type=type(exc).__name__)
        raise CloudflareRequestError("connection_failed") from None

    logger.info("cloudflare.request_completed", model=clean_model, http_status=response.status_code)
    if not 200 <= response.status_code < 300:
        raise MediaProviderError(f"Cloudflare AI rejected request (HTTP {response.status_code})")
    if len(response.content) > 35 * 1024 * 1024:
        raise MediaProviderError("Cloudflare AI response exceeded size limit")
    return response
