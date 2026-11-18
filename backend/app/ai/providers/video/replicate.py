"""
Replicate-backed generative VideoProvider.

Replicate (replicate.com) hosts most of the generative-video models people
mean when they ask for "real" AI video — Kling, Luma Ray, Runway, Google
Veo, Seedance, Hunyuan, etc. — behind one account and one API token, rather
than a separate signup/key/billing relationship per vendor. That makes it
the practical default for a small team: pick one model slug, generate real
motion clips (the gap the mock video provider deliberately leaves open),
and swap the model later without touching this adapter's shape.

IMPORTANT — model input schemas are not uniform. Every model on Replicate
declares its own input fields (a "prompt" field almost always exists; an
image-conditioning field is named "image", "start_image", "image_url" or
similar depending on the model, and not every model accepts one at all).
`REPLICATE_VIDEO_PROMPT_FIELD` / `REPLICATE_VIDEO_IMAGE_FIELD` /
`REPLICATE_VIDEO_EXTRA_INPUT` (see .env.example) let the operator match
whichever model they choose without editing this file — check the model's
"API" tab on replicate.com for its exact input schema before going live.
"""
import asyncio
import base64
import time
from collections.abc import Callable

import httpx

from app.ai.providers.base import VideoGenerationResult, VideoProvider
from app.ai.providers.openai_http import MediaProviderError
from app.config.logging import get_logger

REPLICATE_API_BASE = "https://api.replicate.com/v1"
logger = get_logger("ai.providers.video.replicate")


class ReplicateVideoProvider(VideoProvider):
    name = "replicate"

    def __init__(
        self,
        *,
        api_token: str,
        model: str,
        prompt_field: str = "prompt",
        image_field: str = "image",
        extra_input: dict | None = None,
        poll_timeout_seconds: float = 240.0,
        poll_interval_seconds: float = 3.0,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ):
        self.api_token = api_token
        self.model = model
        self.prompt_field = prompt_field
        self.image_field = image_field
        self.extra_input = extra_input or {}
        self.poll_timeout_seconds = poll_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=60.0))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Prefer": "wait=1",  # ask Replicate to hold the request briefly for fast models; polling still runs
        }

    def _build_input(self, scene_spec: dict) -> dict:
        prompt_parts = [str(scene_spec.get("prompt") or "").strip()]
        camera = scene_spec.get("camera")
        lighting = scene_spec.get("lighting")
        if camera:
            prompt_parts.append(f"Camera: {camera}.")
        if lighting:
            prompt_parts.append(f"Lighting: {lighting}.")
        full_prompt = " ".join(part for part in prompt_parts if part).strip()
        if not full_prompt:
            raise MediaProviderError("Replicate video request is missing a visual prompt")

        payload: dict = {self.prompt_field: full_prompt[:2000], **self.extra_input}

        image_bytes = scene_spec.get("reference_image_bytes")
        if image_bytes and self.image_field:
            image_format = scene_spec.get("reference_image_format", "png")
            encoded = base64.b64encode(image_bytes).decode("ascii")
            payload[self.image_field] = f"data:image/{image_format};base64,{encoded}"
        return payload

    async def generate_clip(self, scene_spec: dict) -> VideoGenerationResult:
        if not self.api_token or not self.api_token.strip():
            raise MediaProviderError("Replicate API token is not configured")
        if not self.model or "/" not in self.model:
            raise MediaProviderError("Replicate video model must be set as 'owner/model'")

        requested_duration = float(scene_spec.get("duration_seconds") or 5.0)
        input_payload = self._build_input(scene_spec)

        async with self.client_factory() as client:
            try:
                response = await client.post(
                    f"{REPLICATE_API_BASE}/models/{self.model}/predictions",
                    headers=self._headers(),
                    json={"input": input_payload},
                )
            except httpx.RequestError:
                raise MediaProviderError("Replicate video request failed (network or timeout)") from None

            if response.status_code == 429:
                raise MediaProviderError("Replicate video provider rate limit or quota reached (HTTP 429)")
            if not 200 <= response.status_code < 300:
                raise MediaProviderError(f"Replicate video provider rejected the request (HTTP {response.status_code})")

            prediction = response.json()
            output_url = await self._poll_until_done(client, prediction)

            try:
                media = await client.get(output_url)
            except httpx.RequestError:
                raise MediaProviderError("Replicate video download failed (network or timeout)") from None
            if not 200 <= media.status_code < 300:
                raise MediaProviderError(f"Replicate video download rejected (HTTP {media.status_code})")
            video_bytes = media.content

        if not video_bytes:
            raise MediaProviderError("Replicate returned an empty video clip")
        return VideoGenerationResult(
            video_bytes=video_bytes, format="mp4",
            duration_seconds=requested_duration, provider=self.name,
        )

    async def _poll_until_done(self, client: httpx.AsyncClient, prediction: dict) -> str:
        get_url = (prediction.get("urls") or {}).get("get")
        status = prediction.get("status")
        # Wall-clock deadline, not a sleep-only counter: a slow-but-successful
        # status request (up to the client's own 60s timeout) must count
        # against the budget too, or REPLICATE_VIDEO_POLL_TIMEOUT_SECONDS
        # stops bounding real latency and a hung provider can ride the
        # worker's much larger job timeout instead of degrading gracefully.
        deadline = time.monotonic() + self.poll_timeout_seconds
        while status not in {"succeeded", "failed", "canceled"}:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not get_url:
                raise MediaProviderError("Replicate video generation timed out")
            await asyncio.sleep(min(self.poll_interval_seconds, remaining))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MediaProviderError("Replicate video generation timed out")
            try:
                poll = await client.get(get_url, headers=self._headers(), timeout=max(1.0, remaining))
            except httpx.RequestError:
                raise MediaProviderError("Replicate video status check failed (network or timeout)") from None
            if not 200 <= poll.status_code < 300:
                raise MediaProviderError(f"Replicate video status check rejected (HTTP {poll.status_code})")
            prediction = poll.json()
            status = prediction.get("status")

        if status != "succeeded":
            # Replicate's own error text may describe the model's licensing/
            # content filters; never forward it verbatim to end users.
            logger.error("replicate.video_generation_failed", status=status)
            raise MediaProviderError(f"Replicate video generation did not succeed (status={status})")

        output = prediction.get("output")
        if isinstance(output, list) and output:
            output = output[-1]
        if not isinstance(output, str) or not output.startswith("https://"):
            raise MediaProviderError("Replicate returned no downloadable video output")
        return output
