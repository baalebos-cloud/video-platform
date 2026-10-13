"""Operator-only adjustments and recorded provider output reporting.

All tests run offline; no external API calls or payment-provider integration.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import admin, billing, users
from app.config.settings import Settings
from app.db.models.asset import AssetType
from app.db.models.audit import AuditLog
from app.db.models.billing import CreditLedgerEntry, LedgerEntryType
from app.db.models.user import UserStatus
from app.security.admin import require_admin
from app.services import usage_service


def administrator():
    return SimpleNamespace(id=uuid.uuid4(), email="admin@example.com")


def target():
    return SimpleNamespace(id=uuid.uuid4(), email="creator@example.com", status=UserStatus.ACTIVE)


def payload(person, *, amount=20, reason="Approved manual starter grant", request_id=None):
    return admin.CreditAdjustment(
        user_id=person.id, amount=amount, request_id=request_id or uuid.uuid4(), reason=reason,
    )


@pytest.mark.asyncio
async def test_normal_user_is_forbidden_from_admin_routes():
    user = administrator()
    with patch("app.security.admin.get_settings", return_value=Settings(
        _env_file=None, admin_user_ids_raw=str(uuid.uuid4())
    )):
        with pytest.raises(HTTPException) as exc:
            await require_admin(user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_provisioned_uuid_is_authorized():
    user = administrator()
    with patch("app.security.admin.get_settings", return_value=Settings(
        _env_file=None, admin_user_ids_raw=str(user.id)
    )):
        assert await require_admin(user=user) is user


def test_invalid_admin_uuid_setting_rejected_at_startup():
    with pytest.raises(ValidationError, match="ADMIN_USER_IDS_RAW"):
        Settings(_env_file=None, admin_user_ids_raw="not-a-uuid")


def test_adjustment_requires_reason_nonzero_and_bounded_amount():
    person = target()
    with pytest.raises(ValidationError):
        payload(person, amount=0)
    with pytest.raises(ValidationError):
        payload(person, amount=1001)
    with pytest.raises(ValidationError):
        payload(person, reason="tiny")


@pytest.mark.asyncio
async def test_credit_adjustment_writes_audited_idempotent_ledger_entry():
    actor, person = administrator(), target()
    db = AsyncMock()
    db.scalar.side_effect = [person, None, Decimal(5), Decimal(25)]
    request = payload(person)
    result = await admin.adjust_credits(request, admin=actor, db=db)
    assert result["applied"] is True
    assert result["balance"] == "25"
    additions = [call.args[0] for call in db.add.call_args_list]
    ledger = next(item for item in additions if isinstance(item, CreditLedgerEntry))
    audit = next(item for item in additions if isinstance(item, AuditLog))
    assert ledger.currency == "CRD"
    assert ledger.entry_type == LedgerEntryType.ADJUSTMENT
    assert Decimal(ledger.amount) == Decimal(20)
    assert ledger.entry_metadata["actor_id"] == str(actor.id)
    assert audit.actor_id == actor.id
    assert audit.audit_metadata["request_id"] == str(request.request_id)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_admin_credit_request_is_replayed_without_second_write():
    actor, person = administrator(), target()
    request = payload(person)
    db = AsyncMock()
    db.scalar.side_effect = [
        person,
        SimpleNamespace(
            amount=Decimal(20), entry_metadata={"actor_id": str(actor.id), "reason": request.reason},
        ),
        Decimal(40),
    ]
    response = await admin.adjust_credits(request, admin=actor, db=db)
    assert response["applied"] is False
    assert response["balance"] == "40"
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_credit_request_reuse_with_different_amount_is_rejected():
    actor, person = administrator(), target()
    db = AsyncMock()
    db.scalar.side_effect = [
        person,
        SimpleNamespace(
            amount=Decimal(10), entry_metadata={"actor_id": str(actor.id), "reason": "Approved manual starter grant"},
        ),
    ]
    with pytest.raises(HTTPException) as exc:
        await admin.adjust_credits(payload(person), admin=actor, db=db)
    assert exc.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_negative_adjustment_cannot_overdraw():
    actor, person = administrator(), target()
    db = AsyncMock()
    db.scalar.side_effect = [person, None, Decimal(4)]
    with pytest.raises(HTTPException) as exc:
        await admin.adjust_credits(payload(person, amount=-5), admin=actor, db=db)
    assert exc.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_admin_cannot_adjust_own_credits():
    actor = administrator()
    db = AsyncMock()
    db.scalar.return_value = SimpleNamespace(id=actor.id, status=UserStatus.ACTIVE)
    with pytest.raises(HTTPException) as exc:
        await admin.adjust_credits(payload(actor), admin=actor, db=db)
    assert exc.value.status_code == 403
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_admin_cannot_adjust_nonactive_target():
    actor, person = administrator(), target()
    person.status = UserStatus.SUSPENDED
    db = AsyncMock()
    db.scalar.return_value = person
    with pytest.raises(HTTPException) as exc:
        await admin.adjust_credits(payload(person), admin=actor, db=db)
    assert exc.value.status_code == 404
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_user_lookup_returns_only_requested_account():
    actor, person = administrator(), target()
    db = AsyncMock()
    db.scalar.return_value = person
    with patch.object(admin.credit_service, "balance", new_callable=AsyncMock, return_value=Decimal(5)):
        result = await admin.lookup_user(person.email, admin=actor, db=db)
    assert result["email"] == person.email
    assert result["balance"] == "5"
    assert db.scalar.await_count == 1


@pytest.mark.asyncio
async def test_usage_summary_counts_only_recorded_saved_assets():
    db = AsyncMock()
    from unittest.mock import MagicMock
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(provider="openai", model="gpt-image-1.5", type=AssetType.IMAGE, outputs=4),
        SimpleNamespace(provider="openai", model="gpt-4o-mini-tts", type=AssetType.AUDIO, outputs=3),
    ]
    db.execute.return_value = result
    summary = await usage_service.media_usage(db, days=7)
    assert summary["recorded_outputs"] == 7
    assert summary["breakdown"][0]["provider"] == "openai"
    assert "not" in summary["metric_note"].lower() or "does not" in summary["metric_note"].lower()


@pytest.mark.asyncio
async def test_billing_usage_scoped_to_logged_in_creator():
    creator = SimpleNamespace(id=uuid.uuid4())
    db = AsyncMock()
    with patch.object(billing.usage_service, "media_usage", new_callable=AsyncMock, return_value={
        "recorded_outputs": 0, "breakdown": [],
    }) as service:
        await billing.get_my_usage(days=30, user=creator, db=db)
    service.assert_awaited_once_with(db, owner_id=creator.id, days=30)


@pytest.mark.asyncio
async def test_profile_only_reports_admin_for_configured_id():
    creator = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", full_name="Creator", status=UserStatus.ACTIVE)
    with patch.object(users, "get_settings", return_value=Settings(_env_file=None, admin_user_ids_raw="")):
        response = await users.get_me(user=creator)
    assert response["is_admin"] is False
