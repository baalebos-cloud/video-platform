import enum
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.session import Base


class VideoStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    PLANNING = "planning"
    SCRIPTING = "scripting"
    STORYBOARDING = "storyboarding"
    GENERATING_ASSETS = "generating_assets"
    RENDERING = "rendering"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Video(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "videos"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    status: Mapped[VideoStatus] = mapped_column(
        pg_enum(VideoStatus, "video_status"), default=VideoStatus.DRAFT, nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str] = mapped_column(String(64), default="English")
    locale: Mapped[str] = mapped_column(String(16), default="en-US")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=60)
    platform: Mapped[str] = mapped_column(String(64), default="youtube_shorts")
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="9:16")
    visual_style: Mapped[str] = mapped_column(String(64), default="cinematic_realistic")
    creativity: Mapped[str] = mapped_column(String(32), default="high")
    voice_preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(64))
    output_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )
    error_message: Mapped[str | None] = mapped_column(String(2048))

    project: Mapped["Project"] = relationship(back_populates="videos")
    scripts: Mapped[list["Script"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="video", cascade="all, delete-orphan")
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="video", cascade="all, delete-orphan")
