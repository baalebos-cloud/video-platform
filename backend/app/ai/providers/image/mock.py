"""
Mock image provider — renders a simple placeholder PNG carrying the prompt
text, so the storyboard/render pipeline has real image bytes to work with
without calling an external image-generation API.
"""
import io

from app.ai.providers.base import ImageGenerationResult, ImageProvider


def _generate_placeholder_png(text: str, size: tuple[int, int] = (1080, 1920)) -> bytes:
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", size, color=(20, 20, 30))
        draw = ImageDraw.Draw(img)
        wrapped = text[:200]
        draw.text((40, size[1] // 2 - 20), wrapped, fill=(230, 230, 230))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Pillow not installed — return a minimal 1x1 PNG so the pipeline still runs.
        return bytes.fromhex(
            "89504e470d0a1a0a0000000d494844520000000100000001080600000"
            "01f15c4890000000a49444154789c6360000002000155a2415d000000"
            "0049454e44ae426082"
        )


class MockImageProvider(ImageProvider):
    name = "mock"

    async def generate(self, prompt: str, *, aspect_ratio: str = "9:16") -> ImageGenerationResult:
        size = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
        return ImageGenerationResult(image_bytes=_generate_placeholder_png(prompt, size), format="png", provider=self.name)
