"""RFC 6238 TOTP, encrypted at rest, replay-safe and scoped admin step-up JWTs."""
import base64
import hmac
import hashlib
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from pydantic import ValidationError

from app.api.deps import get_current_user
from app.config.settings import get_settings
from app.db.models.user import User
from app.security.admin import require_admin
from app.security.auth import decode_token
from app.security.credit_payload import CreditAdjustment, digest_credit_adjustment


def _cipher() -> Fernet:
    key = get_settings().admin_mfa_encryption_key
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Operator second-factor encryption is not configured")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Operator second-factor encryption is misconfigured") from None


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _cipher().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Operator authenticator cannot be verified") from None


def totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def valid_unused_step(secret: str, code: str, last_used: int, *, now: float | None = None) -> int | None:
    if len(code) != 6 or not code.isascii() or not code.isdecimal():
        return None
    current = int((time.time() if now is None else now) // 30)
    # First compare all 3 windows in constant time; reject previously
    # consumed steps. The time window is 30 seconds (+/- one step).
    matches = [
        step for step in (current - 1, current, current + 1)
        if step > last_used and step >= 0 and hmac.compare_digest(totp_code(secret, step), code)
    ]
    return max(matches) if matches else None


def provisioning_uri(secret: str, email: str) -> str:
    issuer_name = "Baalebos Creator Studio"
    account = quote(f"{issuer_name}:{email}", safe="")
    issuer = quote(issuer_name, safe="")
    return f"otpauth://totp/{account}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def issue_adjustment_token(user_id: str, digest: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=3)
    return jwt.encode({
        "type": "admin_credit_step_up", "sub": user_id,
        "digest": digest, "exp": expire,
        "jti": secrets.token_urlsafe(16),
    }, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_adjustment_token(raw_token: str | None, *, user_id: str, digest: str) -> None:
    if not raw_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Authorize this adjustment with your authenticator")
    try:
        claims = decode_token(raw_token)
    except (JWTError, ValueError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Adjustment authorization expired or invalid") from None
    if (
        claims.get("type") != "admin_credit_step_up"
        or not hmac.compare_digest(str(claims.get("sub", "")), user_id)
        or not hmac.compare_digest(str(claims.get("digest", "")), digest)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Adjustment authorization does not match this request")


async def require_adjustment_authorization(
    request: Request,
    user: User = Depends(require_admin),
) -> None:
    try:
        payload = CreditAdjustment.model_validate(await request.json())
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid credit adjustment") from None
    verify_adjustment_token(
        request.headers.get("X-Admin-Authorization"),
        user_id=str(user.id),
        digest=digest_credit_adjustment(payload),
    )
