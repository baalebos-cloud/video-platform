"""
Visual orchestrator — generates scene visuals via the configured image
or video provider (blueprint section 10).
"""
from app.ai.providers.base import ImageGenerationResult
from app.ai.providers.registry import select_provider


async def generate_scene_image(*, prompt: str, aspect_ratio: str = "9:16") -> ImageGenerationResult:
    provider = select_provider("image")
    full_prompt = (
        f"{prompt}\n[QUALITY] Sharp detail, coherent anatomy, realistic motion, clean composition.\n"
        f"[NEGATIVE CONSTRAINTS] No unwanted text, no malformed hands, no duplicate objects, "
        f"no inconsistent character changes, no distracting artifacts."
    )
    return await provider.generate(full_prompt, aspect_ratio=aspect_ratio)
