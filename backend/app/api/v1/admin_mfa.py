"""Admin authenticator setup and per-adjustment password + TOTP reauthorization."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.admin_mfa import AdminMfaCredential
from app.db.models.audit import AuditLog
from app.db.models.user import User
from app.db.session import get_db
from app.security.admin import require_admin
from app.security.admin_mfa import (
    decrypt_secret, digest_credit_adjustment, encrypt_secret,
    generate_totp_secret, issue_adjustment_token, provisioning_uri,
    valid_unused_step,
)
from app.security.auth import verify_password
from app.security.credit_payload import CreditAdjustment
from app.security.rate_limit import RateLimiter

router = APIRouter(prefix="/admin/mfa", tags=["admin-security"])


class AdminPassword(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class TotpConfirmation(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class RotationStart(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(pattern=r"^[0-9]{6}$")


class RotationConfirm(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class CreditStepUpRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(pattern=r"^[0-9]{6}$")
    adjustment: CreditAdjustment


@router.get("/status")
async def mfa_status(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    cred = await db.get(AdminMfaCredential, admin.id)
    return {"enabled": bool(cred and cred.enabled)}


@router.post("/enroll")
async def enroll(
    payload: AdminPassword,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=3, window_seconds=60, scope="admin_mfa_enroll")),
):
    if not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid administrator password")
    cred = await db.get(AdminMfaCredential, admin.id, with_for_update=True)
    if cred is not None and cred.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Authenticator already enabled")
    secret = generate_totp_secret()
    cipher = encrypt_secret(secret)
    if cred is None:
        db.add(AdminMfaCredential(user_id=admin.id, encrypted_secret=cipher))
    else:
        cred.encrypted_secret = cipher
        cred.last_used_step = -1
    db.add(AuditLog(
        actor_id=admin.id, action="admin_mfa_enrollment_started",
        resource="user", resource_id=str(admin.id),
        audit_metadata={"method": "totp"},
    ))
    await db.commit()
    return {"secret": secret, "otpauth_uri": provisioning_uri(secret, admin.email)}


@router.post("/activate")
async def activate(
    payload: TotpConfirmation,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="admin_mfa_activate")),
):
    cred = await db.get(AdminMfaCredential, admin.id, with_for_update=True)
    if cred is None or cred.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending authenticator enrollment")
    step = valid_unused_step(decrypt_secret(cred.encrypted_secret), payload.code, cred.last_used_step)
    if step is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or already-used authenticator code")
    cred.enabled = True
    cred.last_used_step = step
    db.add(AuditLog(
        actor_id=admin.id, action="admin_mfa_enabled",
        resource="user", resource_id=str(admin.id),
        audit_metadata={"method": "totp"},
    ))
    await db.commit()
    return {"enabled": True}


@router.post("/authorize-adjustment")
async def authorize_adjustment(
    payload: CreditStepUpRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="admin_mfa_authorize")),
):
    if not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid administrator credentials")
    cred = await db.get(AdminMfaCredential, admin.id, with_for_update=True)
    if cred is None or not cred.enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Set up an authenticator before managing credits")
    step = valid_unused_step(decrypt_secret(cred.encrypted_secret), payload.code, cred.last_used_step)
    if step is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or already-used authenticator code")
    cred.last_used_step = step
    digest = digest_credit_adjustment(payload.adjustment)
    db.add(AuditLog(
        actor_id=admin.id, action="credit_adjustment_authorized",
        resource="user", resource_id=str(payload.adjustment.user_id),
        audit_metadata={"request_id": str(payload.adjustment.request_id), "payload_digest": digest},
    ))
    await db.commit()
    return {"authorization_token": issue_adjustment_token(str(admin.id), digest), "expires_in_seconds": 180}



@router.post("/rotation/start")
async def start_rotation(
    payload: RotationStart,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=3, window_seconds=60, scope="admin_mfa_rotate_start")),
):
    """Require password + current TOTP. Do not deactivate the current device."""
    if not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid administrator credentials")
    cred = await db.get(AdminMfaCredential, admin.id, with_for_update=True)
    if cred is None or not cred.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Enable an authenticator before replacing it")
    step = valid_unused_step(decrypt_secret(cred.encrypted_secret), payload.code, cred.last_used_step)
    if step is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or already-used authenticator code")
    secret = generate_totp_secret()
    cred.last_used_step = step
    cred.pending_encrypted_secret = encrypt_secret(secret)
    cred.pending_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.add(AuditLog(
        actor_id=admin.id, action="admin_mfa_rotation_started",
        resource="user", resource_id=str(admin.id),
        audit_metadata={"method": "totp"},
    ))
    await db.commit()
    return {
        "secret": secret,
        "otpauth_uri": provisioning_uri(secret, admin.email, label_suffix=" (replacement)"),
        "expires_in_seconds": 600,
    }


@router.post("/rotation/confirm")
async def confirm_rotation(
    payload: RotationConfirm,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="admin_mfa_rotate_confirm")),
):
    cred = await db.get(AdminMfaCredential, admin.id, with_for_update=True)
    if cred is None or not cred.enabled or not cred.pending_encrypted_secret or not cred.pending_expires_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending authenticator replacement")
    if datetime.now(timezone.utc) >= cred.pending_expires_at:
        raise HTTPException(status.HTTP_410_GONE, "Replacement expired. Start again using your current authenticator.")
    step = valid_unused_step(decrypt_secret(cred.pending_encrypted_secret), payload.code, -1)
    if step is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid replacement authenticator code")
    cred.encrypted_secret = cred.pending_encrypted_secret
    cred.last_used_step = step
    cred.pending_encrypted_secret = None
    cred.pending_expires_at = None
    db.add(AuditLog(
        actor_id=admin.id, action="admin_mfa_rotated",
        resource="user", resource_id=str(admin.id),
        audit_metadata={"method": "totp"},
    ))
    await db.commit()
    return {"enabled": True, "rotated": True}
