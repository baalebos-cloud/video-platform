"""Gemini text-only director: fail closed on provider errors, no paid fallback."""
import json
import re
from collections.abc import Callable

import httpx

from app.ai.providers.base import LLMProvider, LLMResponse
from app.ai.providers.openai_http import MediaProviderError
from app.ai.schemas.video_plan import GEMINI_VIDEO_PLAN_SCHEMA

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,100}$")


class GeminiLLMProvider(LLMProvider):
    name = "gemini"

    def __init__(self, *, api_key: str, model: str = "gemini-3.5-flash-lite",
                 client_factory: Callable[[], httpx.AsyncClient] | None = None):
        if not api_key or not api_key.strip():
            raise ValueError("GEMINI_API_KEY is required")
        if not _MODEL_ID.fullmatch(model):
            raise ValueError("Invalid Gemini model identifier")
        self.api_key = api_key
        self.model = model
        self.client_factory = client_factory or httpx.AsyncClient

    async def complete(self, system_prompt: str, user_prompt: str,
                       *, json_mode: bool = False) -> LLMResponse:
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                **({
                    "responseMimeType": "application/json",
                    "responseJsonSchema": GEMINI_VIDEO_PLAN_SCHEMA,
                } if json_mode else {}),
            },
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            async with self.client_factory() as client:
                response = await client.post(
                    url, json=payload,
                    headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                    timeout=90,
                )
        except httpx.RequestError:
            raise MediaProviderError("Gemini planning request unavailable") from None
        if not 200 <= response.status_code < 300:
            raise MediaProviderError(f"Gemini planning rejected request (HTTP {response.status_code})")
        try:
            document = response.json()
            candidates = document["candidates"]
            parts = candidates[0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
            if not text.strip() or len(text) > 150000:
                raise ValueError("Empty response")
            if json_mode:
                json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise MediaProviderError("Gemini planning returned invalid or blocked content") from None
        return LLMResponse(text=text, raw={}, model=self.model, provider=self.name)
