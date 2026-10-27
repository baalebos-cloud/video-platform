"""Provider failure diagnostics are actionable and never forward provider response bodies."""
import pytest

from app.ai.providers.openai_http import MediaProviderError
from app.workers.tasks.pipeline_task import provider_failure_details


@pytest.mark.parametrize("http_status,code", [
    (400, "planning_request"),
    (401, "planning_credentials"),
    (403, "planning_credentials"),
    (404, "planning_model"),
    (429, "planning_quota"),
    (500, "planning_unavailable"),
    (503, "planning_unavailable"),
])
def test_gemini_provider_failure_is_classified(http_status, code):
    error = MediaProviderError(f"Gemini planning rejected request (HTTP {http_status})")
    result_code, message, provider_http_status = provider_failure_details("planning", error)
    assert result_code == code
    assert provider_http_status == http_status
    assert "Gemini" in message
    assert "HTTP" in message


def test_media_failures_do_not_get_mislabeled_as_planning():
    code, message, http_status = provider_failure_details(
        "generating_assets", MediaProviderError("Cloudflare AI rejected request (HTTP 429)")
    )
    assert code == "media_quota"
    assert http_status == 429
    assert "media" in message.lower()


def test_unrecognized_provider_error_never_exposes_secrets_or_unknown_response():
    code, message, http_status = provider_failure_details(
        "planning", MediaProviderError("secret-key=do-not-echo provider body")
    )
    assert code == "planning_unavailable"
    assert http_status is None
    assert "do-not-echo" not in message
    assert "secret-key" not in message


def test_network_error_stays_safe():
    code, message, http_status = provider_failure_details(
        "planning", MediaProviderError("Gemini planning request unavailable")
    )
    assert code == "planning_unavailable"
    assert http_status is None
    assert "worker logs" in message
