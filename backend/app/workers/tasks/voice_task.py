"""Synthesizes narration audio for one scene and uploads it to object storage."""
from app.db.models.scene import Scene
from app.db.models.video import Video
from app.services import storage_service, voice_service


async def run(video: Video, scene: Scene) -> tuple[str, float]:
    """Returns (storage_key, duration_seconds)."""
    result = await voice_service.synthesize_narration(
        text=scene.narration, locale=video.locale, voice_preferences=video.voice_preferences
    )
    storage_key, _checksum, _size = storage_service.put_object(
        result.audio_bytes, content_type=f"audio/{result.format}", prefix=f"videos/{video.id}/audio"
    )
    return storage_key, result.duration_seconds
