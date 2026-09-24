import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def pg_enum(enum_cls, name: str):
    """
    Postgres ENUM column bound to a Python str-enum, storing `.value`
    (e.g. "active") rather than SQLAlchemy's default `.name` (e.g. "ACTIVE").
    Keeps ORM-side enum members and the Postgres type's labels in sync.
    """
    from sqlalchemy import Enum as SAEnum

    return SAEnum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])
