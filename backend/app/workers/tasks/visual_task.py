"""Generate real stock footage where available; otherwise use the configured image AI."""
import asyncio

from app.db.models.scene import Scene
from app.db.models.video import Video
from app.services import stock_footage_service, storage_service, visual_service


async def run(video: Video, scene: Scene) -> dict:
    """Return a persisted scene preview and optionally a licensed MP4 footage key."""
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
                    "provider": "pixabay", "source_url": stock.source_page_url}

    result = await visual_service.generate_scene_image(
        prompt=scene.visual_prompt, aspect_ratio=video.aspect_ratio,
    )
    image_key, _, _ = await asyncio.to_thread(
        storage_service.put_object, result.image_bytes,
        content_type=f"image/{result.format}", prefix=f"videos/{video.id}/images",
    )
    return {"image_key": image_key, "provider": result.provider}
