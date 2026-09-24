import enum
import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.session import Base


class JobType(str, enum.Enum):
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    VOICE = "voice"
    VISUAL = "visual"
    CAPTION = "caption"
    RENDER = "render"
    PUBLISH = "publish"
    VIDEO_GENERATION = "video_generation"  # umbrella pipeline job


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "generation_jobs"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    type: Mapped[JobType] = mapped_column(pg_enum(JobType, "job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), default=JobStatus.QUEUED, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    input_hash: Mapped[str | None] = mapped_column(String(128))
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(10, 4))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2048))
    output_asset_ids: Mapped[list] = mapped_column(JSONB, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), index=True)

    video: Mapped["Video"] = relationship(back_populates="jobs")
