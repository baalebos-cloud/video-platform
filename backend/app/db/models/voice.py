from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.db.session import Base


class Voice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "voices"

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    gender: Mapped[str | None] = mapped_column(String(32))
    voice_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
