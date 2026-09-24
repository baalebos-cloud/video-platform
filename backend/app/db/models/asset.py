import enum
import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum
from app.db.session import Base


class AssetType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    CAPTION = "caption"
    THUMBNAIL = "thumbnail"
    FINAL_VIDEO = "final_video"


class Asset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assets"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[AssetType] = mapped_column(pg_enum(AssetType, "asset_type"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    checksum: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    provider_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
