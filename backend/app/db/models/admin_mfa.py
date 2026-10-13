"""Encrypted TOTP credentials for the explicit operator UUID allowlist."""
import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.mixins import TimestampMixin
from app.db.session import Base


class AdminMfaCredential(Base, TimestampMixin):
    __tablename__ = "admin_mfa_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_used_step: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=-1, server_default="-1"
    )
