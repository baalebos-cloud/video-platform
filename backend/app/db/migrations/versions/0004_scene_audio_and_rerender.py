"""Persist scene narration assets and render-dirty state.

Revision ID: 0004_scene_audio_and_rerender
Revises: 0003_video_thumbnails
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_scene_audio_and_rerender"
down_revision = "0003_video_thumbnails"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("audio_asset_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_scenes_audio_asset_id_assets", "scenes", "assets",
        ["audio_asset_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column(
        "videos", sa.Column("needs_rerender", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )


def downgrade() -> None:
    op.drop_column("videos", "needs_rerender")
    op.drop_constraint("fk_scenes_audio_asset_id_assets", "scenes", type_="foreignkey")
    op.drop_column("scenes", "audio_asset_id")
