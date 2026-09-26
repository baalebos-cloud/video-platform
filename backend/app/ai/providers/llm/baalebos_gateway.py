"""
Adapter for "baalebos-ai" — a personal n8n-hosted LLM gateway that fans a
single prompt out across multiple upstream providers and returns
whichever responds first (gateway.baalebo.xyz).

The gateway's contract is intentionally minimal (a single "prompt" string
in, raw response back, `x-api-key` auth), which is a lot looser than what
the AI Video Director needs (a system prompt + a strict JSON response).
This adapter bridges that gap rather than assuming the gateway can meet
the stricter contract on its own:

  - Embeds the system instructions directly into the prompt text, since
    the gateway has no separate system-message field.
  - Extracts the first valid JSON object from the response leniently —
    unwrapping markdown code fences and ignoring surrounding prose —
    since whichever of the 9 upstream providers answers can't be
    guaranteed to obey "return only JSON" as strictly as a purpose-built
    structured-output API would.
  - Falls back to the built-in mock provider automatically if the
    gateway call fails outright (network error, non-2xx, timeout) or its
    response can't be parsed into valid JSON — so a flaky or
    misbehaving upstream degrades a generation job's quality instead of
    failing it outright.
"""
import json
import re

import httpx

from app.ai.providers.base import LLMProvider, LLMResponse
from app.ai.providers.llm.mock import MockLLMProvider
from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger("ai.providers.llm.baalebos_gateway")

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_ENVELOPE_KEYS = ("output", "response", "text", "message", "result", "answer")


class BaalebosGatewayLLMProvider(LLMProvider):
    name = "baalebos_ai"

    def __init__(self) -> None:
        self._fallback = MockLLMProvider()

    async def complete(self, system_prompt: str, user_prompt: str, *, json_mode: bool = False) -> LLMResponse:
        settings = get_settings()
        if not settings.llm_gateway_url:
            logger.warning("llm_gateway.not_configured", fallback="mock")
            return await self._fallback.complete(system_prompt, user_prompt, json_mode=json_mode)

        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        if json_mode:
            combined_prompt += (
                "\n\nRespond with ONLY a single valid JSON object. "
                "No markdown code fences, no explanation, no text before or after the JSON."
            )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {"x-api-key": settings.llm_api_key} if settings.llm_api_key else {}
                response = await client.post(
                    settings.llm_gateway_url, json={"prompt": combined_prompt}, headers=headers
                )
                response.raise_for_status()
                raw_text = response.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning("llm_gateway.request_failed", error=str(exc), fallback="mock")
            return await self._fallback.complete(system_prompt, user_prompt, json_mode=json_mode)

        text = self._extract_text(raw_text)

        if json_mode:
            extracted = self._extract_json(text)
            if extracted is None:
                logger.warning("llm_gateway.invalid_json_response", raw=text[:500], fallback="mock")
                return await self._fallback.complete(system_prompt, user_prompt, json_mode=json_mode)
            text = extracted

        return LLMResponse(
            text=text, raw={"gateway_raw_response": raw_text}, model="baalebos-ai-gateway", provider=self.name
        )

    @staticmethod
    def _extract_text(raw_text: str) -> str:
        """The gateway may return plain text or a JSON envelope like {"output": "..."}."""
        stripped = raw_text.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        if isinstance(parsed, str):
            return parsed
        if isinstance(parsed, dict):
            for key in _ENVELOPE_KEYS:
                value = parsed.get(key)
                if isinstance(value, str):
                    return value
        return stripped

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Pulls the first {...} block out of arbitrary surrounding text/markdown."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        match = _JSON_OBJECT_RE.search(cleaned)
        if not match:
            return None
        candidate = match.group(0)
        try:
            json.loads(candidate)  # confirm it actually parses before trusting it
        except json.JSONDecodeError:
            return None
        return candidate
