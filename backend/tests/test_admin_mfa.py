"""Offline tests of encrypted TOTP enrollment, replay resistance, and admin scope."""
import base64
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1 import admin_mfa
from app.config.settings import Settings
from app.db.models.admin_mfa import AdminMfaCredential
from app.db.models.audit import AuditLog
from app.security import admin_mfa as security
from app.security.credit_payload import CreditAdjustment, digest_credit_adjustment


def account():
    return SimpleNamespace(id=uuid.uuid4(), email="operator@example.com", password_hash="hash")


def adjustment(**overrides):
    data = {"user_id": uuid.uuid4(), "amount": 20, "request_id": uuid.uuid4(),
            "reason": "Approved customer credit grant"}
    data.update(overrides)
    return CreditAdjustment(**data)


def config(**kwargs):
    data = {"_env_file": None, "admin_mfa_encryption_key": Fernet.generate_key().decode()}
    data.update(kwargs)
    return Settings(**data)


def test_rfc6238_sha1_reference_vector():
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert security.totp_code(secret, 1) == "287082"


def test_otp_replay_and_malformed_values_rejected():
    secret = security.generate_totp_secret()
    moment = 1700000000
    step = moment // 30
    code = security.totp_code(secret, step)
    assert security.valid_unused_step(secret, code, -1, now=moment) == step
    assert security.valid_unused_step(secret, code, step, now=moment) is None
    assert security.valid_unused_step(secret, "abcdef", -1, now=moment) is None


def test_seed_encrypted_at_rest_and_roundtrip():
    secret = security.generate_totp_secret()
    with patch.object(security, "get_settings", return_value=config()):
        encrypted = security.encrypt_secret(secret)
        assert secret not in encrypted
        assert security.decrypt_secret(encrypted) == secret


def test_encryption_unavailable_fails_closed():
    with patch.object(security, "get_settings", return_value=Settings(_env_file=None)):
        with pytest.raises(HTTPException) as exc:
            security.encrypt_secret(security.generate_totp_secret())
    assert exc.value.status_code == 503


def test_production_admin_requires_mfa_secret_key():
    with pytest.raises(ValidationError, match="ADMIN_MFA_ENCRYPTION_KEY"):
        Settings(_env_file=None, app_env="production", admin_user_ids_raw=str(uuid.uuid4()),
                 jwt_secret="secure-production-jwt-secret-stronger-than-thirty-two-characters")


def test_adjustment_digest_binds_recipient_amount_and_reference():
    sample = adjustment()
    digest = digest_credit_adjustment(sample)
    assert digest == digest_credit_adjustment(sample.model_copy(update={"reason": sample.reason + " "}))
    assert digest != digest_credit_adjustment(sample.model_copy(update={"amount": sample.amount + 1}))
    assert digest != digest_credit_adjustment(sample.model_copy(update={"user_id": uuid.uuid4()}))
    assert digest != digest_credit_adjustment(sample.model_copy(update={"request_id": uuid.uuid4()}))


def test_approval_requires_correct_operator_request_and_purpose():
    actor = str(uuid.uuid4())
    change = adjustment()
    digest = digest_credit_adjustment(change)
    token = security.issue_adjustment_token(actor, digest)
    security.verify_adjustment_token(token, user_id=actor, digest=digest)
    for wrong in (
        {"user_id": actor, "digest": "different"},
        {"user_id": str(uuid.uuid4()), "digest": digest},
    ):
        with pytest.raises(HTTPException) as exc:
            security.verify_adjustment_token(token, **wrong)
        assert exc.value.status_code == 403

    from app.security.auth import create_access_token
    with pytest.raises(HTTPException):
        security.verify_adjustment_token(create_access_token(actor), user_id=actor, digest=digest)


def test_expired_step_up_token_rejected():
    from app.security.auth import settings as auth_settings
    token = jwt.encode({
        "type": "admin_credit_step_up", "sub": "operator", "digest": "abc",
        "exp": int(time.time()) - 60,
    }, auth_settings.jwt_secret, algorithm=auth_settings.jwt_algorithm)
    with pytest.raises(HTTPException):
        security.verify_adjustment_token(token, user_id="operator", digest="abc")


