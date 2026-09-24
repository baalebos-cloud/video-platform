"""Voice catalog + preview endpoints (blueprint section 9)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.models.user import User
from app.services import voice_service

router = APIRouter(prefix="/voices", tags=["voices"])


class VoicePreviewRequest(BaseModel):
    voice_id: str
    sample_text: str | None = None


@router.get("")
async def list_voices(locale: str | None = None, user: User = Depends(get_current_user)):
    return await voice_service.list_voices(locale)


@router.post("/preview")
async def preview_voice(payload: VoicePreviewRequest, user: User = Depends(get_current_user)):
    result = await voice_service.preview_voice(
        voice_id=payload.voice_id, sample_text=payload.sample_text or "This is a preview of the selected voice."
    )
    import base64

    return {
        "voice_id": result.voice_id,
        "format": result.format,
        "duration_seconds": result.duration_seconds,
        "audio_base64": base64.b64encode(result.audio_bytes).decode(),
    }
