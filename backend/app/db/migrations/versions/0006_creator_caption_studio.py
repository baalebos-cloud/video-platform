"""Persist editable scene subtitles and an approved caption style.

Revision ID: 0006_creator_caption_studio
Revises: 0005_credit_ledger_uniqueness
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_creator_caption_studio"
down_revision = "0005_credit_ledger_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("caption_text", sa.Text(), nullable=True))
    op.add_column(
        "videos", sa.Column(
            "caption_style", sa.String(length=32), nullable=False,
            server_default=sa.text("'classic'"),
        )
    )


def downgrade() -> None:
    op.drop_column("videos", "caption_style")
    op.drop_column("scenes", "caption_text")
