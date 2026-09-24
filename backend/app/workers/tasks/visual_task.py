"""Generates the visual asset (image, or a rendered video clip) for one scene."""
from app.db.models.scene import Scene
from app.db.models.video import Video
from app.services import storage_service, visual_service


async def run(video: Video, scene: Scene) -> str:
    """Returns storage_key of the generated scene image."""
    result = await visual_service.generate_scene_image(prompt=scene.visual_prompt, aspect_ratio=video.aspect_ratio)
    storage_key, _checksum, _size = storage_service.put_object(
        result.image_bytes, content_type=f"image/{result.format}", prefix=f"videos/{video.id}/images"
    )
    return storage_key
