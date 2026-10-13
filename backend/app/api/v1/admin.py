"""Secure operator workflows: idempotent CRD adjustments and recorded usage."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog
from app.db.models.billing import CreditLedgerEntry, LedgerEntryType
from app.db.models.user import User, UserStatus
from app.db.session import get_db
from app.security.admin import require_admin
from app.services import credit_service, usage_service

router = APIRouter(prefix="/admin", tags=["admin"])


class CreditAdjustment(BaseModel):
    user_id: uuid.UUID
    amount: int = Field(ge=-1000, le=1000)
    request_id: uuid.UUID
    reason: str = Field(min_length=12, max_length=300)

    @model_validator(mode="after")
    def nonzero(self):
        if not self.amount:
            raise ValueError("Credit adjustment amount cannot be zero")
        if not self.reason.strip() or len(self.reason.strip()) < 12:
            raise ValueError("A meaningful adjustment reason is required")
        return self


@router.get("/users/lookup")
async def lookup_user(
    email: EmailStr,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    account = await db.scalar(select(User).where(User.email == str(email)))
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    balance = await credit_service.balance(db, account.id)
    return {
        "id": str(account.id),
        "email": account.email,
        "status": account.status.value,
        "balance": str(balance),
        "currency": credit_service.CREDIT_CURRENCY,
    }


@router.post("/credits/adjust")
async def adjust_credits(
    payload: CreditAdjustment,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # A database row lock, rather than an application mutex, serializes
    # concurrent requests across independent API instances.
    target = await db.scalar(select(User).where(User.id == payload.user_id).with_for_update())
    if target is None or target.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Active account not found")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Self-adjustment is not permitted")

    reference_id = str(payload.request_id)
    existing = await db.scalar(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.user_id == target.id,
            CreditLedgerEntry.entry_type == LedgerEntryType.ADJUSTMENT,
            CreditLedgerEntry.currency == credit_service.CREDIT_CURRENCY,
            CreditLedgerEntry.reference_type == "admin_adjustment",
            CreditLedgerEntry.reference_id == reference_id,
        )
    )
    if existing is not None:
        details = existing.entry_metadata or {}
        if (Decimal(existing.amount) != Decimal(payload.amount)
                or details.get("actor_id") != str(admin.id)
                or details.get("reason") != payload.reason.strip()):
            raise HTTPException(status.HTTP_409_CONFLICT, "Request ID used with different adjustment details")
        return {
            "request_id": reference_id,
            "applied": False,
            "currency": credit_service.CREDIT_CURRENCY,
            "balance": str(await credit_service.balance(db, target.id)),
        }

    current = await credit_service.balance(db, target.id)
    if Decimal(payload.amount) + current < 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Adjustment would create a negative balance")

    db.add(CreditLedgerEntry(
        user_id=target.id, entry_type=LedgerEntryType.ADJUSTMENT,
        amount=Decimal(payload.amount), currency=credit_service.CREDIT_CURRENCY,
        reference_type="admin_adjustment", reference_id=reference_id,
        entry_metadata={"actor_id": str(admin.id), "reason": payload.reason.strip()},
    ))
    db.add(AuditLog(
        actor_id=admin.id, action="credit_adjustment",
        resource="user", resource_id=str(target.id),
        audit_metadata={
            "request_id": reference_id, "amount": payload.amount,
            "currency": credit_service.CREDIT_CURRENCY,
            "reason": payload.reason.strip(),
        },
    ))
    await db.flush()
    updated = await credit_service.balance(db, target.id)
    await db.commit()
    return {
        "request_id": reference_id, "applied": True,
        "currency": credit_service.CREDIT_CURRENCY, "balance": str(updated),
    }


@router.get("/usage")
async def get_platform_usage(
    days: int = Query(default=30, ge=1, le=90),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await usage_service.media_usage(db, days=days)
