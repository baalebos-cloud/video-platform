"""Private consent-based reference voice profiles and cloning capability gate.

A reference profile is a private AUDIO asset tagged as enrollment, not a
trained model. Automatic synthesis is enabled only when a licensed external
inference service is explicitly provisioned by the operator.
"""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.db.models.asset import Asset, AssetType
from app.db.models.user import User
from app.db.session import get_db
from app.security.rate_limit import RateLimiter
from app.services import storage_service
from app.services.personal_voice_service import MAX_UPLOAD_BYTES, PersonalVoiceError, normalize_recording

router = APIRouter(prefix="/voice-profiles", tags=["voice profiles"])
MAX_PROFILES_PER_USER = 3
MIN_REFERENCE_SECONDS = 5.0
MAX_REFERENCE_SECONDS = 30.0


def is_voice_profile(asset: Asset) -> bool:
    return (
        asset.type == AssetType.AUDIO
        and (asset.provider_metadata or {}).get("provider") == "personal_voice_reference"
        and (asset.provider_metadata or {}).get("consent") == "self_recorded"
    )


def profile_data(asset: Asset) -> dict:
    metadata = asset.provider_metadata or {}
    return {
        "id": str(asset.id),
        "name": metadata.get("name", "My voice"),
        "language": metadata.get("language", "English"),
        "duration_seconds": metadata.get("duration_seconds", 0),
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "status": "reference_saved",
    }


@router.get("/capabilities")
async def cloning_capabilities(user: User = Depends(get_current_user)):
    config = get_settings()
    return {
        "recorded_voice": True,
        "reference_profiles": True,
        "automatic_cloning": config.voice_clone_enabled,
        "supported_languages": (
            ["English", "Nigerian Pidgin", "Yoruba"]
            if config.voice_clone_enabled else []
        ),
        "message": (
            "Licensed private voice inference is configured."
            if config.voice_clone_enabled
            else "Automatic personal-voice synthesis requires a commercially licensed inference service. "
                 "You can save a private voice reference and record individual scenes now."
        ),
    }


@router.get("")
async def list_voice_profiles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(Asset.owner_id == user.id, Asset.type == AssetType.AUDIO)
    )
    profiles = [profile_data(a) for a in result.scalars().all() if is_voice_profile(a)]
    return sorted(profiles, key=lambda item: item["created_at"] or "", reverse=True)


@router.post("")
async def create_voice_profile(
    request: Request,
    user: User = Depends(get_current_user),
    _: None = Depends(RateLimiter(limit=4, window_seconds=3600, scope="voice_profile_create")),
    db: AsyncSession = Depends(get_db),
):
    if request.headers.get("x-voice-consent") != "self":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enroll only your own voice with informed consent")
    name = request.headers.get("x-voice-name", "").strip()
    language = request.headers.get("x-voice-language", "")
    if not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Voice profile name must contain 1-60 characters")
    if language not in {"English", "Nigerian Pidgin", "Yoruba"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported reference language")
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_UPLOAD_BYTES):
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Reference audio exceeds 3 MB")
    raw = await request.body()
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Reference audio must be 3 MB or smaller")
    try:
        wav, seconds = await asyncio.to_thread(
            normalize_recording, raw, request.headers.get("content-type", ""), MAX_REFERENCE_SECONDS
        )
    except PersonalVoiceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    if seconds < MIN_REFERENCE_SECONDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Record at least five seconds for a voice profile"
        )
    # Prevent excess private biometric references from accumulating.
    existing = await db.execute(
        select(Asset).where(Asset.owner_id == user.id, Asset.type == AssetType.AUDIO)
    )
    if sum(is_voice_profile(a) for a in existing.scalars().all()) >= MAX_PROFILES_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, "Maximum three voice profiles per account")

    storage_key, checksum, size = await asyncio.to_thread(
        storage_service.put_object, wav, content_type="audio/wav",
        prefix=f"users/{user.id}/voice-profiles",
    )
    asset = Asset(
        owner_id=user.id, type=AssetType.AUDIO, storage_key=storage_key,
        mime_type="audio/wav", checksum=checksum, size_bytes=size,
        provider_metadata={
            "provider": "personal_voice_reference",
            "consent": "self_recorded",
            "name": name, "language": language,
            "duration_seconds": round(seconds, 2),
            "schema_version": 1,
        },
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return profile_data(asset)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_profile(
    profile_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.get(Asset, profile_id)
    if asset is None or asset.owner_id != user.id or not is_voice_profile(asset):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice profile not found")
    # Remove storage first, then metadata. If object deletion fails, the
    # reference remains visible so the owner can retry, not silently orphaned.
    try:
        await asyncio.to_thread(storage_service.delete_object, asset.storage_key)
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Unable to delete reference audio; retry") from None
    await db.delete(asset)
    await db.commit()
