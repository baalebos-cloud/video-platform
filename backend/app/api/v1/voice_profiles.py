"""Private voice profiles and explicit opt-in for a licensed cloning backend.

A profile is reference audio, not a trained voice model. The automatic voice
option is offered only when the operator has licensed/configured a compatible
synthesis service. The owner can revoke and delete the reference at any time.
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

router = APIRouter(prefix="/voice-profiles", tags=["voice-profiles"])
SUPPORTED = {"English": "en", "Nigerian Pidgin": "pcm", "Yoruba": "yo"}


def is_voice_profile(asset: Asset | None, owner_id: uuid.UUID) -> bool:
    return bool(
        asset and asset.owner_id == owner_id
        and asset.type == AssetType.AUDIO
        and (asset.provider_metadata or {}).get("purpose") == "voice_profile"
        and (asset.provider_metadata or {}).get("revoked") is not True
        and (asset.provider_metadata or {}).get("consent") == "explicit"
    )


def profile_public(asset: Asset) -> dict:
    metadata = asset.provider_metadata or {}
    return {
        "id": str(asset.id), "name": metadata.get("name", "My voice"),
        "language": metadata.get("language", "English"),
        "duration_seconds": metadata.get("duration_seconds", 0),
        "status": "reference_saved",
    }


@router.get("/capabilities")
async def capabilities(user: User = Depends(get_current_user)):
    from app.services.voice_clone_service import VoiceCloneUnavailable, configured_clone_url
    try:
        configured_clone_url()
    except VoiceCloneUnavailable:
        enabled = False
    else:
        enabled = True
    return {
        "personal_recordings": True,
        "reference_profiles": True,
        "automatic_cloning": enabled,
        "languages": list(SUPPORTED),
        "notice": (
            "An operator-approved licensed cloning provider is configured."
            if enabled else
            "Automatic voice cloning is not configured. Save a private voice "
            "reference and use your real recordings meanwhile."
        ),
    }


@router.get("")
async def list_profiles(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(Asset.owner_id == user.id, Asset.type == AssetType.AUDIO)
    )
    return [profile_public(asset) for asset in result.scalars().all()
            if is_voice_profile(asset, user.id)]


@router.post("", status_code=201)
async def create_profile(
    request: Request, user: User = Depends(get_current_user),
    _: None = Depends(RateLimiter(limit=5, window_seconds=3600, scope="voice_profile_enroll")),
    db: AsyncSession = Depends(get_db),
):
    if request.headers.get("x-voice-consent") != "confirmed" or request.headers.get("x-clone-consent") != "confirmed":
        raise HTTPException(400, "Explicit voice ownership and synthesis consent are required")
    language = request.headers.get("x-voice-language", "English")
    if language not in SUPPORTED:
        raise HTTPException(422, "Unsupported profile language")
    name = request.headers.get("x-voice-name", "My voice").strip()
    if not 1 <= len(name) <= 60 or any(ord(ch) < 32 for ch in name):
        raise HTTPException(422, "Voice profile name must contain 1-60 printable characters")
    size = request.headers.get("content-length")
    if size and (not size.isdigit() or int(size) > MAX_UPLOAD_BYTES):
        raise HTTPException(413, "Voice reference must be under 3 MB")
    raw = await request.body()
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Voice reference must be under 3 MB")
    try:
        data, seconds = await asyncio.to_thread(
            normalize_recording, raw, request.headers.get("content-type", ""), 20.0,
        )
    except PersonalVoiceError as exc:
        raise HTTPException(422, str(exc)) from None
    if seconds < 5:
        raise HTTPException(422, "Record at least five seconds of clear reference speech")
    storage_key, checksum, size_bytes = await asyncio.to_thread(
        storage_service.put_object, data,
        content_type="audio/wav", prefix=f"users/{user.id}/voice-references",
    )
    asset = Asset(
        owner_id=user.id, type=AssetType.AUDIO, storage_key=storage_key,
        mime_type="audio/wav", checksum=checksum, size_bytes=size_bytes,
        provider_metadata={
            "purpose": "voice_profile", "provider": "user_reference",
            "consent": "explicit", "revoked": False,
            "name": name, "language": language,
            "duration_seconds": round(seconds, 2),
        },
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return profile_public(asset)


@router.delete("/{profile_id}", status_code=204)
async def revoke_profile(
    profile_id: uuid.UUID, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Asset).where(Asset.id == profile_id).with_for_update())
    asset = result.scalar_one_or_none()
    # A previously revoked reference must remain deletable if object-storage
    # cleanup failed. Do not accept other users' or other kinds of assets.
    metadata = (asset.provider_metadata or {}) if asset is not None else {}
    if (
        asset is None or asset.owner_id != user.id
        or asset.type != AssetType.AUDIO
        or metadata.get("purpose") != "voice_profile"
        or metadata.get("consent") != "explicit"
    ):
        raise HTTPException(404, "Voice profile not found")
    key = asset.storage_key
    if metadata.get("revoked") is not True:
        # First make it impossible to use this profile for new synthesis.
        asset.provider_metadata = {**metadata, "revoked": True}
        await db.commit()
    try:
        await asyncio.to_thread(storage_service.delete_object, key)
    except Exception:
        # Keep the tombstone so DELETE can be retried until physical storage
        # removal succeeds. Never report successful deletion for an orphaned WAV.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Voice reference revoked; storage cleanup failed. Retry deletion.",
        ) from None
    # Delete the metadata only after deleting the private WAV.
    await db.delete(asset)
    await db.commit()
