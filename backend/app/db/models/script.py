import enum
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.session import Base


class ScriptStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class Script(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scripts"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(64), default="English")
    status: Mapped[ScriptStatus] = mapped_column(
        pg_enum(ScriptStatus, "script_status"), default=ScriptStatus.DRAFT
    )

    video: Mapped["Video"] = relationship(back_populates="scripts")
