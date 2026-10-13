"""Voice catalog + preview endpoints (blueprint section 9)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.security.rate_limit import RateLimiter
from app.config.settings import get_settings
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services import credit_service
import uuid

from app.api.deps import get_current_user
from app.db.models.user import User
from app.services import voice_service

router = APIRouter(prefix="/voices", tags=["voices"])


class VoicePreviewRequest(BaseModel):
    voice_id: str = Field(min_length=1, max_length=128)
    # Voice preview can incur real provider charges: cap the input and
    # enforce a separate rate limit instead of allowing arbitrary text.
    sample_text: str | None = Field(default=None, max_length=240)


@router.get("")
async def list_voices(locale: str | None = None, user: User = Depends(get_current_user)):
    return await voice_service.list_voices(locale)


@router.post("/preview")
async def preview_voice(
    payload: VoicePreviewRequest,
    user: User = Depends(get_current_user),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="voice_preview")),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    charged_id = str(uuid.uuid4()) if settings.voice_provider != "mock" and settings.credit_enforcement_enabled else None
    if charged_id:
        await credit_service.debit(
            db, user.id, settings.voice_preview_credits, reference_type="voice_preview",
            reference_id=charged_id,
        )
        await db.commit()
    try:
        result = await voice_service.preview_voice(
            voice_id=payload.voice_id, sample_text=payload.sample_text or "This is a preview of the selected voice."
        )
    except Exception:
        await db.rollback()
        if charged_id:
            await credit_service.refund(db, user.id, reference_type="voice_preview", reference_id=charged_id)
            await db.commit()
        raise
    import base64

    return {
        "voice_id": result.voice_id,
        "format": result.format,
        "duration_seconds": result.duration_seconds,
        "audio_base64": base64.b64encode(result.audio_bytes).decode(),
    }
