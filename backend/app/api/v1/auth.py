"""Authentication: signup, login, token refresh."""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from app.security.rate_limit import RateLimiter
from app.services.password_email import send_password_reset_email, mail_delivery_configured
from app.security.password_reset import hash_reset_token, limit_password_reset_email
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User, UserStatus
from app.db.models.password_reset import PasswordResetToken
from app.db.models.audit import AuditLog
from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.db.models.billing import CreditLedgerEntry, LedgerEntryType
from app.services.credit_service import CREDIT_CURRENCY
from app.db.session import get_db
from app.security.auth import hash_password, verify_password
from app.services.user_sessions import create_session, rotate_session, revoke_refresh
from app.db.models.user_session import UserSession

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    normalized_email = str(payload.email).strip().lower()
    existing = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(email=normalized_email, password_hash=hash_password(payload.password), full_name=payload.full_name)
    db.add(user)
    await db.flush()
    settings = get_settings()
    if settings.credit_enforcement_enabled and settings.signup_starter_credits:
        db.add(CreditLedgerEntry(
            user_id=user.id,
            entry_type=LedgerEntryType.ADJUSTMENT,
            amount=settings.signup_starter_credits,
            currency=CREDIT_CURRENCY,
            reference_type="signup",
            reference_id=str(user.id),
            entry_metadata={"reason": "one_time_starter_grant"},
        ))
    await db.commit()
    await db.refresh(user)

    return TokenResponse(**(await create_session(db, user)))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="password_login")),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenResponse(**(await create_session(db, user)))



class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=40, max_length=256)
    new_password: str = Field(min_length=12, max_length=72)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=72)


class RevokeSessionsRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="password_reset_ip")),
):
    """Neutral response for existing/missing accounts; never return reset secrets."""
    if not mail_delivery_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Password recovery email is not configured")

    email = str(payload.email).strip().lower()
    # Per-account throttling is applied even for unknown addresses.
    if not await limit_password_reset_email(email):
        return {"message": "If an account exists, a reset link will be emailed."}
    result = await db.execute(select(User).where(func.lower(User.email) == email).limit(2))
    accounts = list(result.scalars().all())
    # Legacy case-sensitive duplicates must never result in an ambiguous grant.
    user = accounts[0] if len(accounts) == 1 else None
    if user and user.status == UserStatus.ACTIVE:
        token = secrets.token_urlsafe(32)
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        db.add(PasswordResetToken(
            user_id=user.id, token_hash=hash_reset_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        ))
        await db.commit()
        # Sending failures are deliberately not disclosed as account enumeration
        # hints. Operational alerting can be added without logging reset links.
        try:
            await send_password_reset_email(user.email, token)
        except Exception:
            await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
                                                               PasswordResetToken.token_hash == hash_reset_token(token)))
            await db.commit()
    return {"message": "If an account exists, a reset link will be emailed."}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=6, window_seconds=60, scope="password_reset_confirm")),
):
    # Lock the token row to prevent two simultaneous redemption attempts.
    token_hash = hash_reset_token(payload.token)
    token = await db.scalar(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash
    ).with_for_update())
    if token is None or token.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset link is invalid or expired")
    user = await db.scalar(select(User).where(User.id == token.user_id).with_for_update())
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset link is invalid or expired")
    user.password_hash = hash_password(payload.new_password)
    user.session_version += 1
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.add(AuditLog(actor_id=user.id, action="password_reset_completed",
                    resource="user", resource_id=str(user.id),
                    audit_metadata={"method": "email"}))
    await db.commit()


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="password_change")),
):
    # Re-read under lock so concurrent password changes cannot race.
    account = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    if account is None or account.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not active")
    if not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid current password")
    if verify_password(payload.new_password, account.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a different password")
    account.password_hash = hash_password(payload.new_password)
    account.session_version += 1
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == account.id))
    db.add(AuditLog(actor_id=account.id, action="password_changed",
                    resource="user", resource_id=str(account.id), audit_metadata={}))
    await db.commit()


@router.post("/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    payload: RevokeSessionsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(RateLimiter(limit=5, window_seconds=60, scope="logout_all")),
):
    account = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid password")
    account.session_version += 1
    db.add(AuditLog(actor_id=account.id, action="all_sessions_revoked",
                    resource="user", resource_id=str(account.id), audit_metadata={}))
    await db.commit()



class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=4096)


@router.post("/sessions/refresh", response_model=TokenResponse)
async def refresh_session(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return TokenResponse(**(await rotate_session(db, payload.refresh_token)))


@router.post("/sessions/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_session(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    await revoke_refresh(db, payload.refresh_token)


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.revoked.is_(False),
        UserSession.expires_at > datetime.now(timezone.utc),
    ).order_by(UserSession.created_at.desc()).limit(50))).scalars().all()
    return {"sessions": [{"id": str(row.id), "created_at": row.created_at, "expires_at": row.expires_at} for row in rows]}


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: uuid.UUID, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(UserSession).where(
        UserSession.id == session_id, UserSession.user_id == user.id,
    ).with_for_update())
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    session.revoked = True
    await db.commit()
