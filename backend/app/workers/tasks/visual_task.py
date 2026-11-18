"""Generate real stock footage where available; otherwise use the configured
image AI, and — when a real VideoProvider is configured — animate that
still into an actual AI-generated motion clip instead of a static photo."""
import asyncio

from app.ai.providers.registry import select_provider
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.db.models.scene import Scene
from app.db.models.video import Video
from app.services import provider_guard, stock_footage_service, storage_service, visual_service

logger = get_logger("workers.visual")


async def run(video: Video, scene: Scene) -> dict:
    """Return a persisted scene preview and optionally a motion clip key."""
    stock = await stock_footage_service.find_stock_clip(scene.visual_prompt)
    if stock is not None:
        try:
            preview = await asyncio.to_thread(stock_footage_service.frame_from_video, stock.video_bytes)
        except (OSError, ValueError, RuntimeError):
            stock = None
        else:
            video_key, _, _ = await asyncio.to_thread(
                storage_service.put_object, stock.video_bytes,
                content_type="video/mp4", prefix=f"videos/{video.id}/stock",
            )
            image_key, _, _ = await asyncio.to_thread(
                storage_service.put_object, preview,
                content_type="image/png", prefix=f"videos/{video.id}/images",
            )
            return {"image_key": image_key, "video_key": video_key,
                    "video_key_source": "stock_footage_key",
                    "provider": "pixabay", "source_url": stock.source_page_url}

    result = await visual_service.generate_scene_image(
        prompt=scene.visual_prompt, aspect_ratio=video.aspect_ratio,
    )
    image_key, _, _ = await asyncio.to_thread(
        storage_service.put_object, result.image_bytes,
        content_type=f"image/{result.format}", prefix=f"videos/{video.id}/images",
    )

    if get_settings().video_provider != "mock":
        clip_key = await _generate_motion_clip(video, scene, result.image_bytes, result.format)
        if clip_key:
            return {"image_key": image_key, "video_key": clip_key,
                    "video_key_source": "ai_video_key",
                    "provider": result.provider}

    return {"image_key": image_key, "provider": result.provider}


async def _generate_motion_clip(video: Video, scene: Scene, image_bytes: bytes, image_format: str) -> str | None:
    """Animate the scene's still into real AI video motion.

    Best-effort by design: a configured generative-video provider is an
    enhancement over the Ken Burns still-image path, not a hard pipeline
    requirement. A quota hit or provider outage here degrades to the
    still-image path instead of failing a creator's whole video — but it
    is logged, since a persistently failing provider should be noticed and
    fixed rather than silently masked forever.
    """
    provider = select_provider("video")
    try:
        if provider.name != "mock":
            await provider_guard.claim_media_call("video")
        clip = await provider.generate_clip({
            "prompt": scene.visual_prompt,
            "camera": scene.camera,
            "lighting": scene.lighting,
            "duration_seconds": scene.duration_seconds,
            "aspect_ratio": video.aspect_ratio,
            "reference_image_bytes": image_bytes,
            "reference_image_format": image_format,
        })
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, see docstring
        logger.warning(
            "visual.motion_clip_failed", video_id=str(video.id),
            scene_sequence=scene.sequence, error_type=type(exc).__name__,
        )
        return None
    if not clip.video_bytes:
        return None
    clip_key, _, _ = await asyncio.to_thread(
        storage_service.put_object, clip.video_bytes,
        content_type=f"video/{clip.format}", prefix=f"videos/{video.id}/motion",
    )
    return clip_key
