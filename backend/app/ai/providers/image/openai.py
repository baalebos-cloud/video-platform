"""OpenAI image generation adapter; returns validated PNG still images."""
import base64
import binascii
import io
from collections.abc import Callable

import httpx
from PIL import Image, UnidentifiedImageError

from app.ai.providers.base import ImageGenerationResult, ImageProvider
from app.ai.providers.openai_http import MediaProviderError, post_openai_media


IMAGE_SIZES = {"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}
MAX_PNG_SIZE = 25 * 1024 * 1024
MAX_BASE64_CHARS = ((MAX_PNG_SIZE + 2) // 3) * 4


class OpenAIImageProvider(ImageProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-image-1.5",
        quality: str = "medium",
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.quality = quality
        self.client_factory = client_factory or httpx.AsyncClient
        if quality not in {"low", "medium", "high"}:
            raise ValueError("Invalid image quality")

    async def generate(self, prompt: str, *, aspect_ratio: str = "9:16") -> ImageGenerationResult:
        if aspect_ratio not in IMAGE_SIZES:
            raise ValueError("Unsupported image aspect ratio")
        if not prompt.strip() or len(prompt) > 12000:
            raise ValueError("Image prompt cannot be empty or exceed 12000 characters")

        response = await post_openai_media(
            api_key=self.api_key, endpoint="/images/generations",
            payload={
                "model": self.model, "prompt": prompt,
                "n": 1, "size": IMAGE_SIZES[aspect_ratio],
                "quality": self.quality, "output_format": "png",
            },
            client_factory=self.client_factory, timeout=180.0,
        )
        try:
            document = response.json()
            encoded = document["data"][0]["b64_json"]
            if not isinstance(encoded, str) or len(encoded) > MAX_BASE64_CHARS:
                raise ValueError("Image too large or missing")
            data = base64.b64decode(encoded, validate=True)
            if not 8 <= len(data) <= MAX_PNG_SIZE or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Invalid PNG")
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or image.width < 64 or image.height < 64:
                    raise ValueError("Invalid image dimensions")
                image.verify()
        except (ValueError, KeyError, IndexError, TypeError, binascii.Error, UnidentifiedImageError, OSError):
            raise MediaProviderError("OpenAI image response did not contain a valid PNG") from None

        return ImageGenerationResult(image_bytes=data, format="png", provider=self.name)
