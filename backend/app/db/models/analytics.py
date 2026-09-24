import uuid

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.db.session import Base


class AnalyticsSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "analytics_snapshots"

    published_video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("published_videos.id", ondelete="CASCADE"), index=True
    )
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
