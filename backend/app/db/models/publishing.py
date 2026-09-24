import enum
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.session import Base


class PublishStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    PUBLISH_FAILED = "publish_failed"
    RETRYING = "retrying"


class PublishingAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "publishing_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    token_ref: Mapped[str] = mapped_column(String(255), nullable=False)  # reference into secret manager, never the raw token

    published_videos: Mapped[list["PublishedVideo"]] = relationship(back_populates="account")


class PublishedVideo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "published_videos"

    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    publishing_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publishing_accounts.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    external_post_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[PublishStatus] = mapped_column(
        pg_enum(PublishStatus, "publish_status"), default=PublishStatus.DRAFT
    )

    account: Mapped["PublishingAccount"] = relationship(back_populates="published_videos")
