"""Phase 8: single-use recovery, session invalidation and delivery safety."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from starlette.requests import Request

from app.api.deps import get_current_user
from app.api.v1 import auth
from app.config.settings import Settings
from app.db.models.audit import AuditLog
from app.db.models.password_reset import PasswordResetToken
from app.db.models.user import UserStatus
from app.security.auth import create_access_token, create_refresh_token, decode_token, verify_password
from app.security.password_reset import hash_reset_token


def account():
    return SimpleNamespace(
        id=uuid.uuid4(), email="creator@example.com", password_hash="old-hash",
        status=UserStatus.ACTIVE, session_version=0,
    )


@pytest.mark.asyncio
async def test_email_delivery_disabled_returns_503_without_account_lookup():
    db = AsyncMock()
    with patch.object(auth, "mail_delivery_configured", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await auth.request_password_reset(auth.PasswordResetRequest(email="person@example.com"), db=db)
    assert exc.value.status_code == 503
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_email_does_not_send_and_has_generic_response():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    with patch.object(auth, "mail_delivery_configured", return_value=True), \
         patch.object(auth, "limit_password_reset_email", new_callable=AsyncMock, return_value=True), \
         patch.object(auth, "send_password_reset_email", new_callable=AsyncMock) as send:
        response = await auth.request_password_reset(
            auth.PasswordResetRequest(email="missing@example.com"), db=db
        )
    assert response["message"] == "If an account exists, a reset link will be emailed."
    send.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_account_gets_random_token_and_only_hash_persisted():
    user = account()
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [user]
    db.execute.return_value = result
    with patch.object(auth, "mail_delivery_configured", return_value=True), \
         patch.object(auth, "limit_password_reset_email", new_callable=AsyncMock, return_value=True), \
         patch.object(auth, "send_password_reset_email", new_callable=AsyncMock) as send:
        response = await auth.request_password_reset(
            auth.PasswordResetRequest(email="CREATOR@example.com"), db=db
        )
    assert response["message"] == "If an account exists, a reset link will be emailed."
    token = send.await_args.args[1]
    assert len(token) >= 40
    record = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], PasswordResetToken))
    assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in repr(record)
    assert record.user_id == user.id
    assert record.expires_at > datetime.now(timezone.utc)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_email_does_not_expose_account_existence():
    user = account()
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [user]
    db.execute.return_value = result
    with patch.object(auth, "mail_delivery_configured", return_value=True), \
         patch.object(auth, "limit_password_reset_email", new_callable=AsyncMock, return_value=True), \
         patch.object(auth, "send_password_reset_email", new_callable=AsyncMock, side_effect=RuntimeError("provider")):
        response = await auth.request_password_reset(
            auth.PasswordResetRequest(email=user.email), db=db
        )
    assert "If an account exists" in response["message"]
    assert db.commit.await_count == 2  # token created then invalidated


@pytest.mark.asyncio
async def test_reset_link_expiration_rejected():
    db = AsyncMock()
    db.scalar.return_value = SimpleNamespace(
        user_id=uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    with pytest.raises(HTTPException) as exc:
        await auth.confirm_password_reset(
            auth.PasswordResetConfirm(token="a" * 48, new_password="new secure password"), db=db
        )
    assert exc.value.status_code == 400
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_link_single_use_and_revokes_prior_sessions():
    user = account()
    token = "C" * 48
    reset = SimpleNamespace(user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(minutes=20))
    db = AsyncMock()
    db.scalar.side_effect = [reset, user, None]
    with patch.object(auth, "hash_password", return_value="new-hash"):
        await auth.confirm_password_reset(
            auth.PasswordResetConfirm(token=token, new_password="new secure password"), db=db
        )
    assert user.password_hash == "new-hash"
    assert user.session_version == 1
    assert any(isinstance(c.args[0], AuditLog) for c in db.add.call_args_list)
    db.commit.assert_awaited_once()
    with pytest.raises(HTTPException):
        await auth.confirm_password_reset(
            auth.PasswordResetConfirm(token=token, new_password="another secure password"), db=db
        )


@pytest.mark.asyncio
async def test_change_password_checks_old_password_and_revokes_sessions():
    user = account()
    db = AsyncMock()
    db.scalar.return_value = user
    with patch.object(auth, "verify_password", side_effect=[True, False]), \
         patch.object(auth, "hash_password", return_value="new-hash"):
        await auth.change_password(
            auth.PasswordChangeRequest(
                current_password="old", new_password="very secure updated password"
            ),
            user=user, db=db,
        )
    assert user.session_version == 1
    assert user.password_hash == "new-hash"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_password_rejects_invalid_current_password():
    user = account()
    db = AsyncMock()
    db.scalar.return_value = user
    with patch.object(auth, "verify_password", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await auth.change_password(
                auth.PasswordChangeRequest(
                    current_password="bad", new_password="very secure updated password"
                ), user=user, db=db,
            )
    assert exc.value.status_code == 401
    assert user.session_version == 0
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_all_requires_password_and_revokes_previous_tokens():
    user = account()
    db = AsyncMock()
    db.scalar.return_value = user
    with patch.object(auth, "verify_password", return_value=True):
        await auth.revoke_all_sessions(auth.RevokeSessionsRequest(password="right"), user=user, db=db)
    assert user.session_version == 1
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_access_token_session_version_is_enforced():
    user = account()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result
    request = Request({"type": "http", "headers": []})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="example")
    with patch("app.api.deps.decode_token", return_value={
        "type": "access", "sub": str(user.id), "sv": 0,
    }):
        assert await get_current_user(request, credentials=credentials, db=db) is user
        user.session_version = 1
        with pytest.raises(HTTPException, match="revoked") as exc:
            await get_current_user(request, credentials=credentials, db=db)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_legacy_token_is_only_accepted_before_first_revocation():
    user = account()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db.execute.return_value = result
    request = Request({"type": "http", "headers": []})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="example")
    with patch("app.api.deps.decode_token", return_value={"type": "access", "sub": str(user.id)}):
        assert await get_current_user(request, credentials=credentials, db=db) is user
        user.session_version = 2
        with pytest.raises(HTTPException):
            await get_current_user(request, credentials=credentials, db=db)


def test_jwt_access_refresh_version_claims():
    identity = str(uuid.uuid4())
    access = create_access_token(identity, {"sv": 4})
    refresh = create_refresh_token(identity, session_version=4)
    assert decode_token(access)["sv"] == 4
    assert decode_token(refresh)["sv"] == 4
    assert decode_token(refresh)["type"] == "refresh"


def test_reset_password_length_validation():
    with pytest.raises(ValidationError):
        auth.PasswordResetConfirm(token="x" * 48, new_password="too-short")
    with pytest.raises(ValidationError):
        auth.PasswordChangeRequest(current_password="old", new_password="short")


def test_reset_email_requires_https_in_production_when_configured():
    with pytest.raises(ValidationError, match="APP_URL"):
        Settings(
            _env_file=None, app_env="production",
            jwt_secret="strong-prod-jwt-secret-more-than-thirty-two-characters",
            reset_email_api_key="secret", reset_email_from="Baalebos <security@example.com>",
            app_url="http://example.com",
        )


def test_reset_token_digest_has_no_reversible_secret():
    token = "randomly_generated_value_that_should_not_be_saved"
    assert token not in hash_reset_token(token)
    assert len(hash_reset_token(token)) == 64


def test_account_security_routes_have_required_dependencies():
    from app.api.deps import get_current_user
    for endpoint in (auth.change_password, auth.revoke_all_sessions):
        route = next(r for r in auth.router.routes if r.endpoint == endpoint)
        assert any(dep.call is get_current_user for dep in route.dependant.dependencies)


@pytest.mark.asyncio
async def test_legacy_case_only_duplicate_accounts_are_not_reset_ambiguously():
    first, second = account(), account()
    first.email = "Creator@example.com"
    second.email = "creator@example.com"
    result = MagicMock()
    result.scalars.return_value.all.return_value = [first, second]
    db = AsyncMock()
    db.execute.return_value = result
    with patch.object(auth, "mail_delivery_configured", return_value=True), \
         patch.object(auth, "limit_password_reset_email", new_callable=AsyncMock, return_value=True), \
         patch.object(auth, "send_password_reset_email", new_callable=AsyncMock) as send:
        await auth.request_password_reset(auth.PasswordResetRequest(email="creator@example.com"), db=db)
    send.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_signup_normalizes_email_and_rejects_existing_casing():
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(email="Existing@EXAMPLE.COM")
    db = AsyncMock()
    db.execute.return_value = result
    with pytest.raises(HTTPException) as exc:
        await auth.signup(auth.SignupRequest(
            email="existing@example.com", password="a sufficiently long password",
        ), db=db)
    assert exc.value.status_code == 409
    db.commit.assert_not_awaited()
