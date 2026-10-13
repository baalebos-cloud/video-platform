"""Single-use OAuth authorization states; no raw credentials persisted."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models.mixins import TimestampMixin
from app.db.session import Base

class PublishingOAuthState(Base, TimestampMixin):
    __tablename__ = "publishing_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
