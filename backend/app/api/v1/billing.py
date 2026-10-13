"""Credit ledger — the auditable balance mechanism required by blueprint section 12.1."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.billing import CreditLedgerEntry
from app.services.credit_service import CREDIT_CURRENCY
from app.services import usage_service
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/credits")
async def get_credit_balance(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(func.coalesce(func.sum(CreditLedgerEntry.amount), 0)).where(
            CreditLedgerEntry.user_id == user.id, CreditLedgerEntry.currency == CREDIT_CURRENCY,
        )
    )
    balance = result.scalar_one()
    return {"user_id": str(user.id), "balance": float(balance), "currency": CREDIT_CURRENCY}


@router.get("/credits/history")
async def get_credit_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CreditLedgerEntry)
        .where(CreditLedgerEntry.user_id == user.id, CreditLedgerEntry.currency == CREDIT_CURRENCY)
        .order_by(CreditLedgerEntry.created_at.desc())
        .limit(100)
    )
    entries = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "type": e.entry_type.value,
            "amount": float(e.amount),
            "currency": e.currency,
            "reference_type": e.reference_type,
            "reference_id": e.reference_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]


@router.get("/usage")
async def get_my_usage(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await usage_service.media_usage(db, owner_id=user.id, days=days)
