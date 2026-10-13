"""Database-bound refresh token rotation and revocation."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import get_settings
from app.db.models.user_session import UserSession
from app.db.models.user import User, UserStatus
from app.security.auth import create_access_token, create_refresh_token, decode_token

def _digest(jti: str) -> str:
    return hashlib.sha256(jti.encode("ascii")).hexdigest()

def _issue(user: User, session: UserSession) -> dict:
    jti = secrets.token_urlsafe(32)
    session.refresh_hash = _digest(jti)
    session.expires_at = datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_token_expire_days)
    return {
        "access_token": create_access_token(str(user.id), {"sv": user.session_version, "sid": str(session.id)}),
        "refresh_token": create_refresh_token(str(user.id), session_version=user.session_version, jti=jti),
        "token_type": "bearer",
    }

async def create_session(db: AsyncSession, user: User) -> dict:
    session = UserSession(id=uuid.uuid4(), user_id=user.id, refresh_hash="x" * 64,
                          expires_at=datetime.now(timezone.utc), revoked=False)
    response = _issue(user, session)
    db.add(session)
    await db.commit()
    return response

async def rotate_session(db: AsyncSession, raw_refresh: str) -> dict:
    try:
        claims = decode_token(raw_refresh)
        if claims.get("type") != "refresh" or not isinstance(claims.get("jti"), str):
            raise ValueError("Missing refresh identifier")
        uid = uuid.UUID(claims["sub"])
    except (JWTError, ValueError, KeyError, TypeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh session") from None
    record = await db.scalar(select(UserSession).where(UserSession.refresh_hash == _digest(claims["jti"])).with_for_update())
    user = await db.scalar(select(User).where(User.id == uid).with_for_update()) if record else None
    if (record is None or user is None or record.user_id != uid or record.revoked
            or user.status != UserStatus.ACTIVE or record.expires_at <= datetime.now(timezone.utc)
            or claims.get("sv") != user.session_version):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh session expired or revoked")
    # Row-level lock enforces single use. Concurrent duplicate submissions fail.
    response = _issue(user, record)
    await db.commit()
    return response

async def revoke_refresh(db: AsyncSession, raw_refresh: str) -> None:
    try:
        claims = decode_token(raw_refresh)
        if claims.get("type") != "refresh" or not isinstance(claims.get("jti"), str):
            return
        uid = uuid.UUID(claims["sub"])
    except (JWTError, ValueError, KeyError, TypeError):
        return
    record = await db.scalar(select(UserSession).where(
        UserSession.refresh_hash == _digest(claims["jti"]),
        UserSession.user_id == uid,
    ).with_for_update())
    if record:
        record.revoked = True
        await db.commit()
