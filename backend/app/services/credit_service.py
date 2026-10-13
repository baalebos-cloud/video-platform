"""Internal CRD ledger with serialized user-level debits and idempotent refunds.

CRD is a product usage unit, never interchangeable with USD or provider charges.
Caller controls the transaction; reserve before queueing any paid job.
"""
import math
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.models.billing import CreditLedgerEntry, LedgerEntryType
from app.db.models.user import User

CREDIT_CURRENCY = "CRD"


def generation_price(duration_seconds: int) -> Decimal:
    """Fixed units quoted before generation, independent of changing provider prices."""
    if duration_seconds <= 0:
        raise ValueError("Duration must be positive")
    return Decimal(math.ceil(duration_seconds / 30) * get_settings().credits_per_30_seconds)


async def balance(db: AsyncSession, user_id: uuid.UUID) -> Decimal:
    value = await db.scalar(
        select(func.coalesce(func.sum(CreditLedgerEntry.amount), 0)).where(
            CreditLedgerEntry.user_id == user_id,
            CreditLedgerEntry.currency == CREDIT_CURRENCY,
        )
    )
    return Decimal(value or 0)


async def _lock_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    # Serializes ledger mutations by user even when concurrent job requests run
    # through different API workers. Hold the lock until caller commits.
    locked = await db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    if locked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")


async def debit(
    db: AsyncSession, user_id: uuid.UUID, amount: Decimal | int,
    *, reference_type: str, reference_id: str, metadata: dict | None = None,
) -> None:
    if not get_settings().credit_enforcement_enabled:
        return
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("Debit amount must be positive")
    await _lock_user(db, user_id)
    existing = await db.scalar(select(CreditLedgerEntry.id).where(
        CreditLedgerEntry.user_id == user_id,
        CreditLedgerEntry.currency == CREDIT_CURRENCY,
        CreditLedgerEntry.entry_type == LedgerEntryType.DEBIT,
        CreditLedgerEntry.reference_type == reference_type,
        CreditLedgerEntry.reference_id == reference_id,
    ))
    if existing is not None:
        return
    available = await balance(db, user_id)
    if available < amount:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Insufficient usage credits: need {amount}, available {available}.",
        )
    db.add(CreditLedgerEntry(
        user_id=user_id, entry_type=LedgerEntryType.DEBIT, amount=-amount,
        currency=CREDIT_CURRENCY, reference_type=reference_type,
        reference_id=reference_id, entry_metadata=metadata or {},
    ))
    await db.flush()


async def refund(db: AsyncSession, user_id: uuid.UUID, *, reference_type: str, reference_id: str) -> bool:
    """Refund only a real debit; repeated refund attempts are safe."""
    await _lock_user(db, user_id)
    debit_entry = await db.scalar(select(CreditLedgerEntry).where(
        CreditLedgerEntry.user_id == user_id,
        CreditLedgerEntry.currency == CREDIT_CURRENCY,
        CreditLedgerEntry.entry_type == LedgerEntryType.DEBIT,
        CreditLedgerEntry.reference_type == reference_type,
        CreditLedgerEntry.reference_id == reference_id,
    ))
    if debit_entry is None:
        return False
    existing = await db.scalar(select(CreditLedgerEntry.id).where(
        CreditLedgerEntry.user_id == user_id,
        CreditLedgerEntry.currency == CREDIT_CURRENCY,
        CreditLedgerEntry.entry_type == LedgerEntryType.REFUND,
        CreditLedgerEntry.reference_type == reference_type,
        CreditLedgerEntry.reference_id == reference_id,
    ))
    if existing is not None:
        return False
    db.add(CreditLedgerEntry(
        user_id=user_id, entry_type=LedgerEntryType.REFUND,
        amount=-Decimal(debit_entry.amount), currency=CREDIT_CURRENCY,
        reference_type=reference_type, reference_id=reference_id,
        entry_metadata={"reason": "failed_operation"},
    ))
    await db.flush()
    return True
