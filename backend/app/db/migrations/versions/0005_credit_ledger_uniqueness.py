"""Guarantee one internal-credit debit/refund per operation.

Revision ID: 0005_credit_ledger_uniqueness
Revises: 0004_scene_audio_and_rerender
"""
from alembic import op

revision = "0005_credit_ledger_uniqueness"
down_revision = "0004_scene_audio_and_rerender"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_credit_ledger_internal_reference",
        "credit_ledger",
        ["user_id", "entry_type", "reference_type", "reference_id", "currency"],
        unique=True,
        postgresql_where="currency = 'CRD' AND reference_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_credit_ledger_internal_reference", table_name="credit_ledger")
