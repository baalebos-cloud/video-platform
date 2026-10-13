"""
Shared FastAPI dependencies: current user resolution from a bearer JWT,
database session, and small helpers reused across v1 routers.
"""
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User, UserStatus
from app.db.models.user_session import UserSession
from app.db.session import get_db
from app.security.auth import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not active")

    # Tokens issued before this migration have no sv claim: treat as version 0.
    # Any password change, password recovery, or logout-all increments the version.
    if (not isinstance(payload.get("sv", 0), int)
            or isinstance(payload.get("sv", 0), bool)
            or payload.get("sv", 0) != user.session_version):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been revoked")

    # New sessions carry a database session id. Revoking that individual
    # session immediately invalidates its access JWT as well as its refresh.
    if "sid" in payload:
        try:
            sid = uuid.UUID(payload["sid"])
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session identifier") from None
        session = await db.scalar(select(UserSession).where(
            UserSession.id == sid, UserSession.user_id == user.id,
            UserSession.revoked.is_(False),
            UserSession.expires_at > datetime.now(timezone.utc),
        ))
        if session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been revoked")

    request.state.user = user  # available to the rate limiter
    return user
