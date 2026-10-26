"""Cloudflare FLUX image adapter; normalized to PNG for the existing editor."""
import base64
import binascii
import io
from collections.abc import Callable

import httpx
from PIL import Image, UnidentifiedImageError

from app.ai.providers.base import ImageGenerationResult, ImageProvider
from app.ai.providers.cloudflare_http import run_cloudflare_model
from app.ai.providers.openai_http import MediaProviderError


class CloudflareImageProvider(ImageProvider):
    name = "cloudflare"

    def __init__(self, *, account_id: str, api_token: str,
                 model: str = "@cf/black-forest-labs/flux-1-schnell",
                 client_factory: Callable[[], httpx.AsyncClient] | None = None):
        self.account_id, self.api_token, self.model = account_id, api_token, model
        self.client_factory = client_factory or httpx.AsyncClient

    async def generate(self, prompt: str, *, aspect_ratio: str = "9:16") -> ImageGenerationResult:
        if aspect_ratio not in ("9:16", "16:9", "1:1"):
            raise ValueError("Unsupported aspect ratio")
        if not prompt.strip():
            raise ValueError("Image prompt is required")
        response = await run_cloudflare_model(
            account_id=self.account_id, api_token=self.api_token, model=self.model,
            payload={"prompt": prompt[:2000], "steps": 8},
            client_factory=self.client_factory,
        )
        try:
            document = response.json()
            if document.get("success") is False:
                raise ValueError("Unsuccessful inference")
            encoded = document["result"]["image"]
            if not isinstance(encoded, str) or len(encoded) > 30_000_000:
                raise ValueError("Invalid image payload")
            raw = base64.b64decode(encoded, validate=True)
            if len(raw) > 20 * 1024 * 1024:
                raise ValueError("Image too large")
            with Image.open(io.BytesIO(raw)) as image:
                if image.width < 64 or image.height < 64:
                    raise ValueError("Image too small")
                out = io.BytesIO()
                image.convert("RGB").save(out, format="PNG")
            return ImageGenerationResult(image_bytes=out.getvalue(), format="png", provider=self.name)
        except (KeyError, TypeError, ValueError, binascii.Error, UnidentifiedImageError, OSError):
            raise MediaProviderError("Cloudflare returned an invalid image") from None
