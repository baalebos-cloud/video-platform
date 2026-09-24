import enum
import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.session import Base


class LedgerEntryType(str, enum.Enum):
    PURCHASE = "purchase"
    DEBIT = "debit"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class CreditLedgerEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "credit_ledger"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    entry_type: Mapped[LedgerEntryType] = mapped_column(pg_enum(LedgerEntryType, "ledger_entry_type"))
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    reference_type: Mapped[str | None] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    entry_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
