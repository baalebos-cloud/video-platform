"""Phase 7: staged MFA device rotation and safe operator-audit pagination."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.api.v1 import admin, admin_mfa
from app.db.models.audit import AuditLog
from app.security import admin_mfa as crypto


def operator():
    return SimpleNamespace(id=uuid.uuid4(), email="admin@example.com", password_hash="hash")


def credential(*, secret="old-cipher", enabled=True):
    return SimpleNamespace(
        encrypted_secret=secret, enabled=enabled, last_used_step=-1,
        pending_encrypted_secret=None, pending_expires_at=None,
    )


@pytest.mark.asyncio
async def test_rotation_requires_existing_password():
    user = operator()
    db = AsyncMock()
    with patch.object(admin_mfa, "verify_password", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await admin_mfa.start_rotation(
                admin_mfa.RotationStart(password="wrong", code="123456"),
                admin=user, db=db,
            )
    assert exc.value.status_code == 401
    db.get.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_rotation_preserves_current_seed_and_audits():
    user = operator()
    old = crypto.generate_totp_secret()
    cred = credential(secret="old-encrypted")
    db = AsyncMock()
    db.get.return_value = cred
    now = 1700000000
    old_code = crypto.totp_code(old, now // 30)
    key = Fernet.generate_key().decode()
    from app.config.settings import Settings
    with patch.object(admin_mfa, "verify_password", return_value=True), \
         patch.object(admin_mfa, "decrypt_secret", return_value=old), \
         patch.object(crypto, "get_settings", return_value=Settings(_env_file=None, admin_mfa_encryption_key=key)), \
         patch.object(crypto.time, "time", return_value=now):
        response = await admin_mfa.start_rotation(
            admin_mfa.RotationStart(password="valid", code=old_code),
            admin=user, db=db,
        )
    assert cred.encrypted_secret == "old-encrypted"
    assert cred.enabled is True
    assert cred.pending_encrypted_secret != response["secret"]
    assert cred.pending_expires_at > datetime.now(timezone.utc)
    assert response["secret"] in response["otpauth_uri"]
    assert "replacement" in response["otpauth_uri"]
    assert any(isinstance(c.args[0], AuditLog) for c in db.add.call_args_list)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_rotation_rejects_consumed_old_totp():
    user = operator()
    old = crypto.generate_totp_secret()
    now = 1700000000
    cred = credential(secret="old-cipher")
    cred.last_used_step = now // 30
    db = AsyncMock()
    db.get.return_value = cred
    with patch.object(admin_mfa, "verify_password", return_value=True), \
         patch.object(admin_mfa, "decrypt_secret", return_value=old), \
         patch.object(crypto.time, "time", return_value=now):
        with pytest.raises(HTTPException) as exc:
            await admin_mfa.start_rotation(
                admin_mfa.RotationStart(password="valid", code=crypto.totp_code(old, now // 30)),
                admin=user, db=db,
            )
    assert exc.value.status_code == 401
    assert cred.pending_encrypted_secret is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_rotation_commits_replacement_only_after_new_code():
    user = operator()
    new = crypto.generate_totp_secret()
    now = 1700000000
    cred = credential()
    cred.pending_encrypted_secret = "new-encrypted"
    cred.pending_expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
    db = AsyncMock()
    db.get.return_value = cred
    with patch.object(admin_mfa, "decrypt_secret", return_value=new), \
         patch.object(crypto.time, "time", return_value=now):
        with pytest.raises(HTTPException) as exc:
            await admin_mfa.confirm_rotation(
                admin_mfa.RotationConfirm(code="000000"), admin=user, db=db,
            )
        assert exc.value.status_code == 401
        assert cred.encrypted_secret == "old-cipher"
        code = crypto.totp_code(new, now // 30)
        assert (await admin_mfa.confirm_rotation(
            admin_mfa.RotationConfirm(code=code), admin=user, db=db,
        )) == {"enabled": True, "rotated": True}
    assert cred.encrypted_secret == "new-encrypted"
    assert cred.pending_encrypted_secret is None
    assert cred.pending_expires_at is None
    assert cred.last_used_step == now // 30
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_rotation_leaves_original_authenticator_active():
    user = operator()
    cred = credential()
    cred.pending_encrypted_secret = "new-encrypted"
    cred.pending_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db = AsyncMock()
    db.get.return_value = cred
    with pytest.raises(HTTPException) as exc:
        await admin_mfa.confirm_rotation(admin_mfa.RotationConfirm(code="123456"), admin=user, db=db)
    assert exc.value.status_code == 410
    assert cred.encrypted_secret == "old-cipher"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_audit_page_redacts_unknown_metadata_and_exposes_cursor():
    user = operator()
    when = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(
            id=uuid.uuid4(), actor_id=user.id, created_at=when - timedelta(seconds=i),
            action="credit_adjustment", resource="user", resource_id=str(uuid.uuid4()),
            audit_metadata={"amount": 10, "currency": "CRD", "secret": "DO_NOT_EXPOSE"},
        )
        for i in range(3)
    ]
    db = AsyncMock()
    query_result = MagicMock()
    query_result.scalars.return_value.all.return_value = rows
    db.execute.return_value = query_result
    page = await admin.get_operator_audit(limit=2, cursor=None, admin=user, db=db)
    assert len(page["items"]) == 2
    assert page["next_cursor"] == f"{rows[1].created_at.isoformat()}|{rows[1].id}"
    assert "secret" not in page["items"][0]["details"]
    assert page["items"][0]["details"]["amount"] == 10
    page2 = await admin.get_operator_audit(limit=2, cursor=page["next_cursor"], admin=user, db=db)
    assert len(page2["items"]) == 2


@pytest.mark.asyncio
async def test_invalid_audit_cursor_is_rejected():
    with pytest.raises(HTTPException) as exc:
        await admin.get_operator_audit(limit=20, cursor="not-a-timestamp", admin=operator(), db=AsyncMock())
    assert exc.value.status_code == 400


def test_security_routes_require_admin_dependency():
    from app.security.admin import require_admin
    for endpoint in (admin_mfa.start_rotation, admin_mfa.confirm_rotation, admin.get_operator_audit):
        router = admin_mfa.router if endpoint in (admin_mfa.start_rotation, admin_mfa.confirm_rotation) else admin.router
        route = next(r for r in router.routes if r.endpoint == endpoint)
        assert any(d.call is require_admin for d in route.dependant.dependencies)
