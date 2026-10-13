"""Provider OAuth2 linking and encrypted token lifecycle."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import get_settings
from app.config.logging import get_logger
from app.db.models.publishing import PublishingAccount
from app.db.models.publishing_oauth import PublishingOAuthState
import json

PLATFORMS = ("youtube", "tiktok")
logger = get_logger("services.publishing_oauth")

def oauth_settings(platform: str) -> tuple[str, str, str]:
    s = get_settings()
    if platform not in PLATFORMS: raise HTTPException(404, "Unsupported publishing platform")
    client = s.youtube_client_id if platform == "youtube" else s.tiktok_client_id
    secret = s.youtube_client_secret if platform == "youtube" else s.tiktok_client_secret
    if not (client and secret and s.publishing_token_encryption_key):
        raise HTTPException(503, "Publishing OAuth is not configured")
    if s.app_env == "production" and not s.api_url.startswith("https://"):
        raise HTTPException(503, "API_URL must be an HTTPS Render origin")
    return client, secret, f"{s.api_url.rstrip('/')}/api/v1/publishing/oauth/{platform}/callback"

def _fernet() -> Fernet:
    key = get_settings().publishing_token_encryption_key
    try: return Fernet((key or "").encode("ascii"))
    except (TypeError, ValueError):
        raise HTTPException(503, "Publishing token encryption is not configured") from None

def encrypt_tokens(data: dict) -> str:
    # No token values ever exposed by API responses or application logging.
    return _fernet().encrypt(json.dumps(data).encode()).decode("ascii")

def decrypt_tokens(ciphertext: str) -> dict:
    try: return json.loads(_fernet().decrypt(ciphertext.encode("ascii")))
    except (ValueError, InvalidToken, json.JSONDecodeError):
        raise HTTPException(503, "Linked publishing credentials cannot be decrypted") from None

async def authorize(db: AsyncSession, platform: str, user_id: uuid.UUID) -> str:
    client, secret, redirect_uri = oauth_settings(platform)
    state = secrets.token_urlsafe(32)
    db.add(PublishingOAuthState(
        state_hash=hashlib.sha256(state.encode()).hexdigest(),
        user_id=user_id, platform=platform,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    ))
    await db.commit()
    if platform == "youtube":
        base = "https://accounts.google.com/o/oauth2/v2/auth"
        query = {"client_id":client, "redirect_uri":redirect_uri, "response_type":"code",
                 "scope":("https://www.googleapis.com/auth/youtube.upload "
                          "https://www.googleapis.com/auth/youtube.readonly"),
                 "access_type":"offline", "prompt":"consent", "state":state}
    else:
        base = "https://www.tiktok.com/v2/auth/authorize/"
        query = {"client_key":client, "redirect_uri":redirect_uri, "response_type":"code",
                 "scope":"user.info.basic,video.upload", "state":state}
    return f"{base}?{urlencode(query)}"

async def complete_authorization(db: AsyncSession, platform: str, state: str, code: str) -> None:
    client, secret, redirect_uri = oauth_settings(platform)
    digest = hashlib.sha256(state.encode()).hexdigest()
    grant = await db.scalar(select(PublishingOAuthState).where(
        PublishingOAuthState.state_hash == digest, PublishingOAuthState.platform == platform
    ).with_for_update())
    if not grant or grant.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(400, "Authorization expired or invalid")
    # Delete before provider exchange; failures require a fresh user consent.
    user_id = grant.user_id
    await db.delete(grant)
    await db.commit()
    if platform == "youtube":
        url = "https://oauth2.googleapis.com/token"
        data = {"client_id":client, "client_secret":secret, "code":code,
                "grant_type":"authorization_code", "redirect_uri":redirect_uri}
    else:
        url = "https://open.tiktokapis.com/v2/oauth/token/"
        data = {"client_key":client, "client_secret":secret, "code":code,
                "grant_type":"authorization_code", "redirect_uri":redirect_uri}
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as http:
        try:
            response = await http.post(url, data=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Do not leak Google's response, which could contain OAuth details.
            logger.warning("publishing.oauth_token_rejected", platform=platform,
                           provider_status=exc.response.status_code)
            raise HTTPException(
                502, f"{platform.title()} rejected the authorization exchange "
                     f"(HTTP {exc.response.status_code}). Check the OAuth client "
                     "configuration and start a fresh connection."
            ) from None
        except httpx.RequestError as exc:
            logger.warning("publishing.oauth_token_unreachable", platform=platform,
                           error_type=type(exc).__name__)
            raise HTTPException(503, "The publishing provider could not be reached. Please retry.") from None
        try:
            tokens = response.json()
        except ValueError:
            raise HTTPException(502, "The publishing provider returned an invalid token response") from None
        access = tokens.get("access_token")
        if not access or not tokens.get("refresh_token"):
            raise HTTPException(502, "Platform did not grant durable publishing access")
        if platform == "youtube":
            try:
                details = await http.get("https://www.googleapis.com/youtube/v3/channels",
                    params={"part":"id", "mine":"true"}, headers={"Authorization":f"Bearer {access}"})
                details.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning("publishing.youtube_channel_lookup_rejected",
                               provider_status=exc.response.status_code)
                if exc.response.status_code == 403:
                    raise HTTPException(
                        502, "Google denied YouTube channel access (403). Confirm YouTube "
                             "Data API v3 is enabled, and reconnect with youtube.readonly "
                             "and youtube.upload permissions."
                    ) from None
                raise HTTPException(
                    502, f"YouTube channel lookup failed (HTTP {exc.response.status_code}). "
                         "Confirm the account has an active YouTube channel."
                ) from None
            except httpx.RequestError as exc:
                logger.warning("publishing.youtube_channel_unreachable",
                               error_type=type(exc).__name__)
                raise HTTPException(503, "Unable to reach YouTube to verify your channel.") from None
            try:
                items = details.json().get("items", [])
                external_id = items[0]["id"] if items else None
            except (ValueError, KeyError, IndexError, TypeError):
                raise HTTPException(502, "YouTube returned invalid channel information") from None
            if not external_id:
                raise HTTPException(
                    400, "No YouTube channel was found for this Google account. "
                         "Create a YouTube channel or select the account that owns one."
                )
        else:
            external_id = tokens.get("open_id")
            if not external_id: raise HTTPException(502, "TikTok response missing open_id")
    tokens["expires_at"] = (datetime.now(timezone.utc) +
                            timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)).isoformat()
    result = await db.execute(select(PublishingAccount).where(
        PublishingAccount.user_id == user_id, PublishingAccount.platform == platform,
        PublishingAccount.external_id == external_id,
    ).with_for_update())
    account = result.scalar_one_or_none()
    if account is None:
        account = PublishingAccount(user_id=user_id, platform=platform, external_id=external_id, token_ref="encrypted:db")
        db.add(account)
    account.token_ciphertext = encrypt_tokens(tokens)
    await db.commit()

async def usable_token(db: AsyncSession, account: PublishingAccount) -> str:
    if not account.token_ciphertext:
        raise HTTPException(503, "Publishing account must be reconnected using OAuth")
    token = decrypt_tokens(account.token_ciphertext)
    expires = datetime.fromisoformat(token["expires_at"])
    if expires > datetime.now(timezone.utc) + timedelta(minutes=2):
        return token["access_token"]
    client, secret, _ = oauth_settings(account.platform)
    if account.platform == "youtube":
        url = "https://oauth2.googleapis.com/token"
        data = {"client_id":client, "client_secret":secret, "refresh_token":token["refresh_token"],
                "grant_type":"refresh_token"}
    else:
        url = "https://open.tiktokapis.com/v2/oauth/token/"
        data = {"client_key":client, "client_secret":secret, "refresh_token":token["refresh_token"],
                "grant_type":"refresh_token"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as http:
        resp = await http.post(url, data=data)
        resp.raise_for_status()
        updated = resp.json()
    if not updated.get("access_token"): raise HTTPException(502, "Platform refresh failed")
    token.update(updated)
    token["expires_at"] = (datetime.now(timezone.utc) +
                           timedelta(seconds=int(updated.get("expires_in", 3600)) - 60)).isoformat()
    account.token_ciphertext = encrypt_tokens(token)
    await db.commit()
    return token["access_token"]
