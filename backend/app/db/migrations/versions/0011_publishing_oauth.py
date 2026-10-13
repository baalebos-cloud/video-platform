"""Encrypted publishing accounts and one-time OAuth states.

Revision ID: 0011_publishing_oauth
Revises: 0010_rotating_sessions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "0011_publishing_oauth"
down_revision = "0010_rotating_sessions"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("publishing_accounts", sa.Column("token_ciphertext", sa.Text(), nullable=True))
    op.create_table(
        "publishing_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table("publishing_oauth_states")
    op.drop_column("publishing_accounts", "token_ciphertext")
