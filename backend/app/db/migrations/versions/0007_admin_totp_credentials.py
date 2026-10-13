"""Encrypted administrator TOTP second factor.

Revision ID: 0007_admin_totp_credentials
Revises: 0006_creator_caption_studio
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_admin_totp_credentials"
down_revision = "0006_creator_caption_studio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_mfa_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_used_step", sa.BigInteger(), nullable=False, server_default=sa.text("-1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("admin_mfa_credentials")
