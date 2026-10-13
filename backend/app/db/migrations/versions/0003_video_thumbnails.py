"""Link generated thumbnail assets to videos.

Revision ID: 0003_video_thumbnails
Revises: 0002_idempotency_uniqueness
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_video_thumbnails"
down_revision = "0002_idempotency_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("thumbnail_asset_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_videos_thumbnail_asset_id_assets", "videos", "assets",
        ["thumbnail_asset_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_videos_thumbnail_asset_id_assets", "videos", type_="foreignkey")
    op.drop_column("videos", "thumbnail_asset_id")
