"""Synthesizes narration audio for one scene and uploads it to object storage."""
import asyncio

from app.db.models.scene import Scene
from app.db.models.video import Video
from app.services import storage_service, voice_service
from app.services.personal_voice_service import empty_narration


async def run(video: Video, scene: Scene) -> tuple[str, float]:
    """Returns (storage_key, duration_seconds)."""
    preferences = video.voice_preferences or {}
    if preferences.get("mode") == "recorded":
        # A private recorded-voice project first builds its visual storyboard.
        # The editor then replaces each silent placeholder with its owner's
        # narration and re-renders with no text-to-speech provider calls.
        audio_bytes = empty_narration()
        duration = float(scene.duration_seconds)
    else:
        if video.language in {"Nigerian Pidgin", "Yoruba"}:
            raise ValueError("This language requires recorded narration")
        result = await voice_service.synthesize_narration(
            text=scene.narration, locale=video.locale, voice_preferences=preferences
        )
        audio_bytes = result.audio_bytes
        duration = result.duration_seconds
    storage_key, _checksum, _size = await asyncio.to_thread(
        storage_service.put_object,
        audio_bytes,
        content_type="audio/wav",
        prefix=f"videos/{video.id}/audio",
    )
    return storage_key, duration
