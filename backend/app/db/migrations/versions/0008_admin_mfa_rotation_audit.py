"""Stage TOTP device replacement and index the operator audit timeline.

Revision ID: 0008_admin_mfa_rotation_audit
Revises: 0007_admin_totp_credentials
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_admin_mfa_rotation_audit"
down_revision = "0007_admin_totp_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admin_mfa_credentials", sa.Column("pending_encrypted_secret", sa.Text(), nullable=True))
    op.add_column("admin_mfa_credentials", sa.Column("pending_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_audit_logs_created_at_id", "audit_logs", ["created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at_id", table_name="audit_logs")
    op.drop_column("admin_mfa_credentials", "pending_expires_at")
    op.drop_column("admin_mfa_credentials", "pending_encrypted_secret")
