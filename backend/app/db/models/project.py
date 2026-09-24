import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.db.session import Base


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "projects"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[str | None] = mapped_column(String(255))
    brand_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    description: Mapped[str | None] = mapped_column(Text)

    owner: Mapped["User"] = relationship(back_populates="projects")
    videos: Mapped[list["Video"]] = relationship(back_populates="project", cascade="all, delete-orphan")