async def make_request(value, token):
    encoded = json.dumps(value.model_dump(mode="json")).encode()
    async def receive():
        return {"type": "http.request", "body": encoded, "more_body": False}
    headers = [(b"x-admin-authorization", token.encode())] if token else []
    return Request({"type": "http", "headers": headers}, receive)


@pytest.mark.asyncio
async def test_actual_adjustment_dependency_rejects_changed_body():
    actor = account()
    change = adjustment()
    token = security.issue_adjustment_token(str(actor.id), digest_credit_adjustment(change))
    await security.require_adjustment_authorization(await make_request(change, token), user=actor)
    with pytest.raises(HTTPException) as exc:
        await security.require_adjustment_authorization(
            await make_request(change.model_copy(update={"amount": 25}), token), user=actor
        )
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        await security.require_adjustment_authorization(await make_request(change, None), user=actor)


def test_credit_adjustment_route_has_step_up_dependency():
    from app.api.v1.admin import router, adjust_credits
    route = next(r for r in router.routes if r.endpoint == adjust_credits)
    assert any(d.call is security.require_adjustment_authorization for d in route.dependant.dependencies)


@pytest.mark.asyncio
async def test_enrollment_requires_password_and_never_stores_plaintext_seed():
    actor = account()
    db = AsyncMock()
    db.get.return_value = None
    with patch.object(admin_mfa, "verify_password", return_value=True), \
         patch.object(security, "get_settings", return_value=config()):
        response = await admin_mfa.enroll(
            admin_mfa.AdminPassword(password="correct pass"), admin=actor, db=db
        )
    assert response["secret"] in response["otpauth_uri"]
    created = [call.args[0] for call in db.add.call_args_list if isinstance(call.args[0], AdminMfaCredential)]
    assert len(created) == 1
    assert response["secret"] not in created[0].encrypted_secret
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrollment_cannot_replace_enabled_totp():
    actor = account()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(enabled=True)
    with patch.object(admin_mfa, "verify_password", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await admin_mfa.enroll(admin_mfa.AdminPassword(password="right"), admin=actor, db=db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_activation_consumes_first_code_and_audits():
    actor = account()
    secret = security.generate_totp_secret()
    moment = 1700000000
    step = moment // 30
    cred = SimpleNamespace(enabled=False, encrypted_secret="cipher", last_used_step=-1)
    db = AsyncMock()
    db.get.return_value = cred
    with patch.object(admin_mfa, "decrypt_secret", return_value=secret), \
         patch.object(security.time, "time", return_value=moment):
        result = await admin_mfa.activate(
            admin_mfa.TotpConfirmation(code=security.totp_code(secret, step)), admin=actor, db=db
        )
    assert result["enabled"] and cred.enabled
    assert cred.last_used_step == step
    assert any(isinstance(c.args[0], AuditLog) for c in db.add.call_args_list)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_authorize_adjustment_rejects_replayed_code():
    actor = account()
    secret = security.generate_totp_secret()
    moment = 1700000000
    step = moment // 30
    cred = SimpleNamespace(enabled=True, encrypted_secret="cipher", last_used_step=-1)
    db = AsyncMock()
    db.get.return_value = cred
    payload = admin_mfa.CreditStepUpRequest(
        password="password", code=security.totp_code(secret, step), adjustment=adjustment()
    )
    with patch.object(admin_mfa, "verify_password", return_value=True), \
         patch.object(admin_mfa, "decrypt_secret", return_value=secret), \
         patch.object(security.time, "time", return_value=moment):
        result = await admin_mfa.authorize_adjustment(payload, admin=actor, db=db)
        security.verify_adjustment_token(
            result["authorization_token"], user_id=str(actor.id),
            digest=digest_credit_adjustment(payload.adjustment),
        )
        with pytest.raises(HTTPException) as exc:
            await admin_mfa.authorize_adjustment(payload, admin=actor, db=db)
    assert cred.last_used_step == step
    assert exc.value.status_code == 401
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_authorization_requires_enabled_factor():
    actor = account()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(enabled=False)
    with patch.object(admin_mfa, "verify_password", return_value=True):
        with pytest.raises(HTTPException) as exc:
            await admin_mfa.authorize_adjustment(
                admin_mfa.CreditStepUpRequest(
                    password="password", code="123456", adjustment=adjustment()
                ), admin=actor, db=db,
            )
    assert exc.value.status_code == 403
    db.commit.assert_not_awaited()
