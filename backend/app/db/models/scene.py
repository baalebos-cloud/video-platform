import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.db.session import Base


class Scene(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scenes"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    narration: Mapped[str] = mapped_column(Text, default="")
    visual_prompt: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[float] = mapped_column(default=5.0)
    camera: Mapped[str | None] = mapped_column(String(255))
    lighting: Mapped[str | None] = mapped_column(String(255))
    on_screen_text: Mapped[str | None] = mapped_column(String(512))
    continuity_reference_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    negative_constraints: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    visual_asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))

    video: Mapped["Video"] = relationship(back_populates="scenes")
