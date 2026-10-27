"""Synthesizes narration audio for one scene and uploads it to object storage."""
import asyncio

from app.db.models.scene import Scene
from app.db.models.video import Video
from app.services import storage_service, voice_service
from app.services.personal_voice_service import empty_narration
from app.services.voice_clone_service import synthesize_cloned_scene, VoiceCloneUnavailable
from app.db.models.asset import Asset
from app.db.session import session_scope
import uuid


async def run(video: Video, scene: Scene, *, owner_id: uuid.UUID | None = None) -> tuple[str, float]:
    """Returns (storage_key, duration_seconds)."""
    preferences = video.voice_preferences or {}
    if preferences.get("mode") == "recorded":
        # A private recorded-voice project first builds its visual storyboard.
        # The editor then replaces each silent placeholder with its owner's
        # narration and re-renders with no text-to-speech provider calls.
        audio_bytes = empty_narration()
        duration = float(scene.duration_seconds)
    elif preferences.get("mode") == "clone":
        if owner_id is None or not preferences.get("profile_id"):
            raise VoiceCloneUnavailable("Voice owner and profile are required")
        try:
            profile_id = uuid.UUID(preferences["profile_id"])
        except ValueError:
            raise VoiceCloneUnavailable("Voice profile ID is invalid") from None
        async with session_scope() as db:
            asset = await db.get(Asset, profile_id)
            if asset is None:
                raise VoiceCloneUnavailable("Voice profile is unavailable")
            # Read the ownership/consent as of each generation attempt.
            audio_bytes, duration = await synthesize_cloned_scene(
                scene.narration, video.language, asset, owner_id,
            )
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
